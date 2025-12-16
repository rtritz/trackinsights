import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

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
from .util.conversion_util import Conversion


CONVERSION = Conversion()
SPRINT_DNQ_EVENTS = {
    "100 Meters",
    "200 Meters",
    "100 Hurdles",
    "110 Hurdles",
}

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
if SCRIPTS_DIR.is_dir():
    scripts_path = str(SCRIPTS_DIR)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)

try:  # pragma: no-cover
    from percentiles import get_percentiles as _script_get_percentiles  # type: ignore
    from util.const_util import CONST  # type: ignore
except Exception as exc:  # pragma: no-cover
    _script_get_percentiles = None
    _SCRIPT_IMPORT_ERROR = exc
else:
    _SCRIPT_IMPORT_ERROR = None

DEFAULT_PERCENTILES = (25, 50, 75)
PERCENTILE_CHOICES = (10, 25, 50, 75, 90, 95)
GRADE_LEVELS = ("FR", "SO", "JR", "SR")


def _require_percentile_script():
    if _script_get_percentiles is None:
        message = (
            "The percentiles script could not be imported. "
            "See the original exception for details: "
            f"{_SCRIPT_IMPORT_ERROR!r}"
        )
        raise RuntimeError(message)


def _unique_events():
    event_groups = (
        getattr(CONST.EVENT, "ALL_TRACK", []),
        getattr(CONST.EVENT, "ALL_FIELD", []),
        getattr(CONST.EVENT, "ALL_RELAY", []),
        getattr(CONST.EVENT, "ALL_GIRLS_HURDLES", []),
        getattr(CONST.EVENT, "ALL_BOYS_HURDLES", []),
    )
    seen = set()
    output = []
    for group in event_groups:
        for name in group:
            if name not in seen:
                seen.add(name)
                output.append(name)
    return sorted(output)


@lru_cache(maxsize=1)
def _available_meet_years(limit: int = 30):
    db_path = Path(getattr(CONST, "DB_PATH", "")).expanduser()
    if not db_path.exists():
        return []

    import sqlite3

    query = "SELECT DISTINCT year FROM meet WHERE year IS NOT NULL ORDER BY year DESC LIMIT ?"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, (limit,)).fetchall()
    return [int(row[0]) for row in rows if row and row[0] is not None]


def get_percentile_options():
    _require_percentile_script()
    return {
        "events": _unique_events(),
        "genders": list(getattr(CONST.GENDER, "ALL", [])),
        "meet_types": list(getattr(CONST.MEET_TYPE, "ALL", [])),
        "grade_levels": list(GRADE_LEVELS),
        "default_percentiles": list(DEFAULT_PERCENTILES),
        "percentile_choices": list(PERCENTILE_CHOICES),
        "years": _available_meet_years(),
        "db_path": str(getattr(CONST, "DB_PATH", "")),
    }


def _coerce_sequence(values, item_cast):
    processed = []
    for raw in values:
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        processed.append(item_cast(text))
    return tuple(processed)


def _tuple_or_none(seq):
    if not seq:
        return None
    return tuple(seq)


def get_percentiles_report(
    *,
    events=None,
    genders=None,
    percentiles=None,
    years=None,
    meet_types=None,
    grade_levels=None,
):
    _require_percentile_script()

    kwargs = {
        "events": _tuple_or_none(_coerce_sequence(events or [], str)),
        "genders": _tuple_or_none(_coerce_sequence(genders or [], str)),
        "percentiles": _tuple_or_none(
            _coerce_sequence(percentiles or DEFAULT_PERCENTILES, int)
        ),
        "years": _tuple_or_none(_coerce_sequence(years or [], int)),
        "meet_types": _tuple_or_none(_coerce_sequence(meet_types or [], str)),
        "grade_levels": _tuple_or_none(
            _coerce_sequence(grade_levels or [], lambda text: text.upper())
        ),
    }

    df = _script_get_percentiles(**kwargs)
    if df is None:
        return {"columns": [], "rows": [], "filters": kwargs}

    columns = [str(column) for column in df.columns]
    raw_rows = df.to_dict(orient="records")
    rows = [{str(key): value for key, value in row.items()} for row in raw_rows]

    return {
        "columns": columns,
        "rows": rows,
        "filters": {k: v for k, v in kwargs.items() if v},
        "result_count": len(rows),
    }


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


def _compute_stage_badge(stage_name, results, placer_threshold):
    if not results:
        return None

    qualifier_count = 0
    placer_count = 0

    for res, _meet in results:
        qualifier_count += 1
        if res.place is not None and res.place > 0 and res.place <= placer_threshold:
            placer_count += 1

    payload = None
    if placer_count:
        count_prefix = f"{placer_count} x " if placer_count > 1 else ""
        payload = {
            "stage": stage_name,
            "achievement": "Placer",
            "count": placer_count,
            "label": f"{count_prefix}{stage_name} Placer",
        }
    elif qualifier_count:
        count_prefix = f"{qualifier_count} x " if qualifier_count > 1 else ""
        payload = {
            "stage": stage_name,
            "achievement": "Qualifier",
            "count": qualifier_count,
            "label": f"{count_prefix}{stage_name} Qualifier",
        }

    if not payload:
        return None

    payload["qualifier_count"] = qualifier_count
    payload["placer_count"] = placer_count
    payload["entries"] = _serialize_stage_entries(results)
    return payload


def _serialize_stage_entries(results):
    serialized = []
    for res, meet in results:
        place_value = res.place if (res.place is not None and res.place > 0) else None
        serialized.append(
            {
                "event": res.event,
                "result": res.result,
                "place": place_value,
                "place_label": _format_place_label(place_value) if place_value else None,
                "meet_id": getattr(res, "meet_id", None),
                "meet_type": meet.meet_type,
                "year": meet.year,
                "meet_host": meet.host,
                "result_type": getattr(res, "result_type", "Final"),
                "is_relay": isinstance(res, RelayResult),
            }
        )

    serialized.sort(key=lambda entry: (entry["year"] or 0, entry["event"] or ""), reverse=True)
    return serialized


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
        "has_detail": bool(meet_id and result_type),
        "is_relay": is_relay,
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


_RELAY_NAME_DELIMITER = re.compile(r"\band\b|&|/|;|,|\+", re.IGNORECASE)


def _normalize_name_text(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", value)
    return " ".join(cleaned.lower().split())


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


def _extract_relay_names(names_blob: str):
    if not names_blob:
        return []

    pieces = _RELAY_NAME_DELIMITER.split(names_blob)
    normalized = []
    for piece in pieces:
        value = _normalize_name_text(piece)
        if value:
            normalized.append(value)
    return normalized


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


def _estimate_relay_rank(
    event_name: str,
    performance_value,
    *,
    gender: str,
    year: int,
    meet_type: str = "Sectional",
    event_type: Optional[str] = None,
):
    event_type_value = event_type
    if not event_type_value:
        event = Event.query.filter_by(event=event_name).one_or_none()
        if not event or not event.event_type:
            return None
        event_type_value = event.event_type

    normalized_value = _normalize_performance_input(performance_value, event_type_value)

    gender_filter = func.lower(Meet.gender) == (gender or "").strip().lower()
    raw_results = (
        db.session.query(
            RelayResult.school_id.label("team_id"),
            RelayResult.meet_id.label("meet_id"),
            RelayResult.result2.label("result_value"),
            RelayResult.result.label("result_text"),
            RelayResult.place.label("place"),
            RelayResult.athlete_names.label("athlete_names"),
            Meet.host.label("meet_host"),
            Meet.meet_num.label("meet_num"),
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.event == event_name,
            RelayResult.result2.isnot(None),
            Meet.meet_type == meet_type,
            gender_filter,
            Meet.year == year,
        )
    ).all()

    if not raw_results:
        return None

    lower_is_better = _is_lower_better(event_type_value)
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
        team_bucket = meet_entry["results"]
        candidate = {
            "athlete_id": row.team_id,
            "result_value": row.result_value,
            "result_text": row.result_text,
            "result_type": "Final",
            "place": row.place,
        }
        team_bucket[row.team_id] = _choose_result_entry(
            team_bucket.get(row.team_id), candidate, lower_is_better
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
        raw_place = _project_place(values, normalized_value, event_type_value, event_name)
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
    raw_overall_place = _project_place(all_values_sorted, normalized_value, event_type_value, event_name)

    return {
        "event": event_name,
        "event_type": event_type_value,
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


def _is_lower_better(event_type: str) -> bool:
    return event_type != "Field"


def _choose_result_entry(existing, candidate, lower_is_better: bool):
    if existing is None:
        return candidate

    priority = {"Final": 2, "Semi": 1, "Prelim": 1}
    existing_weight = priority.get(existing.get("result_type"), 0)
    candidate_weight = priority.get(candidate.get("result_type"), 0)

    if candidate_weight > existing_weight:
        return candidate
    if candidate_weight < existing_weight:
        return existing

    if lower_is_better:
        return candidate if candidate["result_value"] < existing["result_value"] else existing
    return candidate if candidate["result_value"] > existing["result_value"] else existing


def _format_sectional_name(host, meet_num):
    if host and meet_num:
        return f"{host} (Meet {meet_num})"
    if host:
        return host
    if meet_num:
        return f"Meet {meet_num}"
    return "Unknown Sectional"


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_place_label(value):
    numeric = _safe_int(value)
    if numeric is None:
        return value
    return _ordinal(numeric)


def _count_result_types(entries):
    counts = {}
    for entry in entries:
        label = entry.get("result_type") or "Unknown"
        counts[label] = counts.get(label, 0) + 1
    return counts

