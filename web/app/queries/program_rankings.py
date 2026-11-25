"""Where a whole program sits statewide.

Named program_rankings to keep it apart from event_ranking beside it, which
ranks a single mark within a field. The two were once `rankings.py` and
`ranking.py` -- one letter apart, and imported all over the package.

The composite score and the ranking built from it. Expensive -- it reads every
result in the state -- which is why the dashboards are precomputed rather than
worked out per request.
"""

from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .. import db
from ..models import Athlete, AthleteResult, Meet, RelayResult, School

from common.const import CONST
from .shared import (
    _get_event_types_map,
    _is_lower_better,
    _is_valid_postseason_mark,
    _resolve_postseason_individual_rows,
)
from .formatting import (
    _format_result_display,
    _ordinal,
)
from .event_ranking import (
    _competition_rank_rows,
)
from .meets import (
    _resolve_postseason_relay_rows,
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

    # Ranking marks: an athlete's best from any round (a prelim counts).
    resolved_individual_rows = _resolve_postseason_individual_rows(gender=gender, year=year, best_of_rounds=True)
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

