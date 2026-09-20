"""Insights

The smaller insight tools: sectional trends and hypothetical
result rankings.
"""

from .. import db
from ..models import AthleteResult, Meet

from common.const import CONST

from .shared import (
    _get_all_sectional_events_list,
    _get_event_types_map,
    _get_sectional_events,
    _get_sectional_years,
)
from .formatting import (
    _format_sectional_result,
)
from .event_ranking import (
    _compute_all_event_difficulties_from_data,
)



def get_sectional_event_trends_options():
    """Return filter options for the sectional event trends page."""
    all_events = _get_sectional_events()

    return {
        "events": sorted(all_events),
        "genders": list(CONST.GENDER.ALL),
        "years": _get_sectional_years(),
    }

def get_sectional_event_trends(gender: str, event: str):
    """
    Compute sectional event trends for a given gender and event.
    
    Returns data for each season including:
    - Median mark
    - Cutoff performance (top 8 qualifier threshold)
    - Difficulty rank among all events for that season
    - All events ranked by difficulty for tooltip
    """
    if not gender or not event:
        return {"error": "Gender and event are required", "rows": [], "difficulty_rankings": {}}

    # Pre-fetch all event types in one query (cached)
    event_types_map = _get_event_types_map()
    event_type = event_types_map.get(event, "Track")
    lower_is_better = event_type != "Field"

    # Get all events we need to analyze for difficulty rankings
    all_events = _get_all_sectional_events_list(gender)

    # OPTIMIZATION: Fetch ALL results for ALL events in ONE query
    # This eliminates the N+1 query problem that was causing slowness
    # Include athlete_id to group by athlete and get best time per athlete
    results_query = (
        db.session.query(
            Meet.year,
            AthleteResult.event,
            AthleteResult.athlete_id,
            AthleteResult.result2,
        )
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Meet.meet_type == "Sectional",
            Meet.gender == gender,
            AthleteResult.event.in_(all_events),
            AthleteResult.result2.isnot(None),
        )
        .all()
    )

    # Group results by (year, event, athlete_id) and keep best result per athlete
    # For track events (lower is better), keep minimum; for field events (higher is better), keep maximum
    from collections import defaultdict
    year_event_athlete_results = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for year, evt, athlete_id, result2 in results_query:
        if year is not None and result2 is not None and athlete_id is not None:
            year_event_athlete_results[year][evt][athlete_id].append(result2)
    
    # Now compute best time per athlete for each (year, event)
    year_event_results = defaultdict(lambda: defaultdict(list))
    for year in year_event_athlete_results:
        for evt in year_event_athlete_results[year]:
            evt_type = event_types_map.get(evt, "Track")
            evt_lower_is_better = evt_type != "Field"
            for athlete_id in year_event_athlete_results[year][evt]:
                athlete_results = year_event_athlete_results[year][evt][athlete_id]
                # Get best result for this athlete (min for track, max for field)
                best_result = min(athlete_results) if evt_lower_is_better else max(athlete_results)
                year_event_results[year][evt].append(best_result)

    # Build rows for the requested event
    rows = []
    available_years = []
    for year in sorted(year_event_results.keys()):
        all_values = year_event_results[year].get(event, [])
        if not all_values:
            continue

        available_years.append(year)

        # Calculate median
        sorted_values = sorted(all_values, reverse=not lower_is_better)
        n = len(sorted_values)
        if n % 2 == 1:
            median = sorted_values[n // 2]
        else:
            median = (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2

        # Calculate cutoff (8th place qualifier threshold)
        ascending_values = sorted(all_values) if lower_is_better else sorted(all_values, reverse=True)
        cutoff_index = min(7, len(ascending_values) - 1)
        cutoff = ascending_values[cutoff_index] if ascending_values else None

        # Format the values
        median_formatted = _format_sectional_result(median, event_type)
        cutoff_formatted = _format_sectional_result(cutoff, event_type) if cutoff else None

        rows.append({
            "season": year,
            "median_mark": median_formatted,
            "median_raw": median,
            "cutoff_performance": cutoff_formatted,
            "cutoff_raw": cutoff,
            "event_type": event_type,
        })

    # Calculate difficulty rankings using the already-fetched data
    difficulty_rankings = _compute_all_event_difficulties_from_data(
        year_event_results, all_events, event_types_map, available_years
    )

    # Add difficulty rank to each row
    for row in rows:
        season = row["season"]
        if season in difficulty_rankings:
            rankings = difficulty_rankings[season]
            for rank, item in enumerate(rankings, 1):
                if item["event"] == event:
                    row["difficulty_rank"] = rank
                    row["total_events"] = len(rankings)
                    break

    return {
        "gender": gender,
        "event": event,
        "event_type": event_type,
        "rows": rows,
        "difficulty_rankings": difficulty_rankings,
    }

def get_hypothetical_ranking_options():
    """Return filter options for the hypothetical athlete query page."""
    all_events = _get_sectional_events()
    genders = list(CONST.GENDER.ALL)
    meet_types = list(CONST.MEET_TYPE.ALL)

    return {
        "events": sorted(all_events),
        "genders": genders,
        "meet_types": meet_types if meet_types else ["Sectional"],
        "years": _get_sectional_years(),
    }
