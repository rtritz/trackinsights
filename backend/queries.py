from functools import lru_cache

from sqlalchemy import or_, func, and_
from sqlalchemy.orm import joinedload

from .models import (
    Athlete,
    School,
    AthleteResult,
    RelayResult,
    Meet,
    Event,
    SchoolEnrollment,
)
from . import db


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

def search_bar(query_text: str):
    """
    Search for schools and athletes matching the query.
    Returns a list of dicts with results sorted by a scoring algorithm:
    - +2 for exact word matches (bonus)
    - +1 for prefix matches
    - -999 for mismatches
    - Score divided by length of item
    - Position bonus for matches at start
    - Schools prioritized in ties
    """
    q = (query_text or "").strip().lower()
    if not q:
        return []
    
    query_words = q.split()
    
    # Build SQL filters for performance - only fetch potential matches
    # Use OR to get all records that match ANY query word
    school_filters = [School.school_name.ilike(f"%{word}%") for word in query_words]

    # Get filtered schools (all that match - no limit)
    schools_query = (
        db.session.query(School.school_id, School.school_name)
        .filter(or_(*school_filters))
    ) if school_filters else None
    schools = schools_query.all() if schools_query is not None else []
    
    # Build athlete filters - athlete matches ANY word in first, last, or school name
    athlete_filters = []
    for word in query_words:
        like_pattern = f"%{word}%"
        athlete_filters.extend([
            Athlete.first.ilike(like_pattern),
            Athlete.last.ilike(like_pattern),
            School.school_name.ilike(like_pattern),
        ])

    # Get filtered athletes (all that match - no limit)
    if athlete_filters:
        athletes_query = (
            db.session.query(
                Athlete.athlete_id,
                Athlete.first,
                Athlete.last,
                Athlete.gender,
                Athlete.graduation_year,
                School.school_name.label("school_name"),
            )
            .join(School, Athlete.school_id == School.school_id, isouter=True)
            .filter(or_(*athlete_filters))
        )
        athletes = athletes_query.all()
    else:
        athletes = []
    
    results = []
    
    # Score schools
    for school_id, school_name in schools:
        score = _calculate_score(school_name, query_words)
        if score > -20:  # Only include if at least one match
            results.append({
                "type": "school",
                "id": school_id,
                "name": school_name,
                "score": score,
                "priority": 1  # Schools have higher priority
            })
    
    # Score athletes
    for athlete in athletes:
        athlete_id = athlete.athlete_id
        athlete_name = f"{athlete.first} {athlete.last}".strip()
        school_name = getattr(athlete, "school_name", "") or ""
        
        # Calculate combined score: check if query words match across name + school
        score = _calculate_combined_score(athlete_name, school_name, query_words)
        
        if score > -20:  # Only include if at least one match
            results.append({
                "type": "athlete",
                "id": athlete_id,
                "name": athlete_name,
                "school": school_name or None,
                "gender": athlete.gender,
                "graduation_year": athlete.graduation_year,
                "classYear": athlete.graduation_year,
                "score": score,
                "priority": 2  # Athletes have lower priority
            })
    
    # Sort by priority first (schools before athletes), then by score
    results.sort(key=lambda x: (x["priority"], -x["score"]))
    
    # Remove score and priority from final results
    for r in results:
        del r["score"]
        del r["priority"]
    
    return results[:20]  # Limit to top 20 results


def _calculate_score(text: str, query_words: list) -> float:
    """
    Calculate score for a text based on query words.
    Algorithm:
    - +2 for each exact word match (bonus for exact match)
    - +1 for word that starts with query word (prefix match)
    - +0.5 bonus for matches at the beginning of text (position bonus)
    - -999 for each query word that doesn't match
    - Final score divided by length of text
    """

    #remove schools from search results
    return -999

    text_lower = text.lower()
    text_words = text_lower.split()
    
    if not text_words:
        return -999
    
    score = 0
    for query_word in query_words:
        matched = False
        # Check for exact match or prefix match
        for idx, text_word in enumerate(text_words):
            if text_word == query_word:
                score += 2  # Exact match gets bonus
                # Position bonus: first word gets extra boost
                if idx == 0:
                    score += 0.5
                matched = True
                break
            elif text_word.startswith(query_word):
                score += 1  # Prefix match gets standard score
                # Position bonus: first word gets extra boost
                if idx == 0:
                    score += 0.5
                matched = True
                break
        
        if not matched:
            score -= 999
    
    # Divide by length of text (use length of words to normalize)
    text_length = len(text_words)
    return score / text_length


def _calculate_combined_score(name: str, school: str, query_words: list) -> float:
    """
    Calculate score for an athlete by checking if query words match across name and school.
    Allows queries like "owen park" to match "Owen Zhang" from "Park Tudor".
    
    Algorithm:
    - Check each query word against both name and school
    - +3 for exact match in name (with position bonus)
    - +2 for exact match in name
    - +1 for exact match in school
    - Prefix matches worth less
    - -999 if query word matches neither
    - Heavily favor all-name matches over name+school matches
    """
    name_lower = name.lower()
    school_lower = school.lower()
    name_words = name_lower.split()
    school_words = school_lower.split()
    
    if not name_words and not school_words:
        return -999
    
    score = 0
    name_matches = 0
    school_matches = 0
    
    for query_word in query_words:
        matched_in_name = False
        matched_in_school = False
        
        # Check name first (higher priority)
        for idx, name_word in enumerate(name_words):
            if name_word == query_word:
                score += 3 if idx == 0 else 2  # Bonus for first position
                matched_in_name = True
                name_matches += 1
                break
            elif name_word.startswith(query_word):
                score += 1.5 if idx == 0 else 1
                matched_in_name = True
                name_matches += 1
                break
        
        # If not matched in name, check school
        if not matched_in_name:
            for school_word in school_words:
                if school_word == query_word:
                    score += 1  # School matches worth less
                    matched_in_school = True
                    school_matches += 1
                    break
                elif school_word.startswith(query_word):
                    score += 0.5
                    matched_in_school = True
                    school_matches += 1
                    break
        
        if not matched_in_name and not matched_in_school:
            score -= 999
    
    # Bonus: if ALL query words matched in name, add big bonus
    if name_matches == len(query_words):
        score += 5  # Big bonus for complete name match
    
    # Normalize by number of query words (not total text length)
    # This keeps scores comparable regardless of school name length
    return score / len(query_words)


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

    return {
        "athlete": {
            "id": athlete.athlete_id,
            "first": athlete.first,
            "last": athlete.last,
            "full_name": f"{athlete.first} {athlete.last}".strip(),
            "school": athlete.school.school_name if athlete.school else None,
            "gender": athlete.gender,
            "graduation_year": athlete.graduation_year,
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

    return {
        "sectional": _compute_stage_badge("Sectional", sectional, placer_threshold=8),
        "regional": _compute_stage_badge("Regional", regional, placer_threshold=8),
        "state": _compute_stage_badge("State", state, placer_threshold=9),
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


def _compute_stage_badge(stage_name, results, placer_threshold):
    if not results:
        return None

    qualifier_count = 0
    placer_count = 0

    for res, _meet in results:
        qualifier_count += 1
        if res.place is not None and res.place > 0 and res.place <= placer_threshold:
            placer_count += 1

    if placer_count:
        count_prefix = f"{placer_count} x " if placer_count > 1 else ""
        return {
            "stage": stage_name,
            "achievement": "Placer",
            "count": placer_count,
            "label": f"{count_prefix}{stage_name} Placer",
        }

    if qualifier_count:
        count_prefix = f"{qualifier_count} x " if qualifier_count > 1 else ""
        return {
            "stage": stage_name,
            "achievement": "Qualifier",
            "count": qualifier_count,
            "label": f"{count_prefix}{stage_name} Qualifier",
        }

    return None


def _build_playoff_history(athlete_id: int):
    results = (
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


def _serialize_history_stage(stage_entry, meet_type, event_name):
    if not stage_entry:
        return None

    is_relay = stage_entry.get("source") == "RelayResult"
    meet_id = stage_entry.get("meet_id")
    result_type = stage_entry.get("result_type")

    return {
        "text": stage_entry.get("formatted") or "–",
        "result": stage_entry.get("result"),
        "result_value": stage_entry.get("result_value"),
        "place": stage_entry.get("place"),
        "result_type": result_type,
        "meet_id": meet_id,
        "event": event_name,
        "meet_type": meet_type,
        "has_detail": bool(meet_id and not is_relay and result_type),
    }


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
            AthleteResult.result_type == result_type,
            AthleteResult.result2.isnot(None),
            Meet.year == year,
            Meet.meet_type == meet_type,
            Meet.gender == gender,
        )
        .all()
    )

    entries = []
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
    }


def _fetch_relay_rows_for_athlete(athlete_id, meet_types=None, min_year=None):
    if athlete_id is None:
        return []

    # The production Track.db dataset does not provide a reliable
    # athlete-to-relay mapping, so skip relay aggregation when the
    # necessary columns are unavailable.
    return []


def _select_preferred_result(existing, candidate):
    if existing is None:
        return candidate

    result_type_order = {"Final": 2, "Prelim": 1}
    existing_weight = result_type_order.get(existing.get("result_type"), 0)
    candidate_weight = result_type_order.get(candidate.get("result_type"), 0)

    if candidate_weight > existing_weight:
        return candidate
    if candidate_weight < existing_weight:
        return existing

    existing_place = existing.get("place")
    candidate_place = candidate.get("place")

    if candidate_place is not None and candidate_place > 0:
        if existing_place is None or candidate_place < existing_place:
            return candidate

    return existing


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


def _format_percentile(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def _format_stage_result(result_value, place):
    if place is None or place <= 0:
        return result_value or "–"

    place_str = _ordinal(place)
    if result_value:
        return f"{result_value} ({place_str})"
    return place_str


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _select_best_result_entry(items, event_type):
    if not items:
        return None

    valid = [item for item in items if item[0].result2 is not None]
    if not valid:
        return None

    lower_is_better = _is_lower_better(event_type)
    key_func = lambda pair: pair[0].result2
    return min(valid, key=key_func) if lower_is_better else max(valid, key=key_func)


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
    trimmed = entries[:limit]
    target_entry = next((entry for entry in entries if entry.get("is_target")), None)
    if target_entry and target_entry not in trimmed:
        trimmed = trimmed + [target_entry]

    summary = []
    seen = set()
    for entry in trimmed:
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


def _is_lower_better(event_type: str) -> bool:
    return event_type != "Field"

