"""Athletes

Athlete dashboards, their result rankings and badges.
"""

from .shared import (  # noqa: F401  -- shared setup and constants
    Athlete,
    AthleteResult,
    Conversion,
    Event,
    Meet,
    Optional,
    RelayResult,
    School,
    SchoolEnrollment,
    and_,
    db,
    func,
    joinedload,
)

from .shared import (
    _is_lower_better,
    _school_logo_url,
    _select_best_result_entry,
    _select_preferred_result,
)
from .ranking import (
    _compute_cohort_ranking,
    _compute_rank_for_event,
    _get_field_size,
    _normalize_performance_input,
    estimate_event_rank,
)
from .search_scoring import (
    _normalize_name_text,
)

from .meets import (
    _compute_stage_badge,
    _estimate_relay_rank,
    _extract_relay_names,
    _format_stage_result,
    _serialize_history_stage,
)

from .percentiles import (
    _format_percentile,
)



def get_athletes(limit=100):
    return Athlete.query.limit(limit).all()

def get_athlete_by_id(aid):
    return Athlete.query.get(aid)

def add_athlete(first_name, last_name, school=None, gender=None, graduation_year=None):
    """Create a new athlete.

    The ``school`` argument can be either a ``School`` instance or a school name.
    When a string is provided the school will be looked up (or created) before
    associating it with the new athlete.
    """

    school_obj = None
    if isinstance(school, School):
        school_obj = school
    elif isinstance(school, str) and school.strip():
        school_obj = School.query.filter_by(school_name=school.strip()).first()
        if not school_obj:
            school_obj = School(school_name=school.strip())
            db.session.add(school_obj)
            db.session.flush()

    athlete = Athlete(
        first=first_name,
        last=last_name,
        school=school_obj,
        gender=gender,
        graduation_year=graduation_year,
    )
    db.session.add(athlete)
    db.session.commit()
    return athlete

def get_athlete_dashboard_data(athlete_id: int):
    """Aggregate the data needed to power the athlete dashboard."""

    athlete = (
        Athlete.query.options(joinedload(Athlete.school))
        .filter_by(athlete_id=athlete_id)
        .one_or_none()
    )
    if not athlete:
        return None

    badges = _compute_badges(athlete_id)
    playoff_history = _build_playoff_history(athlete_id)
    personal_bests = get_athlete_personal_bests(athlete_id, athlete_obj=athlete)

    school_logo_url = _school_logo_url(athlete.school) if athlete.school else None

    return {
        "athlete": {
            "id": athlete.athlete_id,
            "first": athlete.first,
            "last": athlete.last,
            "full_name": f"{athlete.first} {athlete.last}".strip(),
            "school": athlete.school.school_name if athlete.school else None,
            "school_id": athlete.school.school_id if athlete.school else None,
            "gender": athlete.gender,
            "graduation_year": athlete.graduation_year,
            "logo_url": school_logo_url,
        },
        "badges": badges,
        "playoff_history": playoff_history,
        "personal_bests": personal_bests,
    }

def _compute_badges(athlete_id: int):
    stage_results = (
        db.session.query(AthleteResult, Meet)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            AthleteResult.athlete_id == athlete_id,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
            AthleteResult.result_type == "Final",
            Event.event_type != "Relay",
        )
        .all()
    )

    relay_rows = _fetch_relay_rows_for_athlete(
        athlete_id,
        meet_types={"Sectional", "Regional", "State"},
    )
    for relay_result, meet, _event in relay_rows:
        stage_results.append((relay_result, meet))

    sectional = [item for item in stage_results if item[1].meet_type == "Sectional"]
    regional = [item for item in stage_results if item[1].meet_type == "Regional"]
    state = [item for item in stage_results if item[1].meet_type == "State"]

    podium_threshold = 3
    return {
        "sectional": _compute_stage_badge("Sectional", sectional, placer_threshold=podium_threshold),
        "regional": _compute_stage_badge("Regional", regional, placer_threshold=podium_threshold),
        "state": _compute_stage_badge("State", state, placer_threshold=podium_threshold),
    }

def _compute_sectional_badge(results):
    if not results:
        return None

    best_percentile = None

    for res, _meet in results:
        if res.place is None or res.place <= 0:
            continue

        field_size = _get_field_size(res.meet_id, res.event, getattr(res, "result_type", "Final"))
        if not field_size:
            continue

        percentile = (res.place / field_size) * 100
        best_percentile = percentile if best_percentile is None else min(best_percentile, percentile)

    if best_percentile is None:
        return None

    return {
        "stage": "Sectional",
        "best_percentile": best_percentile,
        "label": f"Top {_format_percentile(best_percentile)}% Sectional",
    }

def _build_playoff_history(athlete_id: int):
    results = (
        db.session.query(AthleteResult, Meet)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            AthleteResult.athlete_id == athlete_id,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
            AthleteResult.result_type.in_(("Final", "Prelim")),
            Event.event_type != "Relay",
        )
        .all()
    )

    relay_rows = _fetch_relay_rows_for_athlete(
        athlete_id,
        meet_types={"Sectional", "Regional", "State"},
    )
    for relay_result, meet, _event in relay_rows:
        results.append((relay_result, meet))

    if not results:
        return []

    history = {}

    for res, meet in results:
        key = (meet.year, res.event)
        entry = history.setdefault(
            key,
            {
                "year": meet.year,
                "event": res.event,
                "Sectional": None,
                "Regional": None,
                "State": None,
            },
        )

        candidate = {
            "result": res.result,
            "place": res.place,
            "result_type": getattr(res, "result_type", "Final"),
            "formatted": _format_stage_result(res.result, res.place),
            "meet_id": getattr(res, "meet_id", None),
            "result_value": getattr(res, "result2", None),
            "grade": getattr(res, "grade", None),
            "event": res.event,
            "source": res.__class__.__name__,
        }
        entry[meet.meet_type] = _select_preferred_result(entry[meet.meet_type], candidate)

    history_rows = []
    for values in history.values():
        history_rows.append(
            {
                "year": values["year"],
                "event": values["event"],
                "sectional": _serialize_history_stage(values["Sectional"], "Sectional", values["event"]),
                "regional": _serialize_history_stage(values["Regional"], "Regional", values["event"]),
                "state": _serialize_history_stage(values["State"], "State", values["event"]),
            }
        )

    history_rows.sort(key=lambda row: (-row["year"], row["event"]))
    return history_rows

def get_athlete_personal_bests(athlete_id: int, min_year: int = 2022, athlete_obj=None):
    """Return personal-best results for each individual event the athlete has contested."""

    athlete = athlete_obj
    if athlete is None:
        athlete = (
            Athlete.query.options(joinedload(Athlete.school))
            .filter_by(athlete_id=athlete_id)
            .one_or_none()
        )

    if not athlete:
        return []

    results = (
        db.session.query(AthleteResult, Meet, Event)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            AthleteResult.athlete_id == athlete_id,
            #AthleteResult.result_type == "Final",
            AthleteResult.result2.isnot(None),
            Event.event_type != "Relay",
            Meet.year.isnot(None),
            Meet.year >= min_year,
        )
        .all()
    )

    grouped = {}
    for result, meet, event in results:
        bucket = grouped.setdefault(
            event.event,
            {
                "event_type": event.event_type,
                "items": [],
            },
        )
        bucket["items"].append((result, meet))

    relay_entries = _fetch_relay_rows_for_athlete(
        athlete_id,
        min_year=min_year,
    )

    for relay_result, meet, event in relay_entries:
        if meet.year is None or (min_year is not None and meet.year < min_year):
            continue
        bucket = grouped.setdefault(
            event.event,
            {
                "event_type": event.event_type,
                "items": [],
            },
        )
        bucket["items"].append((relay_result, meet))

    if not grouped:
        return []

    personal_bests = []
    for event_name, data in grouped.items():
        selection = _select_best_result_entry(data["items"], data["event_type"])
        if not selection:
            continue

        best_result, best_meet = selection
        school_rank = None
        state_rank = None

        if data["event_type"] != "Relay":
            if athlete.school_id is not None:
                school_rank = _compute_rank_for_event(
                    event_name,
                    data["event_type"],
                    athlete.athlete_id,
                    min_year,
                    school_id=athlete.school_id,
                    gender=athlete.gender,
                )

            state_rank = _compute_rank_for_event(
                event_name,
                data["event_type"],
                athlete.athlete_id,
                min_year,
                gender=athlete.gender,
                school_id=None,
            )

        personal_bests.append(
            {
                "event": event_name,
                "event_type": data["event_type"],
                "result": best_result.result,
                "result_value": best_result.result2,
                "meet_type": best_meet.meet_type,
                "year": best_meet.year,
                "meet_id": best_meet.meet_id,
                "result_type": getattr(best_result, "result_type", "Final"),
                "school_rank": school_rank,
                "state_rank": state_rank,
            }
        )

    personal_bests.sort(key=lambda entry: entry["event"])
    return personal_bests

def get_athlete_result_rankings(athlete_id: int, meet_id: int, event_name: str, result_type: str = "Final"):
    """Return ranking breakdown for a specific athlete result across multiple cohorts."""

    base_row = (
        db.session.query(AthleteResult, Athlete, Meet, Event, School)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .outerjoin(School, Athlete.school_id == School.school_id)
        .filter(
            AthleteResult.athlete_id == athlete_id,
            AthleteResult.meet_id == meet_id,
            AthleteResult.event == event_name,
            AthleteResult.result_type == result_type,
        )
        .one_or_none()
    )

    if not base_row:
        event_model = Event.query.filter_by(event=event_name).one_or_none()
        if event_model and event_model.event_type == "Relay":
            return _get_relay_result_rankings(athlete_id, meet_id, event_name, result_type)
        return None

    athlete_result, athlete, meet, event, school = base_row

    if athlete_result.result2 is None or meet.year is None or not meet.meet_type or not meet.gender:
        return None

    year = meet.year
    gender = meet.gender
    meet_type = meet.meet_type
    event_type = event.event_type
    result_grade = athlete_result.grade
    year_key = year

    enrollment_value = None
    if athlete.school_id is not None and year_key is not None:
        enrollment_record = (
            SchoolEnrollment.query.filter_by(
                school_id=athlete.school_id,
                year=year_key,
            ).one_or_none()
        )
        if enrollment_record:
            enrollment_value = enrollment_record.enrollment

    rows = (
        db.session.query(
            AthleteResult.athlete_id.label("athlete_id"),
            AthleteResult.meet_id.label("meet_id"),
            AthleteResult.result_type.label("result_type"),
            AthleteResult.result.label("result"),
            AthleteResult.result2.label("result_value"),
            AthleteResult.grade.label("grade"),
            AthleteResult.place.label("place"),
            Athlete.first.label("first"),
            Athlete.last.label("last"),
            Athlete.school_id.label("school_id"),
            School.school_name.label("school_name"),
            SchoolEnrollment.enrollment.label("enrollment"),
            Meet.host.label("meet_host"),
            Meet.meet_num.label("meet_num"),
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .outerjoin(School, Athlete.school_id == School.school_id)
        .outerjoin(
            SchoolEnrollment,
            and_(
                SchoolEnrollment.school_id == Athlete.school_id,
                SchoolEnrollment.year == year_key,
            ),
        )
        .filter(
            AthleteResult.event == event_name,
            AthleteResult.result_type.in_(("Final", "Prelim")),
            AthleteResult.result2.isnot(None),
            Meet.year == year,
            Meet.meet_type == meet_type,
            Meet.gender == gender,
        )
        .all()
    )

    # Resolve each athlete+meet to one mark using Final first, then Prelim fallback.
    resolved_rows = {}
    for row in rows:
        key = (row.athlete_id, row.meet_id)
        existing = resolved_rows.get(key)
        if existing is None:
            resolved_rows[key] = row
            continue

        if existing.result_type != "Final" and row.result_type == "Final":
            resolved_rows[key] = row

    entries = []
    for row in resolved_rows.values():
        if row.result_value is None:
            continue
        full_name = " ".join(filter(None, [row.first, row.last])).strip()
        entries.append(
            {
                "athlete_id": row.athlete_id,
                "meet_id": row.meet_id,
                "result": row.result,
                "result_value": row.result_value,
                "grade": row.grade,
                "place": row.place,
                "full_name": full_name,
                "school_id": row.school_id,
                "school_name": row.school_name,
                "enrollment": row.enrollment,
                "meet_host": row.meet_host,
                "meet_num": row.meet_num,
            }
        )

    if not entries:
        return None

    target_key = {"athlete_id": athlete_id, "meet_id": meet_id}
    lower_is_better = _is_lower_better(event_type)

    overall_info = _compute_cohort_ranking(entries, target_key, lower_is_better)

    like_info = None
    if enrollment_value is not None:
        lower_bound = int(round(enrollment_value * 0.75))
        upper_bound = int(round(enrollment_value * 1.25))

        like_info = _compute_cohort_ranking(
            entries,
            target_key,
            lower_is_better,
            filter_fn=lambda item: item["enrollment"] is not None
            and lower_bound <= item["enrollment"] <= upper_bound,
        )

        if like_info:
            like_info["criteria"] = {
                "enrollment": enrollment_value,
                "min_enrollment": lower_bound,
                "max_enrollment": upper_bound,
            }

    grade_info = None
    if result_grade:
        grade_info = _compute_cohort_ranking(
            entries,
            target_key,
            lower_is_better,
            filter_fn=lambda item: item["grade"] == result_grade,
        )
        if grade_info:
            grade_info["criteria"] = {"grade": result_grade}

    where_do_i_rank = None
    performance_input = athlete_result.result or athlete_result.result2
    if performance_input:
        try:
            where_do_i_rank = estimate_event_rank(
                event_name=event_name,
                performance_value=performance_input,
                gender=gender,
                year=year,
                meet_type=meet_type,
            )
        except Exception:  # pragma: no-cover - defensive guard
            where_do_i_rank = None

    return {
        "context": {
            "year": year,
            "gender": gender,
            "event": event_name,
            "meet_type": meet_type,
            "result_type": result_type,
            "event_type": event_type,
        },
        "target_result": {
            "athlete_id": athlete.athlete_id,
            "athlete_name": " ".join(filter(None, [athlete.first, athlete.last])).strip(),
            "result": athlete_result.result,
            "result_value": athlete_result.result2,
            "grade": athlete_result.grade,
            "school_id": athlete.school_id,
            "school_name": school.school_name if school else None,
            "enrollment": enrollment_value,
            "place": athlete_result.place,
            "meet_id": meet.meet_id,
            "meet_host": meet.host,
            "meet_num": meet.meet_num,
            "year": year,
        },
        "rankings": {
            "overall": overall_info,
            "like_schools": like_info,
            "same_grade": grade_info,
        },
        "where_do_i_rank": where_do_i_rank,
    }

def _get_relay_result_rankings(athlete_id: int, meet_id: int, event_name: str, result_type: Optional[str]):
    athlete = (
        Athlete.query.options(joinedload(Athlete.school))
        .filter_by(athlete_id=athlete_id)
        .one_or_none()
    )
    if not athlete or athlete.school_id is None:
        return None

    relay_payload = (
        db.session.query(RelayResult, Meet, School, Event)
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .outerjoin(School, RelayResult.school_id == School.school_id)
        .join(Event, RelayResult.event == Event.event)
        .filter(
            RelayResult.school_id == athlete.school_id,
            RelayResult.meet_id == meet_id,
            RelayResult.event == event_name,
        )
        .one_or_none()
    )
    if not relay_payload:
        return None

    relay_result, meet, school, event_model = relay_payload

    if relay_result.result2 is None or meet.year is None or not meet.meet_type or not meet.gender:
        return None

    year = meet.year
    gender = meet.gender
    meet_type = meet.meet_type
    event_type = event_model.event_type or "Relay"
    school_obj = school or athlete.school

    enrollment_value = None
    if year is not None:
        enrollment_record = (
            SchoolEnrollment.query.filter_by(
                school_id=athlete.school_id,
                year=year,
            ).one_or_none()
        )
        if enrollment_record:
            enrollment_value = enrollment_record.enrollment

    rows = (
        db.session.query(
            RelayResult.school_id.label("team_id"),
            RelayResult.meet_id.label("meet_id"),
            RelayResult.result.label("result"),
            RelayResult.result2.label("result_value"),
            RelayResult.place.label("place"),
            RelayResult.athlete_names.label("athlete_names"),
            School.school_name.label("school_name"),
            SchoolEnrollment.enrollment.label("enrollment"),
            Meet.host.label("meet_host"),
            Meet.meet_num.label("meet_num"),
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .outerjoin(School, RelayResult.school_id == School.school_id)
        .outerjoin(
            SchoolEnrollment,
            and_(
                SchoolEnrollment.school_id == RelayResult.school_id,
                SchoolEnrollment.year == year,
            ),
        )
        .filter(
            RelayResult.event == event_name,
            Meet.year == year,
            Meet.meet_type == meet_type,
            Meet.gender == gender,
            RelayResult.result2.isnot(None),
        )
        .all()
    )

    entries = []
    for row in rows:
        if row.result_value is None:
            continue
        display_name = row.athlete_names or row.school_name or "Relay Team"
        entries.append(
            {
                "athlete_id": row.team_id,
                "meet_id": row.meet_id,
                "result": row.result,
                "result_value": row.result_value,
                "grade": None,
                "place": row.place,
                "full_name": display_name,
                "school_id": row.team_id,
                "school_name": row.school_name,
                "enrollment": row.enrollment,
                "meet_host": row.meet_host,
                "meet_num": row.meet_num,
            }
        )

    if not entries:
        return None

    target_key = {"athlete_id": athlete.school_id, "meet_id": meet_id}
    lower_is_better = _is_lower_better(event_type)

    overall_info = _compute_cohort_ranking(entries, target_key, lower_is_better)
    if not overall_info:
        return None

    like_info = None
    if enrollment_value is not None:
        lower_bound = int(round(enrollment_value * 0.75))
        upper_bound = int(round(enrollment_value * 1.25))
        like_info = _compute_cohort_ranking(
            entries,
            target_key,
            lower_is_better,
            filter_fn=lambda item: item["enrollment"] is not None
            and lower_bound <= item["enrollment"] <= upper_bound,
        )

        if like_info:
            like_info["criteria"] = {
                "enrollment": enrollment_value,
                "min_enrollment": lower_bound,
                "max_enrollment": upper_bound,
            }

    performance_input = relay_result.result2 if relay_result.result2 is not None else relay_result.result
    where_do_i_rank = None
    if performance_input is not None:
        try:
            where_do_i_rank = _estimate_relay_rank(
                event_name=event_name,
                performance_value=performance_input,
                gender=gender,
                year=year,
                meet_type=meet_type,
                event_type=event_type,
            )
        except Exception:
            where_do_i_rank = None

    return {
        "context": {
            "year": year,
            "gender": gender,
            "event": event_name,
            "meet_type": meet_type,
            "result_type": result_type or "Final",
            "event_type": event_type or "Relay",
        },
        "target_result": {
            "athlete_id": athlete.athlete_id,
            "athlete_name": relay_result.athlete_names
            or (school_obj.school_name if school_obj else None),
            "result": relay_result.result,
            "result_value": relay_result.result2,
            "grade": None,
            "school_id": athlete.school_id,
            "school_name": school_obj.school_name if school_obj else None,
            "enrollment": enrollment_value,
            "place": relay_result.place,
            "meet_id": meet.meet_id,
            "meet_host": meet.host,
            "meet_num": meet.meet_num,
            "year": year,
            "relay_team": relay_result.athlete_names,
        },
        "rankings": {
            "overall": overall_info,
            "like_schools": like_info,
            "same_grade": None,
        },
        "where_do_i_rank": where_do_i_rank,
    }

def _fetch_relay_rows_for_athlete(athlete_id, meet_types=None, min_year=None):
    if athlete_id is None:
        return []

    athlete = Athlete.query.filter_by(athlete_id=athlete_id).one_or_none()
    if not athlete:
        return []

    normalized_name = _normalize_name_text(f"{athlete.first or ''} {athlete.last or ''}")
    if not normalized_name:
        return []

    query = (
        db.session.query(RelayResult, Meet, Event)
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .join(Event, RelayResult.event == Event.event)
    )

    if athlete.school_id is not None:
        query = query.filter(RelayResult.school_id == athlete.school_id)

    if athlete.gender:
        query = query.filter(Meet.gender == athlete.gender)

    if meet_types:
        query = query.filter(Meet.meet_type.in_(tuple(meet_types)))

    if min_year is not None:
        query = query.filter(Meet.year.isnot(None), Meet.year >= min_year)

    last_name = (athlete.last or "").strip().lower()
    if last_name:
        query = query.filter(func.lower(RelayResult.athlete_names).like(f"%{last_name}%"))

    matched_rows = []
    for relay_result, meet, event in query.all():
        names_blob = relay_result.athlete_names or ""
        if _relay_entry_includes_athlete(names_blob, normalized_name):
            matched_rows.append((relay_result, meet, event))

    return matched_rows

def _relay_entry_includes_athlete(names_blob: str, normalized_target: str) -> bool:
    if not names_blob or not normalized_target:
        return False

    target_tokens = normalized_target.split()
    if not target_tokens:
        return False

    for candidate in _extract_relay_names(names_blob):
        if not candidate:
            continue
        candidate_tokens = candidate.split()
        if all(token in candidate_tokens for token in target_tokens):
            return True
    return False

def get_hypothetical_result_rankings(
    event_name: str,
    performance_input: str,
    gender: str,
    year: int,
    meet_type: str = "Sectional",
    enrollment: Optional[int] = None,
    grade_level: Optional[str] = None,
):
    """Build ranking data for a hypothetical performance, similar to get_athlete_result_rankings."""

    event = Event.query.filter_by(event=event_name).one_or_none()
    if not event or not event.event_type:
        return None

    event_type = event.event_type

    # A pure-alpha token (e.g. "DNF", "NT") isn't a real performance to rank
    # against -- Conversion maps these to a sentinel value (9999s / 0in)
    # rather than raising, so reject them here explicitly instead of
    # nonsensically ranking the user's hypothetical entry against "9999
    # seconds" or "0 inches".
    if isinstance(performance_input, str) and performance_input.strip().isalpha():
        return None

    try:
        normalized_value = _normalize_performance_input(performance_input, event_type)
    except (ValueError, TypeError):
        return None

    lower_is_better = _is_lower_better(event_type)
    gender_filter = func.lower(Meet.gender) == (gender or "").strip().lower()

    # Format the display string for the input performance
    display_result = str(performance_input).strip()

    # Fetch all results for this event/year/meet_type/gender
    rows = (
        db.session.query(
            AthleteResult.athlete_id.label("athlete_id"),
            AthleteResult.meet_id.label("meet_id"),
            AthleteResult.result.label("result"),
            AthleteResult.result2.label("result_value"),
            AthleteResult.grade.label("grade"),
            AthleteResult.place.label("place"),
            Athlete.first.label("first"),
            Athlete.last.label("last"),
            Athlete.school_id.label("school_id"),
            School.school_name.label("school_name"),
            SchoolEnrollment.enrollment.label("enrollment"),
            Meet.host.label("meet_host"),
            Meet.meet_num.label("meet_num"),
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .outerjoin(School, Athlete.school_id == School.school_id)
        .outerjoin(
            SchoolEnrollment,
            and_(
                SchoolEnrollment.school_id == Athlete.school_id,
                SchoolEnrollment.year == year,
            ),
        )
        .filter(
            AthleteResult.event == event_name,
            AthleteResult.result2.isnot(None),
            Meet.year == year,
            Meet.meet_type == meet_type,
            gender_filter,
        )
        .all()
    )

    # Build entries list including the hypothetical athlete
    HYPOTHETICAL_ID = -1
    HYPOTHETICAL_MEET_ID = -1

    entries = [
        {
            "athlete_id": HYPOTHETICAL_ID,
            "meet_id": HYPOTHETICAL_MEET_ID,
            "result": display_result,
            "result_value": normalized_value,
            "grade": grade_level,
            "place": None,
            "full_name": "Your Athlete",
            "school_id": None,
            "school_name": None,
            "enrollment": enrollment,
            "meet_host": None,
            "meet_num": None,
        }
    ]

    for row in rows:
        if row.result_value is None:
            continue
        full_name = " ".join(filter(None, [row.first, row.last])).strip()
        entries.append(
            {
                "athlete_id": row.athlete_id,
                "meet_id": row.meet_id,
                "result": row.result,
                "result_value": row.result_value,
                "grade": row.grade,
                "place": row.place,
                "full_name": full_name,
                "school_id": row.school_id,
                "school_name": row.school_name,
                "enrollment": row.enrollment,
                "meet_host": row.meet_host,
                "meet_num": row.meet_num,
            }
        )

    if len(entries) < 2:
        return None

    target_key = {"athlete_id": HYPOTHETICAL_ID, "meet_id": HYPOTHETICAL_MEET_ID}

    overall_info = _compute_cohort_ranking(entries, target_key, lower_is_better)

    like_info = None
    if enrollment is not None:
        lower_bound = int(round(enrollment * 0.75))
        upper_bound = int(round(enrollment * 1.25))

        like_info = _compute_cohort_ranking(
            entries,
            target_key,
            lower_is_better,
            filter_fn=lambda item: item["enrollment"] is not None
            and lower_bound <= item["enrollment"] <= upper_bound,
        )
        if like_info:
            like_info["criteria"] = {
                "enrollment": enrollment,
                "min_enrollment": lower_bound,
                "max_enrollment": upper_bound,
            }

    grade_info = None
    if grade_level:
        grade_info = _compute_cohort_ranking(
            entries,
            target_key,
            lower_is_better,
            filter_fn=lambda item: item["grade"] == grade_level,
        )
        if grade_info:
            grade_info["criteria"] = {"grade": grade_level}

    # Sectional projections
    where_do_i_rank = None
    try:
        where_do_i_rank = estimate_event_rank(
            event_name=event_name,
            performance_value=performance_input,
            gender=gender,
            year=year,
            meet_type=meet_type,
        )
    except Exception:
        where_do_i_rank = None

    return {
        "context": {
            "year": year,
            "gender": gender,
            "event": event_name,
            "meet_type": meet_type,
            "result_type": "Final",
            "event_type": event_type,
        },
        "target_result": {
            "athlete_id": HYPOTHETICAL_ID,
            "athlete_name": "Your Athlete",
            "result": display_result,
            "result_value": normalized_value,
            "grade": grade_level,
            "school_id": None,
            "school_name": None,
            "enrollment": enrollment,
            "place": None,
            "meet_id": HYPOTHETICAL_MEET_ID,
            "meet_host": None,
            "meet_num": None,
            "year": year,
        },
        "rankings": {
            "overall": overall_info,
            "like_schools": like_info,
            "same_grade": grade_info,
        },
        "where_do_i_rank": where_do_i_rank,
    }
