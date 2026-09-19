"""Rankings

Where a program sits statewide.

The composite score and the ranking built from it. Expensive -- it reads every
result in the state -- which is why the dashboards are precomputed rather than
worked out per request.
"""

from .shared import (  # noqa: F401  -- shared setup and constants
    Any,
    Athlete,
    AthleteResult,
    CONST,
    Dict,
    Event,
    List,
    MIN_RECORDS_YEAR,
    Meet,
    Optional,
    RelayResult,
    School,
    Tuple,
    bisect,
    db,
    lru_cache,
    statistics,
)
from .shared import (
    _build_school_roster,
    _competition_rank_rows,
    _format_result_display,
    _get_event_types_map,
    _is_lower_better,
    _is_valid_postseason_mark,
    _ordinal,
    _resolve_postseason_individual_rows,
    _resolve_school_enrollment_for_year,
    _school_logo_url,
)
from .meets import (
    _compute_cumulative_points,
    _compute_school_relay_results,
    _compute_team_scores_for_meet,
    _format_points_value,
    _resolve_postseason_relay_rows,
    _score_h2h_meet,
    _stage_cells,
)
from .qualifiers import (
    _format_school_qualifier_row,
    _advancement_from_rows,
    get_regional_qualifiers,
    get_state_qualifiers,
)
from .percentiles import (
    _get_school_percentile_years,
)

from .school_dashboard import (
    _event_groups,
    _events_for_gender,
)



def _normalize_rank_to_score(rank: Optional[int], total_marks: int) -> float:
    if rank is None or total_marks <= 0:
        return 0.0
    if total_marks == 1:
        return 100.0
    return round(((total_marks - rank) / (total_marks - 1)) * 100, 1)

@lru_cache(maxsize=32)
def _build_statewide_program_rankings(gender: str, year: int):
    events = _events_for_gender(gender)
    relay_events = set(CONST.EVENT.ALL_RELAY)
    event_group_map = {}
    for group_name, group_events in _event_groups(gender):
        for event_name in group_events:
            event_group_map[event_name] = group_name

    resolved_individual_rows = _resolve_postseason_individual_rows(gender=gender, year=year)
    sectional_entry_rows = (
        db.session.query(
            Athlete.school_id,
            Athlete.athlete_id,
            Athlete.first,
            Athlete.last,
            AthleteResult.event,
        )
        .join(AthleteResult, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Athlete.gender == gender,
            Meet.gender == gender,
            Meet.year == year,
            Meet.meet_type == CONST.MEET_TYPE.SECTIONAL,
            AthleteResult.event.in_([event_name for event_name in events if event_name not in relay_events]),
        )
        .distinct()
        .all()
    )

    sectional_entries_by_school_event: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    participating_schools = set()
    for row in sectional_entry_rows:
        participating_schools.add(row.school_id)
        sectional_entries_by_school_event.setdefault((row.school_id, row.event), [])
        athlete_name = f"{(row.first or '').strip()} {(row.last or '').strip()}".strip()
        athletes = sectional_entries_by_school_event[(row.school_id, row.event)]
        if not any(existing["athlete_id"] == row.athlete_id for existing in athletes):
            athletes.append({"athlete_id": row.athlete_id, "athlete_name": athlete_name})

    athlete_best_by_event: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for row in resolved_individual_rows:
        if not _is_valid_postseason_mark(row["result_value"], row["event_type"]):
            continue
        key = (row["athlete_id"], row["event"])
        existing = athlete_best_by_event.get(key)
        lower_is_better = _is_lower_better(row["event_type"])
        if existing is None or (
            lower_is_better and row["result_value"] < existing["result_value"]
        ) or (
            not lower_is_better and row["result_value"] > existing["result_value"]
        ):
            athlete_best_by_event[key] = dict(row)

    event_rank_lookup: Dict[Tuple[str, int], Dict[str, Any]] = {}
    event_school_rows = {}
    for event_name in [event_name for event_name in events if event_name not in relay_events]:
        lower_is_better = _is_lower_better(_get_event_types_map().get(event_name, CONST.EVENT_TYPE.TRACK))
        event_rows = [
            {
                **row,
                "result_display": row.get("result") or _format_result_display(row["result_value"], row["event_type"]),
            }
            for row in athlete_best_by_event.values()
            if row["event"] == event_name
        ]
        ranked_rows = _competition_rank_rows(event_rows, lower_is_better, value_key="result_value")
        event_school_rows[event_name] = ranked_rows
        for ranked_row in ranked_rows:
            event_rank_lookup[(event_name, ranked_row["athlete_id"])] = ranked_row

    relay_rows = _resolve_postseason_relay_rows(gender=gender, year=year)
    relay_best_by_school_event: Dict[Tuple[int, str], Dict[str, Any]] = {}
    relay_sectional_entries = (
        db.session.query(RelayResult.school_id, RelayResult.event)
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            Meet.gender == gender,
            Meet.year == year,
            Meet.meet_type == CONST.MEET_TYPE.SECTIONAL,
            RelayResult.event.in_(CONST.EVENT.ALL_RELAY),
        )
        .distinct()
        .all()
    )
    for school_id_value, event_name in relay_sectional_entries:
        participating_schools.add(school_id_value)

    for row in relay_rows:
        participating_schools.add(row["school_id"])
        if not _is_valid_postseason_mark(row["result_value"], CONST.EVENT_TYPE.TRACK):
            continue
        key = (row["school_id"], row["event"])
        existing = relay_best_by_school_event.get(key)
        if existing is None or row["result_value"] < existing["result_value"]:
            relay_best_by_school_event[key] = dict(row)

    relay_rank_lookup: Dict[Tuple[str, int], Dict[str, Any]] = {}
    relay_event_rows = {}
    for event_name in CONST.EVENT.ALL_RELAY:
        event_rows = [
            {
                **row,
                "result_display": row.get("result") or _format_result_display(row["result_value"], CONST.EVENT_TYPE.TRACK),
            }
            for row in relay_best_by_school_event.values()
            if row["event"] == event_name
        ]
        ranked_rows = _competition_rank_rows(event_rows, True, value_key="result_value")
        relay_event_rows[event_name] = ranked_rows
        for ranked_row in ranked_rows:
            relay_rank_lookup[(event_name, ranked_row["school_id"])] = ranked_row

    school_names = dict(
        db.session.query(School.school_id, School.school_name)
        .filter(School.school_id.in_(participating_schools))
        .all()
    ) if participating_schools else {}

    school_results: Dict[int, Dict[str, Any]] = {}
    for school_id_value in participating_schools:
        event_results = []
        group_accumulator: Dict[str, List[float]] = {}

        for event_name in events:
            group_name = event_group_map[event_name]
            if event_name in relay_events:
                relay_ranked = relay_rank_lookup.get((event_name, school_id_value))
                total_marks = len(relay_event_rows.get(event_name, []))
                event_score = _normalize_rank_to_score(relay_ranked.get("rank"), total_marks) if relay_ranked else 0.0
                event_payload = {
                    "event": event_name,
                    "group": group_name,
                    "event_score": event_score,
                    "total_marks": total_marks,
                    "slots": [
                        {
                            "entry_type": "relay",
                            "school_id": school_id_value,
                            "holder_name": school_names.get(school_id_value),
                            "mark": relay_ranked.get("result_display") if relay_ranked else None,
                            "statewide_rank": relay_ranked.get("rank") if relay_ranked else None,
                            "statewide_score": event_score,
                        }
                    ],
                }
            else:
                sectional_entries = sectional_entries_by_school_event.get((school_id_value, event_name), [])
                lower_is_better = _is_lower_better(_get_event_types_map().get(event_name, CONST.EVENT_TYPE.TRACK))
                sorted_entries = sorted(
                    sectional_entries,
                    key=lambda item: (
                        athlete_best_by_event.get((item["athlete_id"], event_name), {}).get(
                            "result_value",
                            float("inf") if lower_is_better else float("-inf"),
                        ),
                        item["athlete_name"],
                        item["athlete_id"],
                    ),
                    reverse=not lower_is_better,
                )[:2]
                slots = []
                total_marks = len(event_school_rows.get(event_name, []))
                for item in sorted_entries:
                    ranked_row = event_rank_lookup.get((event_name, item["athlete_id"]))
                    score = _normalize_rank_to_score(ranked_row.get("rank"), total_marks) if ranked_row else 0.0
                    slots.append(
                        {
                            "entry_type": "individual",
                            "athlete_id": item["athlete_id"],
                            "holder_name": item["athlete_name"],
                            "mark": ranked_row.get("result_display") if ranked_row else None,
                            "statewide_rank": ranked_row.get("rank") if ranked_row else None,
                            "statewide_score": score,
                        }
                    )
                while len(slots) < 2:
                    slots.append(
                        {
                            "entry_type": "individual",
                            "athlete_id": None,
                            "holder_name": None,
                            "mark": None,
                            "statewide_rank": None,
                            "statewide_score": 0.0,
                        }
                    )
                event_score = round(sum(slot["statewide_score"] for slot in slots) / 2, 1)
                event_payload = {
                    "event": event_name,
                    "group": group_name,
                    "event_score": event_score,
                    "total_marks": total_marks,
                    "slots": slots,
                }

            group_accumulator.setdefault(group_name, []).append(event_payload["event_score"])
            event_results.append(event_payload)

        composite_score = round(sum(item["event_score"] for item in event_results) / len(events), 1) if events else 0.0
        group_scores = {
            group_name: round(sum(values) / len(values), 1)
            for group_name, values in group_accumulator.items()
            if values
        }
        school_results[school_id_value] = {
            "school_id": school_id_value,
            "school_name": school_names.get(school_id_value),
            "composite_score": composite_score,
            "event_scores": event_results,
            "group_scores": group_scores,
        }

    leaderboard_rows = _competition_rank_rows(
        list(school_results.values()),
        lower_is_better=False,
        value_key="composite_score",
    )
    total_schools = len(leaderboard_rows)
    leaderboard_by_school = {row["school_id"]: row for row in leaderboard_rows}
    for row in leaderboard_rows:
        row["total_schools"] = total_schools
        row["rank_display"] = f"{_ordinal(row['rank'])} of {total_schools}" if total_schools else "—"

    return {
        "year": year,
        "gender": gender,
        "events": events,
        "group_order": [group_name for group_name, _ in _event_groups(gender)],
        "leaderboard": leaderboard_rows,
        "by_school": leaderboard_by_school,
    }

@lru_cache(maxsize=32)
def _rank_baselines(gender: str, year: int):
    """Median composite and per-group scores across every ranked school.

    A 0-100 strength score means nothing on its own -- "Relays 54.4" is only
    legible next to what a typical program scores. These medians are what the
    UI draws as a reference marker on each bar.
    """
    state = _build_statewide_program_rankings(gender, year)
    rows = list(state["by_school"].values())
    if not rows:
        return {"composite": 0.0, "groups": {}, "ranked_schools": 0}

    group_values: Dict[str, List[float]] = {}
    for row in rows:
        for group_name, score in (row.get("group_scores") or {}).items():
            group_values.setdefault(group_name, []).append(score)

    composite_sorted = sorted(row["composite_score"] for row in rows)
    count = len(composite_sorted)

    return {
        "composite": round(statistics.median(composite_sorted), 1),
        "groups": {
            group_name: round(statistics.median(values), 1)
            for group_name, values in group_values.items()
        },
        "ranked_schools": count,
        # Sorted score arrays, kept in the cached structure so standings can be
        # resolved with a bisect instead of rescanning every school per request.
        "composite_sorted": composite_sorted,
        "group_sorted": {
            group_name: sorted(values) for group_name, values in group_values.items()
        },
        # Quartiles on the SCORE axis. On a rank axis these would always land on
        # 25/50/75 and carry no information; here their bunching is what shows
        # the distribution's skew.
        "quartiles": {
            "min": round(composite_sorted[0], 1),
            "q1": round(composite_sorted[count // 4], 1),
            "median": round(statistics.median(composite_sorted), 1),
            "q3": round(composite_sorted[(3 * count) // 4], 1),
            "max": round(composite_sorted[-1], 1),
        },
    }

@lru_cache(maxsize=64)
def _group_ranks(gender: str, year: int):
    """Rank every school within each event group.

    Group *scores* are not comparable across groups -- their medians run from 24.9
    (Hurdles) to 44.1 (Throws) purely because events differ in how widely they are
    contested, which is what made "Jumps 21 vs Throws 44" misleading. Group *ranks*
    are uniform by construction, so "Jumps 90th, Throws 200th" is a fair sentence.

    A missing event still costs the group, as it should: schools with no pole
    vaulter sit about 6 percentile points worse in Jumps than in their own other
    groups. That is the vacancy showing through, not a distortion.
    """
    state = _build_statewide_program_rankings(gender, year)
    by_group: Dict[str, List[Tuple[int, float]]] = {}
    for row in state["by_school"].values():
        for group_name, score in (row.get("group_scores") or {}).items():
            by_group.setdefault(group_name, []).append((row["school_id"], score))

    ranks: Dict[Tuple[str, int], Tuple[int, int]] = {}
    for group_name, items in by_group.items():
        items.sort(key=lambda item: item[1], reverse=True)
        total = len(items)
        previous_score = None
        previous_rank = 0
        for index, (school_id, score) in enumerate(items):
            rank = previous_rank if score == previous_score else index + 1
            previous_score, previous_rank = score, rank
            ranks[(group_name, school_id)] = (rank, total)
    return ranks

def _group_standings(school_id: int, gender: str, year: int):
    """One entry per group: rank in the selected season and the events it covers.

    Only the selected season is resolved. Walking every season here to draw a trend
    meant rebuilding the statewide rankings once per season, which dominated page
    load time.

    The events list is what lets the strip act as a filter over the event table
    rather than opening a third level of drill-down.
    """
    current = _group_ranks(gender, year)
    standings = []
    for group_name, group_events in _event_groups(gender):
        here = current.get((group_name, school_id))
        standings.append(
            {
                "group": group_name,
                "events": list(group_events),
                "rank": here[0] if here else None,
                "rank_total": here[1] if here else 0,
            }
        )
    return standings

def _slots_filled(school_id: int, gender: str, year: int):
    """How many entry slots held a ranked mark, for one school in one season.

    Same basis as the figure the Entries box shows, so the two can be subtracted.
    Reads the cached statewide build directly: calling the program-rank function
    for the prior year would recurse back through every season on record.
    """
    if year < MIN_RECORDS_YEAR:
        return None
    state = _build_statewide_program_rankings(gender, year)
    school_row = state["by_school"].get(school_id)
    if not school_row:
        return None
    return sum(
        1
        for entry in school_row["event_scores"]
        for slot in entry["slots"]
        if slot.get("statewide_rank")
    )

def get_program_rank(school_id: int, gender: str, year: int):
    """Statewide standing for one program.

    Deliberately standalone rather than a wrapper around the v2 function. v2 also
    computes like-size peer standings and the average percentile of posted marks;
    v3 shows neither, and peer standings alone cost ~1.3s on a cold cache. Wrapping
    would have hidden those figures while still paying for them.

    Event groups are excluded too: 54% of schools field nobody in Pole Vault versus
    5% in the 100m, so a group *score* was never comparable across groups. The group
    strip ranks schools within each group instead, which is comparable.
    """
    state = _build_statewide_program_rankings(gender, year)
    baselines = _rank_baselines(gender, year)
    school_row = state["by_school"].get(school_id)

    info_text = (
        "Unofficial postseason comparison only, not IHSAA team scoring. Individual events use up to two "
        "sectional-entry slots per school; relays use one slot. Valid postseason marks are ranked statewide "
        "with ties sharing rank, then converted to 0-100 scores. Missing entries, DNF/DNS/DQ-style invalid "
        "marks, and empty slots score 0."
    )

    if not school_row:
        return {
            "year": year,
            "gender": gender,
            "rank": None,
            "rank_display": "Not ranked",
            "is_ranked": False,
            "percentile": None,
            "standing": None,
            "total_schools": len(state["leaderboard"]),
            "composite_score": None,
            "entry_slots": None,
            "state_median_composite": baselines["composite"],
            "score_distribution": baselines["quartiles"],
            "prior_rank": None,
            "rank_movement": None,
            "group_standings": _group_standings(school_id, gender, year),
            "info_text": info_text,
        }

    # Counted directly rather than derived from rank, so tied programs are reported
    # as tied instead of being silently folded into "behind you".
    composite_sorted = baselines["composite_sorted"]
    my_score = school_row["composite_score"]
    behind = bisect.bisect_left(composite_sorted, my_score)
    at_or_below = bisect.bisect_right(composite_sorted, my_score)
    tied = max(0, at_or_below - behind - 1)  # excludes this school itself
    ahead = max(0, len(composite_sorted) - at_or_below)
    # Percentile by rank, so the top of the field reads 100.0. "behind / total"
    # was defensible -- no school is ahead of itself, so the best possible was
    # 393/394 = 99.7% -- but it disagreed with the group gauges, which rank the
    # same school 100.0 on the same page, and 99.7 for a state champion reads as
    # a rounding error rather than a result. The exact counts stay in `standing`
    # and on the tooltip, so nothing claims to be ahead of itself.
    total_ranked = school_row["total_schools"] or len(composite_sorted)
    percentile = (
        round(100.0 * (total_ranked - school_row["rank"] + 1) / total_ranked, 1)
        if total_ranked
        else None
    )

    all_slots = [slot for entry in school_row["event_scores"] for slot in entry["slots"]]
    scoring_slots = [slot for slot in all_slots if slot.get("statewide_rank")]
    entered_slots = [slot for slot in all_slots if slot.get("holder_name")]

    # Where this program has ranked in every covered season. One arrow says
    # "up 66 from 2025"; the sequence says the program slid for two years and
    # then recovered, which is the question a coach is actually asking.
    # Every covered season's rank for this school. The statewide table for each
    # season is lru_cached, so a build pays for it once and then reads it for all
    # 414 schools -- which is why this is affordable here and was not in a
    # per-request path.
    history = []
    for season in range(MIN_RECORDS_YEAR, year + 1):
        row = _build_statewide_program_rankings(gender, season)["by_school"].get(school_id)
        if row:
            history.append({
                "season": season,
                "rank": row["rank"],
                "total_schools": row["total_schools"],
            })

    prior = None
    if year - 1 >= MIN_RECORDS_YEAR:
        prior_row = _build_statewide_program_rankings(
            gender, year - 1)["by_school"].get(school_id)
        if prior_row:
            prior = {
                "season": year - 1,
                "rank": prior_row["rank"],
                "total_schools": prior_row["total_schools"],
            }

    return {
        "year": year,
        "gender": gender,
        "rank": school_row["rank"],
        "rank_display": school_row["rank_display"],
        "is_ranked": True,
        "percentile": percentile,
        "standing": {
            "behind": behind,
            "tied": tied,
            "ahead": ahead,
            "total": school_row["total_schools"] or 0,
        },
        "total_schools": school_row["total_schools"] or 0,
        "composite_score": school_row["composite_score"],
        "entry_slots": {
            "total": len(all_slots),
            "filled": len(scoring_slots),
            "entered": len(entered_slots),
            # The same count a season earlier, so the box can say which way it
            # moved. None when there is no prior season on record, which is not
            # the same as no change.
            "prior_filled": _slots_filled(school_id, gender, year - 1),
            "prior_season": year - 1 if year - 1 >= MIN_RECORDS_YEAR else None,
        },
        "state_median_composite": baselines["composite"],
        "score_distribution": baselines["quartiles"],
        "prior_rank": prior,
        "rank_history": history,
        "rank_movement": prior["rank"] - school_row["rank"] if prior else None,
        "group_standings": _group_standings(school_id, gender, year),
        "info_text": info_text,
    }
