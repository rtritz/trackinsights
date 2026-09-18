"""School Dashboard

The school dashboards themselves: the page payload, the
round-by-round summary and the qualifier lists.
"""

from .shared import (  # noqa: F401  -- shared setup and constants
    Any,
    Athlete,
    AthleteResult,
    CONST,
    Dict,
    List,
    MIN_RECORDS_YEAR,
    Meet,
    Optional,
    REGIONAL_SECTIONAL_GROUPS,
    RelayResult,
    School,
    Tuple,
    db,
    func,
    joinedload,
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
