"""Scorecard

One school's entries, round by round: the marks, the places, and
whether each entry advanced.
"""

from .shared import (  # noqa: F401  -- shared setup and constants
    Any,
    Athlete,
    AthleteResult,
    CONST,
    Dict,
    Event,
    List,
    Meet,
    RelayResult,
    Tuple,
    _STAGE_ORDER,
    db,
    lru_cache,
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

from .outlook import (
    _grades_for_season,
)



@lru_cache(maxsize=16)
def _event_ranked_rows(gender: str, year: int):
    """Every postseason mark in the state, ranked within its event, rows kept.

    Athlete rows are ranked against other athletes (roughly 669 marks in the Boys
    100m), not against school bests (375). That is the honest denominator for a
    person: a school best is a school's number, an athlete's mark is theirs.

    One best mark per athlete per event, so an athlete who ran the same event at
    sectional, regional and state appears once at their fastest.

    The ranking used to happen inside _event_mark_ranks, which
    kept only the (rank, total) pair and discarded the ranked rows. The event
    drill-down needs the rows, so the work is done once here and both callers read
    from the same result.
    """
    best: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for row in _resolve_postseason_individual_rows(gender=gender, year=year):
        if not _is_valid_postseason_mark(row["result_value"], row["event_type"]):
            continue
        key = (row["athlete_id"], row["event"])
        existing = best.get(key)
        lower_is_better = _is_lower_better(row["event_type"])
        if existing is None or (
            row["result_value"] < existing["result_value"] if lower_is_better
            else row["result_value"] > existing["result_value"]
        ):
            best[key] = row

    by_event: Dict[str, List[Dict[str, Any]]] = {}
    for row in best.values():
        by_event.setdefault(row["event"], []).append(row)

    return {
        event_name: _competition_rank_rows(rows, _is_lower_better(rows[0]["event_type"]))
        for event_name, rows in by_event.items()
    }

@lru_cache(maxsize=32)
def _event_mark_ranks(gender: str, year: int):
    """(athlete, event) -> (rank, total), off the ranked rows above."""
    ranks: Dict[Tuple[int, str], Tuple[int, int]] = {}
    for event_name, rows in _event_ranked_rows(gender, year).items():
        total = len(rows)
        for row in rows:
            ranks[(row["athlete_id"], event_name)] = (row["rank"], total)
    return ranks

@lru_cache(maxsize=16)
def _relay_ranked_rows(gender: str, year: int):
    """Relay bests ranked within their event, rows kept. One entry per school."""
    best: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for row in _resolve_postseason_relay_rows(gender=gender, year=year):
        if not _is_valid_postseason_mark(row["result_value"], CONST.EVENT_TYPE.TRACK):
            continue
        key = (row["school_id"], row["event"])
        existing = best.get(key)
        if existing is None or row["result_value"] < existing["result_value"]:
            best[key] = row

    by_event: Dict[str, List[Dict[str, Any]]] = {}
    for row in best.values():
        by_event.setdefault(row["event"], []).append(row)

    return {
        event_name: _competition_rank_rows(rows, True)
        for event_name, rows in by_event.items()
    }

@lru_cache(maxsize=32)
def _relay_mark_ranks(gender: str, year: int):
    """(school, event) -> (rank, total), off the ranked relay rows above."""
    ranks: Dict[Tuple[int, str], Tuple[int, int]] = {}
    for event_name, rows in _relay_ranked_rows(gender, year).items():
        total = len(rows)
        for row in rows:
            ranks[(row["school_id"], event_name)] = (row["rank"], total)
    return ranks

@lru_cache(maxsize=64)
def _individual_advancement(gender: str, year: int):
    """Per (athlete, event): where the season ended, and the mark needed to go on."""
    rows = []
    query = (
        db.session.query(
            AthleteResult.athlete_id,
            AthleteResult.event,
            AthleteResult.meet_id,
            AthleteResult.place,
            AthleteResult.result,
            AthleteResult.result2,
            AthleteResult.result_type,
            Meet.meet_type,
            Meet.meet_num,
            Event.event_type,
        )
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year == year,
            Meet.gender == gender,
            AthleteResult.result2.isnot(None),
        )
    )
    for row in query.all():
        rows.append({
            "athlete_id": row.athlete_id,
            "event": row.event,
            "meet_id": row.meet_id,
            "meet_type": row.meet_type,
            "meet_num": row.meet_num,
            "place": row.place,
            "result": row.result,
            "result_value": row.result2,
            "result_type": row.result_type,
            "event_type": row.event_type or CONST.EVENT_TYPE.TRACK,
        })

    next_stage_pairs = {}
    for stage in _STAGE_ORDER[1:]:
        next_stage_pairs[stage] = {
            (item["athlete_id"], item["event"])
            for item in rows if item["meet_type"] == stage
        }

    return _advancement_from_rows(
        rows,
        next_stage_pairs,
        pair_of=lambda item: (item["athlete_id"], item["event"]),
        lower_is_better_of=lambda item: _is_lower_better(item["event_type"]),
    )

@lru_cache(maxsize=64)
def _relay_advancement(gender: str, year: int):
    """The same, keyed by school and relay -- relays live in relay_result."""
    rows = []
    query = (
        db.session.query(
            RelayResult.school_id,
            RelayResult.event,
            RelayResult.meet_id,
            RelayResult.place,
            RelayResult.result,
            RelayResult.result2,
            Meet.meet_type,
            Meet.meet_num,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year == year,
            Meet.gender == gender,
            RelayResult.result2.isnot(None),
        )
    )
    for row in query.all():
        rows.append({
            "school_id": row.school_id,
            "event": row.event,
            "meet_id": row.meet_id,
            "meet_type": row.meet_type,
            "meet_num": row.meet_num,
            "place": row.place,
            "result": row.result,
            "result_value": row.result2,
            # relay_result carries no rounds; every relay row is a final
            "result_type": CONST.RESULT_TYPE.FINAL,
            "event_type": CONST.EVENT_TYPE.TRACK,
        })

    next_stage_pairs = {}
    for stage in _STAGE_ORDER[1:]:
        next_stage_pairs[stage] = {
            (item["school_id"], item["event"])
            for item in rows if item["meet_type"] == stage
        }

    return _advancement_from_rows(
        rows,
        next_stage_pairs,
        pair_of=lambda item: (item["school_id"], item["event"]),
        lower_is_better_of=lambda _item: True,
    )

def get_athlete_scorecard(school_id: int, gender: str, season):
    """One row per athlete who competed in the postseason, plus their best mark.

    Rows are per athlete rather than per event because a coach reads this to see
    their people. Events nobody entered still get a placeholder row: without one a
    gap simply vanishes from the table, and an unfilled event is the most
    actionable thing on the page.
    """
    if season == "all-time":
        year = None
    else:
        year = int(season)

    events = _events_for_gender(gender)
    event_group_map = {}
    for group_name, group_events in _event_groups(gender):
        for event_name in group_events:
            event_group_map[event_name] = group_name

    mark_ranks = _event_mark_ranks(gender, year) if year else {}
    relay_ranks = _relay_mark_ranks(gender, year) if year else {}
    grades = _grades_for_season(gender, year) if year else {}
    advancement = _individual_advancement(gender, year) if year else {}
    relay_advancement = _relay_advancement(gender, year) if year else {}

    # All-Time is a records board, not a season card: there is no statewide rank to
    # sort by, so order by the mark itself and keep the top three per event. Seven
    # undifferentiated rows in the 100 with an empty Rank column read as broken;
    # "the three fastest ever, and who ran them" is the thing this mode is for.
    records_mode = year is None
    RECORDS_PER_EVENT = 3

    # Every postseason mark, grouped by athlete and event, so each stage gets its
    # own cell rather than one "best" that silently belongs to one of three meets.
    grouped: Dict[Tuple[int, str], List[Dict[str, Any]]] = {}
    for row in _resolve_postseason_individual_rows(gender=gender, year=year, school_id=school_id):
        grouped.setdefault((row["athlete_id"], row["event"]), []).append(row)

    rows_by_event: Dict[str, List[Dict[str, Any]]] = {}
    for (athlete_id, event_name), athlete_rows in grouped.items():
        event_type = athlete_rows[0]["event_type"]
        lower_is_better = _is_lower_better(event_type)
        cells, best_stage, best_value = _stage_cells(athlete_rows, lower_is_better, event_type)
        if not cells:
            continue
        rank = mark_ranks.get((athlete_id, event_name))
        advance = advancement.get((athlete_id, event_name)) or {}
        rows_by_event.setdefault(event_name, []).append(
            {
                "event": event_name,
                "group": event_group_map.get(event_name),
                "entry_type": "individual",
                "athlete_id": athlete_id,
                "name": athlete_rows[0].get("athlete_name"),
                "grade": grades.get(athlete_id),
                "stages": cells,
                # The best of the three, kept because the statewide rank is computed
                # on it -- the cell holding it is highlighted so the rank is never a
                # figure without a visible source.
                "best_stage": best_stage,
                "mark_display": cells[best_stage]["mark_display"] if best_stage else None,
                "result_value": best_value,
                "rank": rank[0] if (rank and best_stage) else None,
                "rank_total": rank[1] if (rank and best_stage) else 0,
                "year": max(
                    (item.get("year") for item in athlete_rows if item.get("year")),
                    default=None,
                ),
                "reached_state": CONST.MEET_TYPE.STATE in cells,
                "final_stage": advance.get("final_stage"),
                "cutoff_display": advance.get("cutoff_display"),
                "cutoff_path": advance.get("cutoff_path"),
                "gap_display": advance.get("gap_display"),
                "cutoff_value": advance.get("cutoff_value"),
                "gap_value": advance.get("gap_value"),
                "qualified_did_not_compete": advance.get("qualified_did_not_compete", False),
                "tied_cutoff": advance.get("tied_cutoff", False),
            }
        )

    relay_grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in _resolve_postseason_relay_rows(gender=gender, year=year, school_id=school_id):
        relay_grouped.setdefault(row["event"], []).append(row)

    for event_name, relay_rows in relay_grouped.items():
        # On the records board a relay's unit is the season's squad, so each season
        # contributes its own best mark and the three best seasons stand as records.
        # Within a season the unit is the event itself, as for an individual.
        if records_mode:
            by_year: Dict[Any, List[Dict[str, Any]]] = {}
            for item in relay_rows:
                by_year.setdefault(item.get("year"), []).append(item)
            groups = list(by_year.values())
        else:
            groups = [relay_rows]

        for group_rows in groups:
            cells, best_stage, best_value = _stage_cells(
                group_rows, True, CONST.EVENT_TYPE.TRACK
            )
            if not cells:
                continue
            rank = relay_ranks.get((school_id, event_name))
            source = next(
                (item for item in group_rows if item.get("meet_type") == best_stage), group_rows[0]
            )
            advance = relay_advancement.get((school_id, event_name)) or {}
            rows_by_event.setdefault(event_name, []).append(
                {
                    "event": event_name,
                    "group": event_group_map.get(event_name),
                    "entry_type": "relay",
                    "athlete_id": None,
                    # The school, never the legs: relay_result.athlete_names is not
                    # being populated going forward, so a name here would be present
                    # for old seasons and blank for new ones.
                    "name": source.get("school_name"),
                    "grade": None,
                    "stages": cells,
                    "best_stage": best_stage,
                    "mark_display": cells[best_stage]["mark_display"] if best_stage else None,
                    "result_value": best_value,
                    "rank": rank[0] if (rank and best_stage) else None,
                    "rank_total": rank[1] if (rank and best_stage) else 0,
                    "year": max(
                        (item.get("year") for item in group_rows if item.get("year")), default=None
                    ),
                    "reached_state": CONST.MEET_TYPE.STATE in cells,
                    "final_stage": advance.get("final_stage"),
                    "cutoff_display": advance.get("cutoff_display"),
                    "cutoff_path": advance.get("cutoff_path"),
                    "gap_display": advance.get("gap_display"),
                    "cutoff_value": advance.get("cutoff_value"),
                    "gap_value": advance.get("gap_value"),
                    "qualified_did_not_compete": advance.get("qualified_did_not_compete", False),
                    "tied_cutoff": advance.get("tied_cutoff", False),
                }
            )


    rows = []
    for event_name in events:
        entries = rows_by_event.get(event_name)
        if entries:
            if records_mode:
                event_type = (
                    CONST.EVENT_TYPE.TRACK
                    if event_name in CONST.EVENT.ALL_RELAY
                    else db.session.query(Event.event_type)
                    .filter(Event.event == event_name)
                    .scalar()
                    or CONST.EVENT_TYPE.TRACK
                )
                lower_is_better = _is_lower_better(event_type)
                entries = [item for item in entries if item.get("result_value") is not None]
                if not entries:
                    continue
                entries.sort(
                    key=lambda item: item["result_value"], reverse=not lower_is_better
                )
                for position, entry in enumerate(entries):
                    entry["record_position"] = position + 1
                entries = entries[:RECORDS_PER_EVENT]
            else:
                entries.sort(key=lambda item: item["rank"] or 10 ** 9)
            rows.extend(entries)
        else:
            # No entry at all. Kept visible on purpose -- the gap is the point.
            rows.append(
                {
                    "event": event_name,
                    "group": event_group_map.get(event_name),
                    "entry_type": "none",
                    "athlete_id": None,
                    "name": None,
                    "mark_display": None,
                    "result_value": None,
                    "rank": None,
                    "rank_total": (
                        relay_ranks.get((school_id, event_name), (None, 0))[1]
                        if event_name in CONST.EVENT.ALL_RELAY
                        else 0
                    ),
                    "stages": {},
                    "best_stage": None,
                    "reached_state": False,
                }
            )

    # Only offer a stage column the school actually reached. A State column is dead
    # space for 58% of schools, and its presence is itself worth something.
    stages_present = [
        stage for stage in _STAGE_ORDER
        if any(stage in (row.get("stages") or {}) for row in rows)
    ]

    return {
        "gender": gender,
        "season": season,
        "mode": "records" if records_mode else "season",
        "records_per_event": RECORDS_PER_EVENT if records_mode else None,
        "stages_present": stages_present,
        "rows": rows,
    }
