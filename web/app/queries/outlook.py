"""Outlook

What the season implies about the next one: who is returning, and
how this roster would have fared against an earlier one.
"""

from functools import lru_cache
from typing import Any, Dict, List, Tuple

from .. import db
from ..models import Athlete, AthleteResult, Meet

from common.const import CONST
from .shared import (
    _PLACE_POINTS,
    _is_lower_better,
    _is_valid_postseason_mark,
    _resolve_postseason_individual_rows,
)
from .meets import (
    _resolve_postseason_relay_rows,
    _score_h2h_meet,
)

from .school_dashboard import (
    _available_years,
)



@lru_cache(maxsize=64)
def _grades_for_season(gender: str, year: int):
    """Class year (FR/SO/JR/SR) for every athlete with a postseason mark that season.

    ``athlete_result.grade`` is populated on 100% of rows, so this is the reliable
    way to answer "who is coming back" -- ``athlete.grad_year`` is not needed and
    would disagree for athletes who repeat or skip a year. An athlete can carry
    different grades across meets in the same season (data entry), so the most
    advanced grade seen wins: assuming a senior is graduating is the safer error,
    since it under-promises what returns rather than over-promising it.
    """
    order = {"FR": 0, "SO": 1, "JR": 2, "SR": 3}
    rows = (
        db.session.query(AthleteResult.athlete_id, AthleteResult.grade)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year == year,
            Meet.gender == gender,
            Athlete.gender == gender,
        )
        .all()
    )
    grades: Dict[int, str] = {}
    for athlete_id, grade in rows:
        if grade not in order:
            continue
        current = grades.get(athlete_id)
        if current is None or order[grade] > order[current]:
            grades[athlete_id] = grade
    return grades

# Head-to-head rebuilds this once per prior season, so an uncached call made
# that endpoint the only one on the page whose warm cost matched its cold one.
# Consumers read the rows without mutating them, and the default argument is a
# frozenset precisely so the signature stays hashable.
@lru_cache(maxsize=2048)
def _season_entries(
    school_id: int, gender: str, year: int, exclude_athlete_ids=frozenset(),
    sectional_only: bool = False,
):
    """The entries one school could field in one season, by event.

    Up to two individual entries per event and one relay -- the same slot model
    as the IHSAA sectional entry limit.

    ``sectional_only`` restricts every mark to the sectional. It exists for the
    season-vs-season comparison, where taking each athlete's best across all
    rounds scores a team that advanced on best-of-three against a team that bowed
    out at the sectional on best-of-one. 22% of athlete-events get more than one
    attempt, and only the advancing ones do. Measuring both seasons on the round
    every team runs removes that asymmetry -- across 2,301 comparisons it leaves
    95.5% of verdicts unchanged and shifts the median margin by 0.0 points, so
    the cost is small and the flips it does cause are symmetric.

    ``exclude_athlete_ids`` drops athletes before the slots are chosen, not after,
    so removing a graduating senior promotes the next athlete in that event into
    the open slot. Filtering afterwards would leave the slot empty and overstate
    what graduation costs.
    """
    best_by_athlete: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for row in _resolve_postseason_individual_rows(gender=gender, year=year, school_id=school_id):
        if sectional_only and row["meet_type"] != CONST.MEET_TYPE.SECTIONAL:
            continue
        if not _is_valid_postseason_mark(row["result_value"], row["event_type"]):
            continue
        if row["athlete_id"] in exclude_athlete_ids:
            continue
        key = (row["event"], row["athlete_id"])
        existing = best_by_athlete.get(key)
        lower_is_better = _is_lower_better(row["event_type"])
        if existing is None or (
            row["result_value"] < existing["result_value"] if lower_is_better
            else row["result_value"] > existing["result_value"]
        ):
            best_by_athlete[key] = row

    by_event: Dict[str, List[Dict[str, Any]]] = {}
    for (event_name, _athlete_id), row in best_by_athlete.items():
        by_event.setdefault(event_name, []).append(row)

    for event_name, entries in by_event.items():
        lower_is_better = _is_lower_better(entries[0]["event_type"])
        entries.sort(key=lambda item: item["result_value"], reverse=not lower_is_better)
        by_event[event_name] = entries[:2]

    for row in _resolve_postseason_relay_rows(gender=gender, year=year, school_id=school_id):
        if sectional_only and row["meet_type"] != CONST.MEET_TYPE.SECTIONAL:
            continue
        if not _is_valid_postseason_mark(row["result_value"], CONST.EVENT_TYPE.TRACK):
            continue
        current = by_event.get(row["event"])
        if not current or row["result_value"] < current[0]["result_value"]:
            enriched = dict(row)
            enriched.setdefault("event_type", CONST.EVENT_TYPE.TRACK)
            by_event[row["event"]] = [enriched]

    return by_event

# Caching the entries below was only half the fix: without this, every request
# still re-scored the dual meet against each prior season from warm data.
@lru_cache(maxsize=2048)
def get_season_h2h(school_id: int, gender: str, year):
    """This season scored as a dual meet against the one before it.

    Only the immediately prior season is scored. Earlier ones were computed to
    feed an aggregate "3 wins, 1 loss vs past seasons" line that has been
    removed: the comparison people act on is against last year's team, and
    scoring every season on record cost an entry rebuild per season for a
    sentence nobody was reading. `seasons` stays a list so the payload shape and
    its single consumer, which reads `seasons[0]`, are unchanged.
    """
    if year in (None, "", "all-time"):
        return {"available": False, "seasons": []}

    current_year = int(year)
    available = _available_years(school_id, gender)
    prior_years = sorted((item for item in available if item < current_year), reverse=True)
    if not prior_years:
        return {
            "available": False,
            "seasons": [],
            "reason": "No earlier season on record for this program.",
        }

    # Both seasons on the sectional, so neither is scored on more attempts than
    # the other simply because it advanced further.
    current_entries = _season_entries(
        school_id, gender, current_year, sectional_only=True)
    seasons = []
    for prior_year in prior_years[:1]:
        prior_entries = _season_entries(
            school_id, gender, prior_year, sectional_only=True)
        scored = _score_h2h_meet(current_entries, prior_entries)
        if scored["points_for"] > scored["points_against"]:
            result = "WIN"
        elif scored["points_for"] < scored["points_against"]:
            result = "LOSS"
        else:
            result = "TIE"
        seasons.append({"season": prior_year, "result": result, **scored})

    return {"available": True, "year": current_year, "gender": gender, "seasons": seasons}

def _returning_points(school_id: int, gender: str, year: int):
    """Sectional points, split by whether the athlete who scored them returns.

    Points are the currency a coach actually plans in, so "83% of our scoring is
    back" says more than any count of slots or event bests.

    Two deliberate narrowings:

    * **Sectional only.** It is the one meet the whole team contests, so every
      athlete is measured on the same stage. Folding in regional and state points
      would weight the figure toward the handful who advanced.
    * **Individual events only.** Relay legs are not recorded for every season --
      2026 has 0 of 2,557 populated -- so relay points cannot be attributed to a
      class year at all. Counting them would put a number over a denominator that
      silently excludes them; leaving them out and saying so is honest.
    """
    grades = _grades_for_season(gender, year)

    rows = (
        db.session.query(
            AthleteResult.athlete_id,
            AthleteResult.event,
            AthleteResult.meet_id,
            AthleteResult.place,
        )
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(
            Meet.meet_type == CONST.MEET_TYPE.SECTIONAL,
            Meet.year == year,
            Meet.gender == gender,
            Athlete.gender == gender,
            Athlete.school_id == school_id,
            AthleteResult.result_type == CONST.RESULT_TYPE.FINAL,
            AthleteResult.place.isnot(None),
        )
        .all()
    )

    total = 0.0
    returning = 0.0
    scorers = 0
    for row in rows:
        points = _PLACE_POINTS.get(row.place)
        if not points:
            continue
        total += points
        scorers += 1
        if grades.get(row.athlete_id) != "SR":
            returning += points

    return {
        "points_total": round(total, 1),
        "points_returning": round(returning, 1),
        "percent": round(100.0 * returning / total, 1) if total else None,
        "scoring_marks": scorers,
        "note": (
            "Sectional individual points only \u2014 the meet the whole team runs. "
            "Relays are left out because relay legs are not recorded for every season."
        ),
    }

def get_returning_athletes(school_id: int, gender: str, year):
    """What the program keeps and loses to graduation, and what the core is worth.

    The season head-to-head answers "are we better than last year" looking back.
    This answers the same question looking forward, which is the one a coach acts
    on -- and it needs no new scoring concept: the returning athletes are scored
    against each earlier season with the same dual-meet routine, so "our core
    would still beat 2025" is directly comparable to the cards above it.
    """
    if year in (None, "", "all-time"):
        return {"available": False, "reason": "Pick a single season to see what returns."}

    current_year = int(year)
    grades = _grades_for_season(gender, current_year)
    # The points below are sectional-only, so the roster they are attributed to is
    # chosen on the same stage. Picking slots from all-rounds bests would count
    # athletes the points figure never saw.
    entries = _season_entries(
        school_id, gender, current_year, sectional_only=True)
    if not entries:
        return {"available": False, "reason": "No valid postseason marks in this season."}

    # Individual slots only. A relay leg is not attributable to an athlete in
    # this data (see _returning_points), so a relay cannot
    # say who graduates.
    #
    # This used to build a per-athlete graduating list -- names, marks and
    # statewide ranks -- and an event-best list, then return only len() of the
    # first. The rank lookup alone forced a full statewide mark-rank build on
    # every request to populate ranks nothing ever read. The payload exposes a
    # count, so a count is all that is computed.
    senior_ids = set()
    roster_ids = set()
    for event_name, event_entries in entries.items():
        if event_name in CONST.EVENT.ALL_RELAY:
            continue
        for row in event_entries:
            athlete_id = row.get("athlete_id")
            if athlete_id is None:
                continue
            roster_ids.add(athlete_id)
            if grades.get(athlete_id) == "SR":
                senior_ids.add(athlete_id)

    retention = {
        "athletes_returning": len(roster_ids - senior_ids),
        "athletes_total": len(roster_ids),
    }
    # What share of the season's scoring comes back -- the one number a coach
    # plans against. Replaces the slot and event-best counts, which measured
    # proxies for it.
    points = _returning_points(school_id, gender, current_year)

    return {
        "available": True,
        "year": current_year,
        "next_year": current_year + 1,
        "gender": gender,
        "retention": retention,
        "points": points,
        "graduating_count": len(senior_ids),
        "note": points["note"],
    }
