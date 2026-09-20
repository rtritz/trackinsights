"""Where one mark stands against everyone else's.

Named event_ranking to keep it apart from program_rankings beside it, which
ranks whole programs statewide. The two were once `ranking.py` and `rankings.py`
-- one letter apart, and imported all over the package.

Two related jobs. Ranking a mark within a field -- a school, a sectional, the
whole state -- with the competition rules that govern ties, and estimating
where a hypothetical mark would have landed. Both read the same postseason
rows and both have to agree with how a meet was actually scored, so they live
together rather than beside the features that call them.

Depends on formatting for display and on shared for the row helpers; nothing
here is imported back by either.
"""
from functools import lru_cache
from typing import Any, Dict, List

from sqlalchemy import func

from .. import db
from ..models import Athlete, AthleteResult, Event, Meet
from .formatting import (
    _format_place_label,
    _format_sectional_name,
    _format_sectional_result,
    _safe_int,
)
from .shared import (
    CONVERSION,
    SPRINT_DNQ_EVENTS,
    _choose_result_entry,
    _count_result_types,
    _get_all_sectional_events_list,
    _get_event_types_map,
    _is_lower_better,
)


@lru_cache(maxsize=None)
def _get_field_size(meet_id, event, result_type):
    return (
        db.session.query(func.max(AthleteResult.place))
        .filter(
            AthleteResult.meet_id == meet_id,
            AthleteResult.event == event,
            AthleteResult.result_type == result_type,
            AthleteResult.place.isnot(None),
        )
        .scalar()
    )


def _compute_rank_for_event(event_name, event_type, athlete_id, min_year, school_id=None, gender=None):
    aggregator = func.min if _is_lower_better(event_type) else func.max

    query = (
        db.session.query(
            AthleteResult.athlete_id,
            aggregator(AthleteResult.result2).label("best_value"),
        )
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(
            AthleteResult.result2.isnot(None),
            #AthleteResult.result_type == "Final",
            Event.event == event_name,
            Event.event_type != "Relay",
            Meet.year.isnot(None),
            Meet.year >= min_year,
        )
    )

    if school_id is not None:
        query = query.filter(Athlete.school_id == school_id)

    if gender is not None:
        query = query.filter(Athlete.gender == gender)

    rows = query.group_by(AthleteResult.athlete_id).all()
    if not rows:
        return None

    lower_is_better = _is_lower_better(event_type)
    leaderboard = [
        (row.athlete_id, row.best_value)
        for row in rows
        if row.best_value is not None
    ]

    if not leaderboard:
        return None

    leaderboard.sort(key=lambda item: item[1], reverse=not lower_is_better)

    rank = None
    for index, (ath_id, _value) in enumerate(leaderboard, start=1):
        if ath_id == athlete_id:
            rank = index
            break

    if rank is None:
        return None

    return {
        "rank": rank,
        "total": len(leaderboard),
        "since_year": min_year,
    }


def _compute_cohort_ranking(entries, target_key, lower_is_better, filter_fn=None, limit=10):
    filter_fn = filter_fn or (lambda _item: True)
    filtered = [item for item in entries if filter_fn(item)]
    if not filtered:
        return None

    sorted_entries = sorted(
        filtered,
        key=lambda item: (
            item["result_value"],
            item["athlete_id"],
            item["meet_id"],
        ),
        reverse=not lower_is_better,
    )

    ranked_entries = []
    target_rank = None
    previous_value = None
    current_rank = 0

    for index, entry in enumerate(sorted_entries, start=1):
        value = entry["result_value"]
        if previous_value is None or value != previous_value:
            current_rank = index
            previous_value = value

        enriched = dict(entry)
        enriched["rank"] = current_rank
        enriched["is_target"] = (
            entry["athlete_id"] == target_key["athlete_id"]
            and entry["meet_id"] == target_key["meet_id"]
        )
        ranked_entries.append(enriched)

        if enriched["is_target"]:
            target_rank = current_rank

    if target_rank is None:
        return None

    return {
        "rank": target_rank,
        "total": len(ranked_entries),
        "top_results": _summarize_leaderboard(ranked_entries, limit=limit),
    }


def _summarize_leaderboard(entries, limit=10):
    summary = []
    seen = set()
    for entry in entries:
        key = (entry["athlete_id"], entry["meet_id"])
        if key in seen:
            continue
        seen.add(key)
        summary.append(
            {
                "athlete_id": entry["athlete_id"],
                "name": entry["full_name"],
                "school": entry["school_name"],
                "result": entry["result"],
                "result_value": entry["result_value"],
                "grade": entry["grade"],
                "rank": entry["rank"],
                "is_target": entry.get("is_target", False),
                "meet_id": entry["meet_id"],
                "meet_host": entry["meet_host"],
                "place": entry["place"],
            }
        )

    return summary


def estimate_event_rank(
    event_name: str,
    performance_value,
    *,
    gender: str,
    year: int,
    meet_type: str = "Sectional",
):
    """Project how a performance would place at every sectional in scope.

    Finals are always preferred for athletes who advanced; prelim marks are
    used for everyone else so the projection mirrors the legacy
    ``WhereDoIRank`` script.

    Both prelim and final performances are considered automatically with
    finals taking precedence when available.
    """

    event = Event.query.filter_by(event=event_name).one_or_none()
    if not event or not event.event_type:
        return None

    event_type = event.event_type
    normalized_value = _normalize_performance_input(performance_value, event_type)

    gender_filter = func.lower(Meet.gender) == (gender or "").strip().lower()
    raw_results = (
        db.session.query(
            AthleteResult.athlete_id.label("athlete_id"),
            AthleteResult.meet_id.label("meet_id"),
            AthleteResult.result2.label("result_value"),
            AthleteResult.result.label("result_text"),
            AthleteResult.result_type.label("result_type"),
            AthleteResult.place.label("place"),
            Meet.host.label("meet_host"),
            Meet.meet_num.label("meet_num"),
        )
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            AthleteResult.event == event_name,
            AthleteResult.result2.isnot(None),
            Meet.meet_type == meet_type,
            gender_filter,
            Meet.year == year,
        )
    ).all()

    if not raw_results:
        return None

    lower_is_better = _is_lower_better(event_type)
    per_meet = {}
    for row in raw_results:
        meet_entry = per_meet.setdefault(
            row.meet_id,
            {
                "meet_id": row.meet_id,
                "host": row.meet_host,
                "meet_num": row.meet_num,
                "results": {},
            },
        )
        athlete_bucket = meet_entry["results"]
        candidate = {
            "athlete_id": row.athlete_id,
            "result_value": row.result_value,
            "result_text": row.result_text,
            "result_type": row.result_type,
            "place": row.place,
        }
        athlete_bucket[row.athlete_id] = _choose_result_entry(
            athlete_bucket.get(row.athlete_id), candidate, lower_is_better
        )

    sectional_results = []
    all_result_values = []
    for meet_data in per_meet.values():
        entries = list(meet_data["results"].values())
        if not entries:
            continue
        values = sorted(
            (entry["result_value"] for entry in entries),
            reverse=not lower_is_better,
        )
        all_result_values.extend(values)
        raw_place = _project_place(values, normalized_value, event_type, event_name)
        numeric_place = _safe_int(raw_place)
        sectional_results.append(
            {
                "meet_id": meet_data["meet_id"],
                "meet_num": meet_data["meet_num"],
                "sectional_name": _format_sectional_name(meet_data["host"], meet_data["meet_num"]),
                "projected_place": numeric_place,
                "projected_place_label": _format_place_label(raw_place),
                "field_size": len(values),
                "result_type_counts": _count_result_types(entries),
            }
        )

    if not sectional_results:
        return None

    sectional_results.sort(
        key=lambda item: (
            item["meet_num"] if item.get("meet_num") is not None else float("inf"),
            item.get("sectional_name") or "",
        )
    )

    all_values_sorted = sorted(all_result_values, reverse=not lower_is_better)
    raw_overall_place = _project_place(all_values_sorted, normalized_value, event_type, event_name)

    return {
        "event": event_name,
        "event_type": event_type,
        "gender": gender,
        "year": year,
        "meet_type": meet_type,
        "comparison_count": len(all_values_sorted),
        "projected_place": raw_overall_place,
        "projected_place_label": _format_place_label(raw_overall_place),
        "input_value": normalized_value,
        "sectional_results": sectional_results,
    }


def _normalize_performance_input(value, event_type: str) -> float:
    if value is None:
        raise ValueError("performance_value is required")

    if isinstance(value, (int, float)):
        return float(value)

    if not isinstance(value, str):
        raise TypeError("performance_value must be a string or number")

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("performance_value cannot be empty")

    if _is_lower_better(event_type):
        return float(CONVERSION.time_to_seconds(cleaned))
    return float(CONVERSION.distance_to_inches(cleaned))


def _project_place(result_values, candidate_value, event_type: str, event_name: str) -> str:
    comparator = (lambda existing: existing < candidate_value) if _is_lower_better(event_type) else (
        lambda existing: existing > candidate_value
    )

    for index, existing in enumerate(result_values, start=1):
        if not comparator(existing):
            return str(index)

    if event_name in SPRINT_DNQ_EVENTS:
        return "DNQ for Finals"

    return str(len(result_values) + 1)


def _competition_rank_rows(rows: List[Dict[str, Any]], lower_is_better: bool, value_key: str = "result_value"):
    if not rows:
        return []

    default_value = float("inf") if lower_is_better else float("-inf")
    sorted_rows = sorted(
        rows,
        key=lambda item: item.get(value_key, default_value),
        reverse=not lower_is_better,
    )

    ranked = []
    last_value = object()
    current_rank = 0
    for index, row in enumerate(sorted_rows, start=1):
        value = row.get(value_key)
        if index == 1 or value != last_value:
            current_rank = index
            last_value = value
        ranked_row = dict(row)
        ranked_row["rank"] = current_rank
        ranked.append(ranked_row)
    return ranked


def _compute_all_event_difficulties_from_data(
    year_event_results: dict,
    all_events: list,
    event_types_map: dict,
    years: list,
):
    """
    Compute difficulty rankings for all events in each season using pre-fetched data.
    
    Difficulty = |Cutoff - Median| / Median * 100
    
    Returns a dict mapping year -> list of events sorted by difficulty (descending).
    
    This version uses data already fetched in a single query, avoiding N+1 queries.
    """
    difficulty_rankings = {}

    for year in years:
        event_difficulties = []

        for event_name in all_events:
            all_values = year_event_results.get(year, {}).get(event_name, [])

            if len(all_values) < 8:
                continue

            # Get event type from cached map
            event_type = event_types_map.get(event_name, "Track")
            lower_is_better = event_type != "Field"

            # Calculate median
            sorted_values = sorted(all_values, reverse=not lower_is_better)
            n = len(sorted_values)
            if n % 2 == 1:
                median = sorted_values[n // 2]
            else:
                median = (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2

            # Calculate cutoff (8th place)
            ascending_values = sorted(all_values) if lower_is_better else sorted(all_values, reverse=True)
            cutoff = ascending_values[min(7, len(ascending_values) - 1)]

            # Calculate relative difficulty
            if median and median != 0:
                difficulty = abs(cutoff - median) / abs(median) * 100
            else:
                difficulty = 0

            event_difficulties.append({
                "event": event_name,
                "difficulty": round(difficulty, 2),
                "median": _format_sectional_result(median, event_type),
                "cutoff": _format_sectional_result(cutoff, event_type),
            })

        # Sort by difficulty descending (higher difficulty = harder to qualify)
        event_difficulties.sort(key=lambda x: x["difficulty"], reverse=True)
        difficulty_rankings[year] = event_difficulties

    return difficulty_rankings


def _compute_all_event_difficulties(gender: str, years: list):
    """
    Compute difficulty rankings for all events in each season.
    
    Difficulty = |Cutoff - Median| / Median * 100
    
    Returns a dict mapping year -> list of events sorted by difficulty (descending).
    
    NOTE: This function is kept for backwards compatibility but the optimized
    version _compute_all_event_difficulties_from_data should be preferred.
    """
    all_events = _get_all_sectional_events_list(gender)
    event_types_map = _get_event_types_map()

    # Fetch all data in one query instead of per-event queries
    results_query = (
        db.session.query(
            Meet.year,
            AthleteResult.event,
            AthleteResult.result2,
        )
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Meet.meet_type == "Sectional",
            Meet.gender == gender,
            Meet.year.in_(years),
            AthleteResult.event.in_(all_events),
            AthleteResult.result_type == "Final",
            AthleteResult.result2.isnot(None),
        )
        .all()
    )

    # Group results by (year, event)
    from collections import defaultdict
    year_event_results = defaultdict(lambda: defaultdict(list))
    for year, evt, result2 in results_query:
        if year is not None and result2 is not None:
            year_event_results[year][evt].append(result2)

    return _compute_all_event_difficulties_from_data(
        year_event_results, all_events, event_types_map, years
    )
