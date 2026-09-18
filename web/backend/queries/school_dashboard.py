"""School Dashboard

Everything behind the school dashboards, including the
statewide program rankings the dashboard reports.
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
    REGIONAL_SECTIONAL_GROUPS,
    RelayResult,
    School,
    Tuple,
    _PLACE_POINTS,
    _V3_STAGE_ORDER,
    bisect,
    db,
    func,
    joinedload,
    lru_cache,
    re,
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
    _v4_stage_cells,
)

from .qualifiers import (
    _format_school_qualifier_row,
    _v4_advancement_from_rows,
    get_regional_qualifiers,
    get_state_qualifiers,
)

from .percentiles import (
    _get_school_percentile_years,
)



def get_school_dashboard_data(school_id: int):
    """Aggregate all data needed for the school dashboard page."""

    school = (
        School.query.options(joinedload(School.enrollments))
        .filter_by(school_id=school_id)
        .one_or_none()
    )
    if not school:
        return None

    # Basic school info
    latest_enrollment = None
    enrollment_year = None
    if school.enrollments:
        sorted_enrollments = sorted(school.enrollments, key=lambda e: e.year, reverse=True)
        latest_enrollment = sorted_enrollments[0].enrollment
        enrollment_year = sorted_enrollments[0].year

    logo_url = _school_logo_url(school)

    school_info = {
        "id": school.school_id,
        "name": school.school_name,
        "city": school.city,
        "school_type": school.school_type,
        "enrollment": latest_enrollment,
        "enrollment_year": enrollment_year,
        "logo_url": logo_url,
    }

    roster = _build_school_roster(school_id)
    cumulative_points = _compute_cumulative_points(school_id)
    percentile_years = _get_school_percentile_years(school_id)
    relay_results = _compute_school_relay_results(school_id)
    relay_years = sorted({row["year"] for row in relay_results if row.get("year") is not None}, reverse=True)

    return {
        "school": school_info,
        "roster": roster,
        "cumulative_points": cumulative_points,
        # Load percentiles asynchronously on the client so first dashboard paint is faster.
        "school_percentiles": [],
        "percentile_years": percentile_years,
        "relay_results": relay_results,
        "relay_years": relay_years,
    }

def _school_dashboard_v4_event_groups(gender: str) -> List[Tuple[str, List[str]]]:
    hurdles = (
        list(getattr(CONST.EVENT, "ALL_GIRLS_HURDLES", []))
        if gender == CONST.GENDER.GIRLS
        else list(getattr(CONST.EVENT, "ALL_BOYS_HURDLES", []))
    )
    return [
        ("Sprints", [CONST.EVENT.E100, CONST.EVENT.E200, CONST.EVENT.E400]),
        ("Distance", [CONST.EVENT.E800, CONST.EVENT.E1600, CONST.EVENT.E3200]),
        ("Hurdles", hurdles),
        ("Jumps", [CONST.EVENT.EHJ, CONST.EVENT.ELJ, CONST.EVENT.EPV]),
        ("Throws", [CONST.EVENT.ESP, CONST.EVENT.EDT]),
        ("Relays", list(getattr(CONST.EVENT, "ALL_RELAY", []))),
    ]

def _school_dashboard_v4_events_for_gender(gender: str) -> List[str]:
    events = []
    for _, group_events in _school_dashboard_v4_event_groups(gender):
        events.extend(group_events)
    return events

def _school_dashboard_v4_available_years(school_id: int, gender: str) -> List[int]:
    individual_years = (
        db.session.query(Meet.year)
        .join(AthleteResult, AthleteResult.meet_id == Meet.meet_id)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(
            Athlete.school_id == school_id,
            Athlete.gender == gender,
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .distinct()
        .all()
    )
    relay_years = (
        db.session.query(Meet.year)
        .join(RelayResult, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.school_id == school_id,
            Meet.gender == gender,
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .distinct()
        .all()
    )
    return sorted(
        {
            int(row.year)
            for row in list(individual_years) + list(relay_years)
            if getattr(row, "year", None) is not None
        },
        reverse=True,
    )

def _school_dashboard_v4_covered_years(gender: str) -> List[int]:
    """Every postseason year the database covers for this gender, ascending.

    This is the full axis the season picker draws. A school's own available
    years are a subset of it, so any year missing from that subset renders as
    a visible gap ("this program had no postseason team in 2025") instead of
    silently vanishing from the list the way a dropdown would hide it.
    """
    rows = (
        db.session.query(Meet.year)
        .filter(
            Meet.gender == gender,
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .distinct()
        .all()
    )
    return sorted({int(row.year) for row in rows if getattr(row, "year", None) is not None})

def _default_school_dashboard_v4_season(gender: str, school_years: List[int]) -> Optional[int]:
    if school_years:
        latest_school_year = max(school_years)
    else:
        latest_school_year = None

    latest_completed = (
        db.session.query(func.max(Meet.year))
        .filter(
            Meet.gender == gender,
            Meet.meet_type == CONST.MEET_TYPE.STATE,
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .scalar()
    )
    if latest_completed is None:
        return latest_school_year
    if latest_school_year is None:
        return latest_completed
    return min(latest_completed, latest_school_year)

def _get_school_dashboard_v4_scope(
    school_id: int,
    gender: Optional[str] = None,
    season: Optional[str] = None,
):
    school = (
        School.query.options(joinedload(School.enrollments))
        .filter_by(school_id=school_id)
        .one_or_none()
    )
    if not school:
        return None

    clean_gender = (gender or CONST.GENDER.BOYS).strip().title()
    if clean_gender not in CONST.GENDER.ALL:
        raise ValueError("gender must be Boys or Girls")

    available_years = _school_dashboard_v4_available_years(school_id, clean_gender)
    if not available_years and season not in (None, "", "all-time"):
        raise ValueError("season must be All-Time or a covered postseason year for this school")

    if season in (None, ""):
        selected_season = _default_school_dashboard_v4_season(clean_gender, available_years)
    elif str(season).strip().lower() == "all-time":
        selected_season = "all-time"
    else:
        try:
            selected_season = int(season)
        except (TypeError, ValueError) as exc:
            raise ValueError("season must be All-Time or a numeric postseason year") from exc
        if selected_season not in available_years:
            raise ValueError("season must be one of the school's covered postseason years or All-Time")

    if selected_season is None:
        selected_season = "all-time"

    return school, clean_gender, selected_season, available_years

def _normalize_rank_to_score(rank: Optional[int], total_marks: int) -> float:
    if rank is None or total_marks <= 0:
        return 0.0
    if total_marks == 1:
        return 100.0
    return round(((total_marks - rank) / (total_marks - 1)) * 100, 1)

def get_school_dashboard_v4_stage_summary(school_id: int, gender: str, year: int):
    stage_order = {CONST.MEET_TYPE.SECTIONAL: 1, CONST.MEET_TYPE.REGIONAL: 2, CONST.MEET_TYPE.STATE: 3}
    scoring_cutoffs = {
        CONST.MEET_TYPE.SECTIONAL: 8,
        CONST.MEET_TYPE.REGIONAL: 8,
        CONST.MEET_TYPE.STATE: 9,
    }
    summary = {
        meet_type: {
            "stage": meet_type,
            "attended": False,
            "entries": 0,
            "scoring_finishes": 0,
            "points": None,
            "points_display": "—",
            "team_rank": None,
            "team_rank_display": "—",
            "total_teams": None,
        }
        for meet_type in CONST.MEET_TYPE.ALL
    }

    individual_rows = (
        db.session.query(
            AthleteResult.meet_id,
            AthleteResult.event,
            AthleteResult.place,
            AthleteResult.result_type,
            Athlete.athlete_id,
            Meet.meet_type,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Athlete.school_id == school_id,
            Athlete.gender == gender,
            Meet.gender == gender,
            Meet.year == year,
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
        )
        .all()
    )
    relay_rows = (
        db.session.query(
            RelayResult.meet_id,
            RelayResult.event,
            RelayResult.place,
            Meet.meet_type,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.school_id == school_id,
            Meet.gender == gender,
            Meet.year == year,
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
        )
        .all()
    )

    meet_ids_by_stage: Dict[str, set] = {meet_type: set() for meet_type in CONST.MEET_TYPE.ALL}
    stage_entries: Dict[str, set] = {meet_type: set() for meet_type in CONST.MEET_TYPE.ALL}
    stage_scores: Dict[str, set] = {meet_type: set() for meet_type in CONST.MEET_TYPE.ALL}

    for row in individual_rows:
        key = ("individual", row.athlete_id, row.event)
        stage_entries[row.meet_type].add(key)
        meet_ids_by_stage[row.meet_type].add(row.meet_id)
        scoring_cutoff = scoring_cutoffs.get(row.meet_type, 8)
        if (
            row.result_type == CONST.RESULT_TYPE.FINAL
            and row.place is not None
            and 0 < row.place <= scoring_cutoff
        ):
            stage_scores[row.meet_type].add(key)

    for row in relay_rows:
        key = ("relay", row.event)
        stage_entries[row.meet_type].add(key)
        meet_ids_by_stage[row.meet_type].add(row.meet_id)
        scoring_cutoff = scoring_cutoffs.get(row.meet_type, 8)
        if row.place is not None and 0 < row.place <= scoring_cutoff:
            stage_scores[row.meet_type].add(key)

    for meet_type in CONST.MEET_TYPE.ALL:
        entry = summary[meet_type]
        entry["attended"] = bool(stage_entries[meet_type])
        entry["entries"] = len(stage_entries[meet_type])
        entry["scoring_finishes"] = len(stage_scores[meet_type])
        if not entry["attended"]:
            continue

        meet_id = sorted(meet_ids_by_stage[meet_type])[0] if meet_ids_by_stage[meet_type] else None
        team_scores = _compute_team_scores_for_meet(meet_id) if meet_id else {}
        team_stats = team_scores.get(school_id)
        entry["points"] = team_stats.get("points", 0) if team_stats else 0
        entry["points_display"] = _format_points_value(entry["points"]) or "0"
        entry["team_rank"] = team_stats.get("rank") if team_stats else None
        entry["total_teams"] = team_stats.get("total_teams") if team_stats else None
        entry["team_rank_display"] = (
            f"{_ordinal(entry['team_rank'])} of {entry['total_teams']}"
            if entry["team_rank"] and entry["total_teams"]
            else "—"
        )

    return {
        "year": year,
        "gender": gender,
        "stages": [summary[meet_type] for meet_type in sorted(summary.keys(), key=lambda item: stage_order[item])],
    }

@lru_cache(maxsize=32)
def _build_statewide_program_rankings(gender: str, year: int):
    events = _school_dashboard_v4_events_for_gender(gender)
    relay_events = set(CONST.EVENT.ALL_RELAY)
    event_group_map = {}
    for group_name, group_events in _school_dashboard_v4_event_groups(gender):
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
        "group_order": [group_name for group_name, _ in _school_dashboard_v4_event_groups(gender)],
        "leaderboard": leaderboard_rows,
        "by_school": leaderboard_by_school,
    }

@lru_cache(maxsize=32)
def _school_dashboard_v4_rank_baselines(gender: str, year: int):
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

# Keyed on gender alone, so there are exactly two possible return values -- yet
# this was recomputed for every school, because its caller is keyed on
# (school, gender, season). It scans every postseason row for the gender across
# every season (~20k reduced keys, ~640ms), which made it the single largest
# cost on the v3 page: more than half the query time for a school nobody had
# visited yet. maxsize=8 leaves room for a third gender value without evicting.
@lru_cache(maxsize=8)
def _build_school_best_history(gender: str):
    individual_rows = _resolve_postseason_individual_rows(gender=gender)
    history: Dict[Tuple[int, str, int], Dict[str, Any]] = {}
    for row in individual_rows:
        if not _is_valid_postseason_mark(row["result_value"], row["event_type"]):
            continue
        key = (row["school_id"], row["event"], row["year"])
        enriched = {
            **row,
            "result_display": row.get("result") or _format_result_display(row["result_value"], row["event_type"]),
        }
        existing = history.get(key)
        lower_is_better = _is_lower_better(row["event_type"])
        if existing is None or (
            lower_is_better and enriched["result_value"] < existing["result_value"]
        ) or (
            not lower_is_better and enriched["result_value"] > existing["result_value"]
        ):
            history[key] = enriched

    for row in _resolve_postseason_relay_rows(gender=gender):
        if not _is_valid_postseason_mark(row["result_value"], CONST.EVENT_TYPE.TRACK):
            continue
        key = (row["school_id"], row["event"], row["year"])
        enriched = {
            **row,
            "result_display": row.get("result") or _format_result_display(row["result_value"], CONST.EVENT_TYPE.TRACK),
        }
        existing = history.get(key)
        if existing is None or enriched["result_value"] < existing["result_value"]:
            history[key] = enriched
    return history

@lru_cache(maxsize=128)
def get_school_dashboard_v4_qualifiers(school_id: int, gender: str, year: int):
    if year < MIN_RECORDS_YEAR:
        return {
            "year": year,
            "gender": gender,
            "available": False,
            "regional": None,
            "state": None,
        }

    regional_stage = {
        "stage": CONST.MEET_TYPE.REGIONAL,
        "individual": [],
        "relay": [],
        "regional_num": None,
        "status": "empty",
        "empty_text": "No regional qualifiers for this school in the selected postseason season.",
    }
    for regional_num in sorted(REGIONAL_SECTIONAL_GROUPS.keys()):
        payload = get_regional_qualifiers(gender=gender, regional_num=regional_num, year=year)
        stage_rows = []
        for event_block in payload.get("events", []):
            for row in event_block.get("qualifiers", []):
                if row.get("is_placeholder") or row.get("school_id") != school_id:
                    continue
                stage_rows.append(_format_school_qualifier_row(row, CONST.MEET_TYPE.SECTIONAL, event_block.get("event")))
        if stage_rows:
            regional_stage["regional_num"] = regional_num
            regional_stage["status"] = payload.get("context", {}).get("status", "ready")
            for entry in stage_rows:
                target = regional_stage["relay"] if entry["event"] in CONST.EVENT.ALL_RELAY else regional_stage["individual"]
                target.append(entry)
            break

    state_payload = get_state_qualifiers(gender=gender, year=year)
    state_stage = {
        "stage": CONST.MEET_TYPE.STATE,
        "individual": [],
        "relay": [],
        "status": state_payload.get("context", {}).get("status", "pending"),
        "empty_text": "No state qualifiers for this school in the selected postseason season.",
    }
    for event_block in state_payload.get("events", []):
        for row in event_block.get("qualifiers", []):
            if row.get("is_placeholder") or row.get("school_id") != school_id:
                continue
            entry = _format_school_qualifier_row(row, CONST.MEET_TYPE.REGIONAL, event_block.get("event"))
            target = state_stage["relay"] if entry["event"] in CONST.EVENT.ALL_RELAY else state_stage["individual"]
            target.append(entry)

    return {
        "year": year,
        "gender": gender,
        "available": True,
        "regional": regional_stage,
        "state": state_stage,
    }

# The v4 precompute calls this once per school per season, so the cache earns
# its keep across a build rather than within one request. Callers treat the
# payload as read-only, so a shared instance is safe to hand out.
@lru_cache(maxsize=2048)
def get_school_dashboard_v4_core(school_id: int, gender: Optional[str] = None, season: Optional[str] = None):
    scope = _get_school_dashboard_v4_scope(school_id, gender=gender, season=season)
    if not scope:
        return None

    school, clean_gender, selected_season, available_years = scope
    selected_year = None if selected_season == "all-time" else int(selected_season)
    enrollment_meta = _resolve_school_enrollment_for_year(school, selected_year)
    return {
        "school": {
            "id": school.school_id,
            "name": school.school_name,
            "city": school.city,
            "school_type": school.school_type,
            "logo_url": _school_logo_url(school),
            "enrollment": enrollment_meta["value"],
            "enrollment_source_year": enrollment_meta["source_year"],
            "enrollment_is_exact": enrollment_meta["is_exact"],
        },
        "filters": {
            "selected_gender": clean_gender,
            "selected_season": selected_season,
            "default_season": _default_school_dashboard_v4_season(clean_gender, available_years),
            "genders": list(CONST.GENDER.ALL),
            "covered_seasons": _school_dashboard_v4_covered_years(clean_gender),
            "seasons": available_years + (["all-time"] if available_years else ["all-time"]),
            "season_labels": {**{str(year_value): str(year_value) for year_value in available_years}, "all-time": "All-Time"},
        },
        "stage_results": None if selected_year is None else get_school_dashboard_v4_stage_summary(school_id, clean_gender, selected_year),
        "all_time_intro": (
            "All-Time mode shows covered postseason program bests only. Stage cards and qualifier lists are hidden because combining advancement stages across seasons is misleading."
            if selected_year is None
            else None
        ),
    }

@lru_cache(maxsize=64)
def _school_dashboard_v4_grades(gender: str, year: int):
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
def _school_dashboard_v4_season_entries(
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
def get_school_dashboard_v4_season_h2h(school_id: int, gender: str, year):
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
    available = _school_dashboard_v4_available_years(school_id, gender)
    prior_years = sorted((item for item in available if item < current_year), reverse=True)
    if not prior_years:
        return {
            "available": False,
            "seasons": [],
            "reason": "No earlier season on record for this program.",
        }

    # Both seasons on the sectional, so neither is scored on more attempts than
    # the other simply because it advanced further.
    current_entries = _school_dashboard_v4_season_entries(
        school_id, gender, current_year, sectional_only=True)
    seasons = []
    for prior_year in prior_years[:1]:
        prior_entries = _school_dashboard_v4_season_entries(
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

def _school_dashboard_v4_returning_points(school_id: int, gender: str, year: int):
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
    grades = _school_dashboard_v4_grades(gender, year)

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

def get_school_dashboard_v4_returning(school_id: int, gender: str, year):
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
    grades = _school_dashboard_v4_grades(gender, current_year)
    # The points below are sectional-only, so the roster they are attributed to is
    # chosen on the same stage. Picking slots from all-rounds bests would count
    # athletes the points figure never saw.
    entries = _school_dashboard_v4_season_entries(
        school_id, gender, current_year, sectional_only=True)
    if not entries:
        return {"available": False, "reason": "No valid postseason marks in this season."}

    # Individual slots only. A relay leg is not attributable to an athlete in
    # this data (see _school_dashboard_v4_returning_points), so a relay cannot
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
    points = _school_dashboard_v4_returning_points(school_id, gender, current_year)

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

@lru_cache(maxsize=64)
def _school_dashboard_v4_group_ranks(gender: str, year: int):
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

def _school_dashboard_v4_group_standings(school_id: int, gender: str, year: int):
    """One entry per group: rank in the selected season and the events it covers.

    Only the selected season is resolved. Walking every season here to draw a trend
    meant rebuilding the statewide rankings once per season, which dominated page
    load time.

    The events list is what lets the strip act as a filter over the event table
    rather than opening a third level of drill-down.
    """
    current = _school_dashboard_v4_group_ranks(gender, year)
    standings = []
    for group_name, group_events in _school_dashboard_v4_event_groups(gender):
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

def _school_dashboard_v4_slots_filled(school_id: int, gender: str, year: int):
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

def get_school_dashboard_v4_program_rank(school_id: int, gender: str, year: int):
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
    baselines = _school_dashboard_v4_rank_baselines(gender, year)
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
            "group_standings": _school_dashboard_v4_group_standings(school_id, gender, year),
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
            "prior_filled": _school_dashboard_v4_slots_filled(school_id, gender, year - 1),
            "prior_season": year - 1 if year - 1 >= MIN_RECORDS_YEAR else None,
        },
        "state_median_composite": baselines["composite"],
        "score_distribution": baselines["quartiles"],
        "prior_rank": prior,
        "rank_history": history,
        "rank_movement": prior["rank"] - school_row["rank"] if prior else None,
        "group_standings": _school_dashboard_v4_group_standings(school_id, gender, year),
        "info_text": info_text,
    }

@lru_cache(maxsize=16)
def _school_dashboard_v4_event_ranked_rows(gender: str, year: int):
    """Every postseason mark in the state, ranked within its event, rows kept.

    Athlete rows are ranked against other athletes (roughly 669 marks in the Boys
    100m), not against school bests (375). That is the honest denominator for a
    person: a school best is a school's number, an athlete's mark is theirs.

    One best mark per athlete per event, so an athlete who ran the same event at
    sectional, regional and state appears once at their fastest.

    The ranking used to happen inside _school_dashboard_v4_event_mark_ranks, which
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
def _school_dashboard_v4_event_mark_ranks(gender: str, year: int):
    """(athlete, event) -> (rank, total), off the ranked rows above."""
    ranks: Dict[Tuple[int, str], Tuple[int, int]] = {}
    for event_name, rows in _school_dashboard_v4_event_ranked_rows(gender, year).items():
        total = len(rows)
        for row in rows:
            ranks[(row["athlete_id"], event_name)] = (row["rank"], total)
    return ranks

@lru_cache(maxsize=16)
def _school_dashboard_v4_relay_ranked_rows(gender: str, year: int):
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
def _school_dashboard_v4_relay_mark_ranks(gender: str, year: int):
    """(school, event) -> (rank, total), off the ranked relay rows above."""
    ranks: Dict[Tuple[int, str], Tuple[int, int]] = {}
    for event_name, rows in _school_dashboard_v4_relay_ranked_rows(gender, year).items():
        total = len(rows)
        for row in rows:
            ranks[(row["school_id"], event_name)] = (row["rank"], total)
    return ranks

@lru_cache(maxsize=64)
def _school_dashboard_v4_advancement(gender: str, year: int):
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
    for stage in _V3_STAGE_ORDER[1:]:
        next_stage_pairs[stage] = {
            (item["athlete_id"], item["event"])
            for item in rows if item["meet_type"] == stage
        }

    return _v4_advancement_from_rows(
        rows,
        next_stage_pairs,
        pair_of=lambda item: (item["athlete_id"], item["event"]),
        lower_is_better_of=lambda item: _is_lower_better(item["event_type"]),
    )

@lru_cache(maxsize=64)
def _school_dashboard_v4_relay_advancement(gender: str, year: int):
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
    for stage in _V3_STAGE_ORDER[1:]:
        next_stage_pairs[stage] = {
            (item["school_id"], item["event"])
            for item in rows if item["meet_type"] == stage
        }

    return _v4_advancement_from_rows(
        rows,
        next_stage_pairs,
        pair_of=lambda item: (item["school_id"], item["event"]),
        lower_is_better_of=lambda _item: True,
    )

def get_school_dashboard_v4_athlete_scorecard(school_id: int, gender: str, season):
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

    events = _school_dashboard_v4_events_for_gender(gender)
    event_group_map = {}
    for group_name, group_events in _school_dashboard_v4_event_groups(gender):
        for event_name in group_events:
            event_group_map[event_name] = group_name

    mark_ranks = _school_dashboard_v4_event_mark_ranks(gender, year) if year else {}
    relay_ranks = _school_dashboard_v4_relay_mark_ranks(gender, year) if year else {}
    grades = _school_dashboard_v4_grades(gender, year) if year else {}
    advancement = _school_dashboard_v4_advancement(gender, year) if year else {}
    relay_advancement = _school_dashboard_v4_relay_advancement(gender, year) if year else {}

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
        cells, best_stage, best_value = _v4_stage_cells(athlete_rows, lower_is_better, event_type)
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
            cells, best_stage, best_value = _v4_stage_cells(
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
        stage for stage in _V3_STAGE_ORDER
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
