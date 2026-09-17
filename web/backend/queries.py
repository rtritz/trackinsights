import os
import json
import re
import sys
import bisect
import logging
import math
import statistics
# Set up module-level logger
logger = logging.getLogger("trackinsights.queries")
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('[%(levelname)s] %(asctime)s %(name)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
import html as html_lib
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from sqlalchemy import or_, func, and_, text as sqlalchemy_text
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
from common.conversion import Conversion
from common.regional_hosts import get_configured_regional_hosts
from common.standards import meets_state_standard, get_state_standard_display
from common.const import CONST
from .analytics.percentiles import get_percentiles as _script_get_percentiles


CONVERSION = Conversion()
SPRINT_DNQ_EVENTS = {
    "100 Meters",
    "200 Meters",
    "100 Hurdles",
    "110 Hurdles",
}

DEFAULT_PERCENTILES = (25, 50, 75)
PERCENTILE_CHOICES = (10, 25, 50, 75, 90, 95)
GRADE_LEVELS = ("FR", "SO", "JR", "SR")


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


# -----------------------------------------------------------------------------
# Sectional Event Trends
# -----------------------------------------------------------------------------

# Fallback constants in case CONST is not available
_FALLBACK_EVENTS = {
    "ALL_TRACK": ["100 Meters", "200 Meters", "400 Meters", "800 Meters", "1600 Meters", "3200 Meters"],
    "ALL_FIELD": ["High Jump", "Long Jump", "Pole Vault", "Shot Put", "Discus"],
    "ALL_GIRLS_HURDLES": ["100 Hurdles", "300 Hurdles"],
    "ALL_BOYS_HURDLES": ["110 Hurdles", "300 Hurdles"],
}
_FALLBACK_GENDERS = ["Boys", "Girls"]


def _get_sectional_events():
    """Get all events for sectional trends, with fallback if CONST not available."""
    all_events = []
    try:
        groups = [
            getattr(CONST.EVENT, "ALL_TRACK", _FALLBACK_EVENTS["ALL_TRACK"]),
            getattr(CONST.EVENT, "ALL_FIELD", _FALLBACK_EVENTS["ALL_FIELD"]),
            getattr(CONST.EVENT, "ALL_GIRLS_HURDLES", _FALLBACK_EVENTS["ALL_GIRLS_HURDLES"]),
            getattr(CONST.EVENT, "ALL_BOYS_HURDLES", _FALLBACK_EVENTS["ALL_BOYS_HURDLES"]),
        ]
    except NameError:
        groups = list(_FALLBACK_EVENTS.values())
    
    for group in groups:
        for name in group:
            if name not in all_events:
                all_events.append(name)
    return all_events


def _get_sectional_years():
    """Get available years from the database for sectional trends."""
    years_query = (
        db.session.query(Meet.year)
        .filter(Meet.meet_type == "Sectional", Meet.year.isnot(None))
        .distinct()
        .order_by(Meet.year.desc())
        .limit(10)
        .all()
    )
    return [row[0] for row in years_query if row[0] is not None]


def get_sectional_event_trends_options():
    """Return filter options for the sectional event trends page."""
    all_events = _get_sectional_events()
    
    try:
        genders = list(getattr(CONST.GENDER, "ALL", _FALLBACK_GENDERS))
    except NameError:
        genders = _FALLBACK_GENDERS
    
    return {
        "events": sorted(all_events),
        "genders": genders,
        "years": _get_sectional_years(),
    }


@lru_cache(maxsize=32)
def _get_event_types_map():
    """Fetch all event types in a single query and cache the result."""
    events = Event.query.all()
    return {e.event: (e.event_type or "Track") for e in events}


def _get_all_sectional_events_list(gender: str):
    """Get the list of events to analyze for a given gender."""
    all_events = []
    try:
        track_events = getattr(CONST.EVENT, "ALL_TRACK", _FALLBACK_EVENTS["ALL_TRACK"])
        field_events = getattr(CONST.EVENT, "ALL_FIELD", _FALLBACK_EVENTS["ALL_FIELD"])
    except NameError:
        track_events = _FALLBACK_EVENTS["ALL_TRACK"]
        field_events = _FALLBACK_EVENTS["ALL_FIELD"]

    for name in track_events + field_events:
        if name not in all_events:
            all_events.append(name)

    # Add gender-specific hurdles
    try:
        if gender == "Girls":
            hurdles = getattr(CONST.EVENT, "ALL_GIRLS_HURDLES", _FALLBACK_EVENTS["ALL_GIRLS_HURDLES"])
        else:
            hurdles = getattr(CONST.EVENT, "ALL_BOYS_HURDLES", _FALLBACK_EVENTS["ALL_BOYS_HURDLES"])
    except NameError:
        if gender == "Girls":
            hurdles = _FALLBACK_EVENTS["ALL_GIRLS_HURDLES"]
        else:
            hurdles = _FALLBACK_EVENTS["ALL_BOYS_HURDLES"]

    for name in hurdles:
        if name not in all_events:
            all_events.append(name)

    return all_events


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


def _format_sectional_result(value, event_type: str) -> str:
    """Format a result value for display."""
    if value is None:
        return ""
    
    if event_type == "Field":
        # Convert inches to feet-inches format
        feet = int(value // 12)
        inches = value % 12
        if inches == int(inches):
            return f"{feet}'{int(inches)}\""
        return f"{feet}'{inches:.2f}\""
    else:
        # Convert seconds to time format
        if value >= 60:
            minutes = int(value // 60)
            seconds = value % 60
            return f"{minutes}:{seconds:05.2f}"
        return f"{value:.2f}"


# ---------------------------------------------------------------------------
# Hypothetical athlete ranking
# ---------------------------------------------------------------------------

def get_hypothetical_ranking_options():
    """Return filter options for the hypothetical athlete query page."""
    all_events = _get_sectional_events()
    try:
        genders = list(getattr(CONST.GENDER, "ALL", _FALLBACK_GENDERS))
    except NameError:
        genders = _FALLBACK_GENDERS

    try:
        meet_types = list(getattr(CONST.MEET_TYPE, "ALL", []))
    except NameError:
        meet_types = ["Sectional"]

    return {
        "events": sorted(all_events),
        "genders": genders,
        "meet_types": meet_types if meet_types else ["Sectional"],
        "years": _get_sectional_years(),
    }


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


# -----------------------------------------------------------------------------
# School Dashboard
# -----------------------------------------------------------------------------

# Points awarded by place for cumulative scoring
_PLACE_POINTS = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
# State Finals score the top 9 places (3rd=7, not 6th) -- see
# web/backend/scripts/calculate_team_scores.py's STATE_SCORING, verified
# against MileSplit's official state team totals.
_STATE_PLACE_POINTS = {1: 10, 2: 8, 3: 7, 4: 6, 5: 5, 6: 4, 7: 3, 8: 2, 9: 1}

MIN_RECORDS_YEAR = 2023


def _active_db_path():
    """The database this app is actually reading.

    Not necessarily CONST.DB_PATH: Flask takes its URI from config.py, and the
    test suite points it at a fixture. Fingerprinting CONST.DB_PATH while the app
    served a different database meant the precomputed payloads looked valid for
    data they were never built from -- which is how a test fixture got answered
    with production rows.
    """
    try:
        from flask import current_app
        uri = current_app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    except Exception:
        uri = ''
    if uri.startswith('sqlite:///'):
        return uri[len('sqlite:///'):]
    return CONST.DB_PATH


def _db_fingerprint():
    """A cheap stamp of the database's current state.

    Size only, deliberately -- NOT modification time.

    mtime is not portable between machines, and this fingerprint has to be: the
    precomputed payloads are built here and read on the server. A deploy clones
    the repository fresh, and git stamps every checked-out file with the time of
    the clone, so an mtime recorded at build time can never match the one the
    server sees. That silently invalidated every precomputed payload on every
    request, which is the opposite of what these files are for.

    Size travels with the bytes, so it means the same thing in both places. It is
    a weaker signal -- a change that leaves the file exactly as large goes
    unnoticed -- but SQLite moves the page count for anything substantial, and a
    missed change costs a stale cache rather than a wrong one, since the payloads
    are regenerated by hand anyway.
    """
    try:
        return str(os.stat(_active_db_path()).st_size)
    except OSError:
        return ''


def _covered_rank_seasons():
    """Every season the rankings span, oldest first."""
    rows = db.session.execute(
        sqlalchemy_text(
            "select distinct year from meet "
            "where year is not null and year >= :y order by year"
        ),
        {"y": MIN_RECORDS_YEAR},
    )
    return [int(row[0]) for row in rows]


def _clear_query_caches(*, keep=()):
    """Empty every lru_cache in this module.

    Used when the database has changed underneath a running process: the caches
    here are keyed on query arguments, not on the state of the data, so nothing
    else would ever evict them.
    """
    for name, value in list(globals().items()):
        if name in keep:
            continue
        clear = getattr(value, 'cache_clear', None)
        if callable(clear):
            clear()


_LAST_SEEN_DB = {'fingerprint': None}


def ensure_fresh_queries():
    """Drop every cached query result if the database has changed.

    The caches in this module are keyed on query arguments, so nothing evicts
    them when the underlying data moves -- a long-running worker would keep
    serving the rankings it computed at start-up until it was restarted. That is
    why updating results meant remembering to reload the web app.

    Called once per request. The check is a single os.stat, and on the ordinary
    request -- where nothing has changed -- it does nothing else.
    """
    current = _db_fingerprint()
    previous = _LAST_SEEN_DB['fingerprint']
    _LAST_SEEN_DB['fingerprint'] = current
    if previous is not None and previous != current:
        logger.info('database changed (%s -> %s); clearing query caches',
                    previous, current)
        _clear_query_caches()
        return True
    return False


_SCHOOL_LOGO_DIR = os.path.join(CONST.WEB_DIR, "frontend", "static", CONST.SCHOOL_LOGO_STATIC_SUBDIR)


@lru_cache(maxsize=1)
def _schools_with_logos() -> frozenset:
    """school_ids that have a logo file on disk, cached for the process
    lifetime -- this directory only changes when standalone/notebooks/Load
    Schools in DB.ipynb is re-run, which happens far less often than a
    request comes in.
    """
    if not os.path.isdir(_SCHOOL_LOGO_DIR):
        return frozenset()
    ext_suffix = f".{CONST.SCHOOL_LOGO_EXT}"
    return frozenset(
        int(stem)
        for stem, ext in (os.path.splitext(name) for name in os.listdir(_SCHOOL_LOGO_DIR))
        if ext == ext_suffix and stem.isdigit()
    )


def _school_logo_url(school) -> Optional[str]:
    """Build the served URL for a school's logo, or None if it has none.

    Every logo is converted to a single canonical format/size (common/logo.py),
    so a file's existence at frontend/static/<CONST.SCHOOL_LOGO_STATIC_SUBDIR>/
    <school_id>.<CONST.SCHOOL_LOGO_EXT> IS the "has a logo" signal -- no DB
    column needed.
    """
    if not school or school.school_id not in _schools_with_logos():
        return None
    return f"/static/{CONST.SCHOOL_LOGO_STATIC_SUBDIR}/{school.school_id}.{CONST.SCHOOL_LOGO_EXT}"


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


def _build_school_roster(school_id: int):
    """Return list of athletes at this school, sorted by graduation year desc then last name."""
    athletes = (
        db.session.query(
            Athlete.athlete_id,
            Athlete.first,
            Athlete.last,
            Athlete.gender,
            Athlete.graduation_year,
        )
        .filter(Athlete.school_id == school_id)
        .all()
    )

    roster = []
    for a in athletes:
        roster.append({
            "athlete_id": a.athlete_id,
            "name": f"{a.first} {a.last}".strip(),
            "gender": a.gender,
            "graduation_year": a.graduation_year,
        })

    roster.sort(key=lambda r: (-(r["graduation_year"] or 0), r["name"]))
    return roster


def _compute_school_relay_results(school_id: int):
    """Return school relay performances for dashboard display."""
    rows = (
        db.session.query(
            RelayResult.event,
            RelayResult.result,
            RelayResult.result2,
            RelayResult.place,
            RelayResult.athlete_names,
            Meet.meet_id,
            Meet.host,
            Meet.meet_type,
            Meet.meet_num,
            Meet.gender,
            Meet.year,
            Event.event_type,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .join(Event, RelayResult.event == Event.event)
        .filter(
            RelayResult.school_id == school_id,
            RelayResult.result2.isnot(None),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .all()
    )

    statewide_rows = (
        db.session.query(
            RelayResult.event,
            Meet.gender,
            Meet.year,
            Meet.meet_type,
            RelayResult.school_id,
            RelayResult.result2,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.result2.isnot(None),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .all()
    )

    # Dedupe by school within each (event, gender, year, meet_type) bucket:
    # keep each school's best (lowest time) mark at that meet level so
    # ranking reflects teams that competed at that level, not raw
    # performance counts. Each row on the dashboard is ranked against the
    # pool of teams that ran the event at the same meet_type that year.
    best_by_school = {}
    for item in statewide_rows:
        key = (item.event, item.gender, item.year, item.meet_type, item.school_id)
        existing = best_by_school.get(key)
        if existing is None or item.result2 < existing:
            best_by_school[key] = item.result2

    statewide_marks = {}
    for (event, gender, year, meet_type, _sid), mark in best_by_school.items():
        statewide_marks.setdefault((event, gender, year, meet_type), []).append(mark)

    meet_order = {"Sectional": 1, "Regional": 2, "State": 3}
    results = []
    for row in rows:
        event_type = row.event_type or "Relay"
        lineup = _extract_relay_names(row.athlete_names or "")
        marks = statewide_marks.get((row.event, row.gender, row.year, row.meet_type), [])
        total_marks = len(marks)
        better_or_equal = sum(1 for mark in marks if mark <= row.result2) if total_marks else None
        percentile = round((1 - (better_or_equal / total_marks)) * 100, 1) if total_marks else None
        # Cap at 99.9: an athlete is included in their own pool, so they can
        # never beat themselves (true max is (1 - 1/total) * 100 < 100).
        if percentile is not None:
            percentile = min(percentile, 99.9)
        results.append(
            {
                "event": row.event,
                "result": row.result or _format_result_display(row.result2, event_type),
                "result_value": row.result2,
                "place": row.place,
                "athlete_names": row.athlete_names,
                "lineup": lineup,
                "meet_id": row.meet_id,
                "meet_host": row.host,
                "meet_type": row.meet_type,
                "meet_num": row.meet_num,
                "gender": row.gender,
                "year": row.year,
                "event_type": event_type,
                "state_percentile": max(percentile, 0) if percentile is not None else None,
                "rank": better_or_equal,
                "total_marks": total_marks,
                "_meet_order": meet_order.get(row.meet_type, 0),
            }
        )

    results.sort(
        key=lambda item: (
            -(item.get("year") or 0),
            -(item.get("_meet_order") or 0),
            item.get("event") or "",
            item.get("result_value") if item.get("result_value") is not None else float("inf"),
        )
    )

    for item in results:
        item.pop("_meet_order", None)

    return results


def _compute_cumulative_points(school_id: int):
    """
    Compute cumulative points, team rankings, and average places for a school across playoff meets from 2023+.
    Points: 1st=10, 2nd=8, 3rd=6, 4th=5, 5th=4, 6th=3, 7th=2, 8th=1.
    Returns dict keyed by gender, each containing yearly breakdown with points, team rank, and avg places.
    Team rank is relative to schools at the same meet (sectional/regional) or statewide (state).
    """

    # First, get ALL schools' points for ranking purposes
    # Include meet_id and event so ties WITHIN an event can be detected and
    # split fractionally -- two different events both having a "3rd place"
    # at the same meet are not a tie with each other.
    all_individual_rows = (
        db.session.query(
            Athlete.school_id,
            AthleteResult.event,
            Meet.meet_id,
            Meet.year,
            Meet.gender,
            Meet.meet_type,
            AthleteResult.place,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            AthleteResult.result_type == "Final",
            AthleteResult.place.isnot(None),
            AthleteResult.place > 0,
            AthleteResult.place <= 9,
            Meet.year >= MIN_RECORDS_YEAR,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .all()
    )

    all_relay_rows = (
        db.session.query(
            RelayResult.school_id,
            RelayResult.event,
            Meet.meet_id,
            Meet.year,
            Meet.gender,
            Meet.meet_type,
            RelayResult.place,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.place.isnot(None),
            RelayResult.place > 0,
            RelayResult.place <= 9,
            Meet.year >= MIN_RECORDS_YEAR,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .all()
    )

    # Group into {(meet_id, event): [(school_id, place), ...]} for tie
    # detection, and separately track each school's raw per-meet place list
    # (for avg_place/entries display -- unaffected by point tie-splitting).
    event_groups = {}
    meet_metadata = {}
    school_places_by_meet = {}
    for rows in (all_individual_rows, all_relay_rows):
        for sid, event, meet_id, year, gender, meet_type, place in rows:
            meet_metadata.setdefault(meet_id, (year, gender, meet_type))
            event_groups.setdefault((meet_id, event), []).append((sid, place))
            school_places_by_meet.setdefault(meet_id, {}).setdefault(sid, []).append(place)

    # Build {meet_id: {school_id: {"points": float, "places": [int]}}},
    # awarding points per event using each event's actual recorded place
    # (not each row's sequential position), splitting a tie's combined
    # scoring-slot value evenly across the tied schools -- mirrors
    # web/backend/scripts/calculate_team_scores.py's get_points().
    meet_school_stats = {}

    def _stats_entry(meet_id, sid):
        return meet_school_stats.setdefault(meet_id, {}).setdefault(sid, {"points": 0, "places": []})

    for (meet_id, event), school_places in event_groups.items():
        _, _, meet_type = meet_metadata[meet_id]
        points_table = _STATE_PLACE_POINTS if meet_type == "State" else _PLACE_POINTS

        by_place = {}
        for sid, place in school_places:
            by_place.setdefault(place, []).append(sid)

        for actual_place, tied_schools in by_place.items():
            tie_size = len(tied_schools)
            scoring_slots = [p for p in range(actual_place, actual_place + tie_size) if p in points_table]
            pts_value = (sum(points_table[p] for p in scoring_slots) / tie_size) if scoring_slots else 0
            for sid in tied_schools:
                _stats_entry(meet_id, sid)["points"] += pts_value

    for meet_id, by_school in school_places_by_meet.items():
        for sid, places in by_school.items():
            _stats_entry(meet_id, sid)["places"] = places

    # Compute rankings for each meet
    # {meet_id: {school_id: {"rank": int, "total_teams": int}}}
    # total_teams = all schools that competed at the meet (not just scorers)
    all_competing_indiv = (
        db.session.query(Athlete.school_id, AthleteResult.meet_id)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Meet.year >= MIN_RECORDS_YEAR,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .distinct()
        .all()
    )
    all_competing_relay = (
        db.session.query(RelayResult.school_id, RelayResult.meet_id)
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            Meet.year >= MIN_RECORDS_YEAR,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .distinct()
        .all()
    )
    meet_total_schools = {}
    for sid, mid in all_competing_indiv + all_competing_relay:
        meet_total_schools.setdefault(mid, set()).add(sid)

    # Alphabetical-by-school-name secondary sort for equal-points ties --
    # standardizes on the tiebreak convention already used by the
    # regional/state/projected-team-scores prediction scripts.
    school_names = dict(db.session.query(School.school_id, School.school_name).all())

    meet_rankings = {}
    for meet_id, schools_data in meet_school_stats.items():
        sorted_schools = sorted(
            schools_data.items(),
            key=lambda x: (-x[1]["points"], school_names.get(x[0], "")),
        )
        total = len(meet_total_schools.get(meet_id, set()) | set(schools_data.keys()))
        rankings = {}
        for rank, (sid, _) in enumerate(sorted_schools, start=1):
            rankings[sid] = {"rank": rank, "total_teams": total}
        meet_rankings[meet_id] = rankings

    # Now extract data for the specific school
    # Aggregate by (year, gender, meet_type) for display
    stats_data = {}
    for meet_id, schools_data in meet_school_stats.items():
        if school_id not in schools_data:
            continue
        year, gender, meet_type = meet_metadata[meet_id]
        school_stats = schools_data[school_id]
        ranking_info = meet_rankings[meet_id].get(school_id, {})
        
        gender_data = stats_data.setdefault(gender, {})
        year_data = gender_data.setdefault(year, {})
        # For a given year/gender/meet_type, store the data
        # (a school only competes at one sectional/regional per year/gender)
        year_data[meet_type] = {
            "points": school_stats["points"],
            "places": school_stats["places"],
            "team_rank": ranking_info.get("rank"),
            "total_teams": ranking_info.get("total_teams"),
        }

    result = {}
    for gender, years_dict in stats_data.items():
        yearly = []
        total = 0
        for year in sorted(years_dict.keys(), reverse=True):
            meet_types = years_dict[year]
            year_total = sum(mt.get("points", 0) for mt in meet_types.values())
            total += year_total
            
            year_entry = {"year": year, "total": year_total}
            for mt_name in ("Sectional", "Regional", "State"):
                mt_key = mt_name.lower()
                mt_data = meet_types.get(mt_name, {})
                places = mt_data.get("places", [])
                year_entry[mt_key] = {
                    "points": mt_data.get("points", 0),
                    "avg_place": round(sum(places) / len(places), 1) if places else None,
                    "entries": len(places),
                    "team_rank": mt_data.get("team_rank"),
                    "total_teams": mt_data.get("total_teams"),
                }
            yearly.append(year_entry)
        result[gender] = {"yearly": yearly, "grand_total": total}

    return result


def _compute_school_percentiles(school_id: int, year: Optional[int] = None):
    """Compute school best/avg marks and percentiles for playoff meets only.

    Rules implemented:
      - Only Sectional/Regional/State results are considered.
      - Individual marks resolve per meet using Final first, then Prelim fallback.
      - Athlete best mark = best resolved playoff mark in the filtered scope.
      - Best Mark percentile compares against individual athlete bests only.
      - Avg Mark percentile compares against qualifying school duo averages only.
      - For running events, lower is better; for field events, higher is better.
    """

    PLAYOFF_MEETS = ("Sectional", "Regional", "State")
    year_filter = (Meet.year == year) if year else Meet.year.isnot(None)

    def _athlete_season_marks(rows):
        """Collapse rows to (event, year, athlete) season best with Final-over-Prelim per meet."""
        per_meet = {}  # (athlete_id, event, meet_id) -> {result_type: (result2, year)}
        event_type_map = {}
        for r in rows:
            key = (r.athlete_id, r.event, r.meet_id)
            per_meet.setdefault(key, {})[r.result_type] = (r.result2, r.year)
            event_type_map[r.event] = r.event_type

        season = {}  # (event, year, athlete_id) -> {mark_raw, event_type}
        for (athlete_id, event, _meet_id), marks in per_meet.items():
            picked = marks.get("Final") or marks.get("Prelim")
            if picked is None:
                picked = next(iter(marks.values()), None)
            if picked is None:
                continue

            mark_val, mark_year = picked
            event_type = event_type_map[event]
            lower = _is_lower_better(event_type)
            season_key = (event, mark_year, athlete_id)
            existing = season.get(season_key)
            if existing is None or (
                (lower and mark_val < existing["mark_raw"])
                or (not lower and mark_val > existing["mark_raw"])
            ):
                season[season_key] = {
                    "mark_raw": mark_val,
                    "event_type": event_type,
                }
        return season

    def _calc_percentile(mark, all_marks, lower_is_better):
        if mark is None or not all_marks:
            return None, None, None
        total = len(all_marks)
        better_or_equal = sum(
            1 for m in all_marks if (m <= mark if lower_is_better else m >= mark)
        )
        percentile = round((1 - (better_or_equal / total)) * 100, 1)
        percentile = min(percentile, 99.9)
        return max(percentile, 0), better_or_equal, total

    # ── School individual rows (playoff meets only) ──
    school_indiv_rows = (
        db.session.query(
            AthleteResult.event,
            AthleteResult.meet_id,
            AthleteResult.result_type,
            AthleteResult.result2,
            AthleteResult.athlete_id,
            Athlete.first,
            Athlete.last,
            Athlete.gender,
            Event.event_type,
            Meet.year,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            Athlete.school_id == school_id,
            AthleteResult.result2.isnot(None),
            year_filter,
            Meet.meet_type.in_(PLAYOFF_MEETS),
            Event.event_type != "Relay",
        )
        .all()
    )

    school_athlete_meta = {}
    for r in school_indiv_rows:
        if r.athlete_id not in school_athlete_meta:
            school_athlete_meta[r.athlete_id] = (
                "{} {}".format(r.first, r.last).strip(),
                r.gender,
            )

    school_season = _athlete_season_marks(school_indiv_rows)
    school_event_year_athletes = {}  # (event, gender, year) -> [{athlete...}]
    for (event, season_year, athlete_id), info in school_season.items():
        name, gender = school_athlete_meta[athlete_id]
        school_event_year_athletes.setdefault((event, gender, season_year), []).append(
            {
                "athlete_id": athlete_id,
                "name": name,
                "mark_raw": info["mark_raw"],
                "year": season_year,
                "event_type": info["event_type"],
            }
        )

    indiv_metrics = {}
    event_gender_pairs = {(e, g) for (e, g, _y) in school_event_year_athletes.keys()}
    for (event, gender) in event_gender_pairs:
        year_groups = {
            y: lst
            for (e, g, y), lst in school_event_year_athletes.items()
            if e == event and g == gender
        }
        event_type = next(iter(year_groups.values()))[0]["event_type"]
        lower = _is_lower_better(event_type)

        best_mark = None
        best_athletes = []
        for y, athletes in year_groups.items():
            for a in athletes:
                if best_mark is None or (
                    (lower and a["mark_raw"] < best_mark)
                    or (not lower and a["mark_raw"] > best_mark)
                ):
                    best_mark = a["mark_raw"]
                    best_athletes = [a]
                elif best_mark is not None and math.isclose(a["mark_raw"], best_mark, rel_tol=0.0, abs_tol=1e-9):
                    best_athletes.append(a)

        # Keep tie ordering deterministic.
        best_athletes.sort(key=lambda item: (-(item.get("year") or 0), item.get("name") or ""))

        best_duos = []
        best_duo_avg = None
        for y, athletes in year_groups.items():
            if len(athletes) < 2:
                continue
            sorted_athletes = sorted(athletes, key=lambda a: a["mark_raw"], reverse=not lower)
            duo = sorted_athletes[:2]
            duo_avg = (duo[0]["mark_raw"] + duo[1]["mark_raw"]) / 2.0
            if best_duo_avg is None or (
                (lower and duo_avg < best_duo_avg)
                or (not lower and duo_avg > best_duo_avg)
            ):
                best_duo_avg = duo_avg
                best_duos = [{"year": y, "avg_raw": duo_avg, "athletes": duo}]
            elif best_duo_avg is not None and math.isclose(duo_avg, best_duo_avg, rel_tol=0.0, abs_tol=1e-9):
                best_duos.append({"year": y, "avg_raw": duo_avg, "athletes": duo})

        best_duos.sort(
            key=lambda item: (
                -(item.get("year") or 0),
                " | ".join(a.get("name") or "" for a in item.get("athletes", [])),
            )
        )
        best_duo = best_duos[0]["athletes"] if best_duos else []
        best_duo_year = best_duos[0]["year"] if best_duos else None
        best_year = best_athletes[0]["year"] if best_athletes else None

        indiv_metrics[(event, gender)] = {
            "is_relay": False,
            "event_type": event_type,
            "best_raw": best_mark,
            "best_holder": best_athletes[0]["name"] if best_athletes else None,
            "best_holder_id": best_athletes[0]["athlete_id"] if best_athletes else None,
            "best_holders": best_athletes,
            "best_year": best_year,
            "avg_top2_raw": best_duo_avg,
            "avg_year": best_duo_year,
            "avg_top_athletes": best_duo,
            "avg_top_duos": best_duos,
        }

    # ── School relay bests (playoff meets only) ──
    relay_rows = (
        db.session.query(
            RelayResult.event,
            RelayResult.result2,
            RelayResult.athlete_names,
            Meet.gender,
            Meet.year,
            Event.event_type,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .join(Event, RelayResult.event == Event.event)
        .filter(
            RelayResult.school_id == school_id,
            RelayResult.result2.isnot(None),
            year_filter,
            Meet.meet_type.in_(PLAYOFF_MEETS),
        )
        .all()
    )

    relay_metrics = {}
    for row in relay_rows:
        key = (row.event, row.gender)
        lower_is_better = _is_lower_better(row.event_type)
        existing = relay_metrics.get(key)
        entry = {
            "name": row.athlete_names or "Relay Team",
            "athlete_id": None,
            "year": row.year,
            "mark_raw": row.result2,
        }
        if existing is None or (
            (lower_is_better and row.result2 < existing["best_raw"])
            or (not lower_is_better and row.result2 > existing["best_raw"])
        ):
            relay_metrics[key] = {
                "is_relay": True,
                "event_type": row.event_type,
                "best_raw": row.result2,
                "best_holder": entry["name"],
                "best_holder_id": None,
                "best_holders": [entry],
                "best_year": row.year,
                "avg_top2_raw": None,
                "avg_year": None,
                "avg_top_athletes": [],
                "avg_top_duos": [],
            }
        elif math.isclose(row.result2, existing["best_raw"], rel_tol=0.0, abs_tol=1e-9):
            existing["best_holders"].append(entry)

    for item in relay_metrics.values():
        holders = item.get("best_holders", [])
        holders.sort(key=lambda entry: (-(entry.get("year") or 0), entry.get("name") or ""))
        if holders:
            item["best_holder"] = holders[0]["name"]
            item["best_year"] = holders[0]["year"]

    all_metrics = {}
    all_metrics.update(indiv_metrics)
    all_metrics.update(relay_metrics)
    if not all_metrics:
        return []

    # ── Statewide individual rows (playoff meets only) ──
    statewide_indiv_rows = (
        db.session.query(
            AthleteResult.event,
            AthleteResult.meet_id,
            AthleteResult.result_type,
            AthleteResult.result2,
            AthleteResult.athlete_id,
            Athlete.school_id,
            Athlete.gender,
            Event.event_type,
            Meet.year,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            AthleteResult.result2.isnot(None),
            year_filter,
            Meet.meet_type.in_(PLAYOFF_MEETS),
            Event.event_type != "Relay",
        )
        .all()
    )
    sw_season = _athlete_season_marks(statewide_indiv_rows)

    sw_meta = {}
    for r in statewide_indiv_rows:
        if r.athlete_id not in sw_meta:
            sw_meta[r.athlete_id] = {"gender": r.gender, "school_id": r.school_id}

    # Best distribution (individual athlete bests only)
    statewide_indiv_best_dist = {}  # (event, gender) -> [mark]
    sw_athlete_best = {}  # (event, gender, athlete_id) -> best mark
    for (event, _season_year, athlete_id), info in sw_season.items():
        meta = sw_meta.get(athlete_id)
        if not meta:
            continue
        gender = meta["gender"]
        lower = _is_lower_better(info["event_type"])
        key = (event, gender, athlete_id)
        existing = sw_athlete_best.get(key)
        if existing is None or (
            (lower and info["mark_raw"] < existing)
            or (not lower and info["mark_raw"] > existing)
        ):
            sw_athlete_best[key] = info["mark_raw"]

    for (event, gender, _athlete_id), mark in sw_athlete_best.items():
        statewide_indiv_best_dist.setdefault((event, gender), []).append(mark)

    # Avg distribution (qualifying school duos only)
    sw_school_event_year = {}  # (event, gender, year, school_id) -> [{mark_raw, event_type}]
    for (event, season_year, athlete_id), info in sw_season.items():
        meta = sw_meta.get(athlete_id)
        if not meta:
            continue
        key = (event, meta["gender"], season_year, meta["school_id"])
        sw_school_event_year.setdefault(key, []).append(
            {
                "mark_raw": info["mark_raw"],
                "event_type": info["event_type"],
            }
        )

    sw_duo_by_schoolyear = {}  # (event, gender, year, school_id) -> avg_raw
    for (event, gender, season_year, sid), athletes in sw_school_event_year.items():
        if len(athletes) < 2:
            continue
        event_type = athletes[0]["event_type"]
        lower = _is_lower_better(event_type)
        top2 = sorted(athletes, key=lambda a: a["mark_raw"], reverse=not lower)[:2]
        sw_duo_by_schoolyear[(event, gender, season_year, sid)] = (
            (top2[0]["mark_raw"] + top2[1]["mark_raw"]) / 2.0
        )

    # Avg percentile pool:
    # - Year-specific views use qualifying school-year duo values for that season.
    # - All-time views collapse to each school's single best duo average across all years in scope.
    statewide_duo_dist = {}  # (event, gender) -> [avg_raw]
    if year is not None:
        for (event, gender, _season_year, _sid), duo_avg in sw_duo_by_schoolyear.items():
            statewide_duo_dist.setdefault((event, gender), []).append(duo_avg)
    else:
        sw_best_duo_by_school = {}  # (event, gender, school_id) -> avg_raw
        for (event, gender, _season_year, sid), duo_avg in sw_duo_by_schoolyear.items():
            athletes = sw_school_event_year[(event, gender, _season_year, sid)]
            event_type = athletes[0]["event_type"]
            lower = _is_lower_better(event_type)
            key = (event, gender, sid)
            existing = sw_best_duo_by_school.get(key)
            if existing is None or (
                (lower and duo_avg < existing)
                or (not lower and duo_avg > existing)
            ):
                sw_best_duo_by_school[key] = duo_avg

        for (event, gender, _sid), duo_avg in sw_best_duo_by_school.items():
            statewide_duo_dist.setdefault((event, gender), []).append(duo_avg)

    # ── Statewide relay best distributions (school best relay marks) ──
    statewide_relay_dist = {}
    relay_group_rows = (
        db.session.query(
            RelayResult.event,
            Meet.gender,
            RelayResult.school_id,
            Event.event_type,
            func.min(RelayResult.result2).label("best_mark"),
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .join(Event, RelayResult.event == Event.event)
        .filter(
            RelayResult.result2.isnot(None),
            year_filter,
            Meet.meet_type.in_(PLAYOFF_MEETS),
        )
        .group_by(RelayResult.event, Meet.gender, RelayResult.school_id, Event.event_type)
        .all()
    )
    for row in relay_group_rows:
        statewide_relay_dist.setdefault((row.event, row.gender), []).append(row.best_mark)

    results = []
    for (event_name, gender), info in sorted(all_metrics.items()):
        event_type = info["event_type"]
        lower_is_better = _is_lower_better(event_type)

        best_raw = info["best_raw"]
        if info["is_relay"]:
            best_pool = statewide_relay_dist.get((event_name, gender), [])
        else:
            best_pool = statewide_indiv_best_dist.get((event_name, gender), [])
        best_pct, best_rank, best_total = _calc_percentile(best_raw, best_pool, lower_is_better)

        avg_raw = info.get("avg_top2_raw") if not info["is_relay"] else None
        avg_pool = statewide_duo_dist.get((event_name, gender), []) if not info["is_relay"] else []
        avg_pct, avg_rank, avg_total = _calc_percentile(avg_raw, avg_pool, lower_is_better)

        avg_top_athletes = [
            {
                "name": a["name"],
                "athlete_id": a["athlete_id"],
                "mark_raw": a["mark_raw"],
                "mark": _format_result_display(a["mark_raw"], event_type),
                "year": a["year"],
            }
            for a in info.get("avg_top_athletes", [])
        ]

        best_holders = [
            {
                "name": h.get("name"),
                "athlete_id": h.get("athlete_id"),
                "year": h.get("year"),
                "mark_raw": h.get("mark_raw"),
                "mark": _format_result_display(h.get("mark_raw"), event_type)
                if h.get("mark_raw") is not None else None,
            }
            for h in info.get("best_holders", [])
        ]

        top_duos = [
            {
                "year": duo.get("year"),
                "avg_raw": duo.get("avg_raw"),
                "avg_mark": _format_result_display(duo.get("avg_raw"), event_type)
                if duo.get("avg_raw") is not None else None,
                "athletes": [
                    {
                        "name": a.get("name"),
                        "athlete_id": a.get("athlete_id"),
                        "year": a.get("year"),
                        "mark_raw": a.get("mark_raw"),
                        "mark": _format_result_display(a.get("mark_raw"), event_type)
                        if a.get("mark_raw") is not None else None,
                    }
                    for a in duo.get("athletes", [])
                ],
            }
            for duo in info.get("avg_top_duos", [])
        ]

        results.append(
            {
                "event": event_name,
                "gender": gender,
                "event_type": event_type,
                "is_relay": info["is_relay"],
                "school_best": _format_result_display(best_raw, event_type) if best_raw is not None else None,
                "school_best_raw": best_raw,
                "school_avg_top2": _format_result_display(avg_raw, event_type) if avg_raw is not None else None,
                "school_avg_top2_raw": avg_raw,
                "avg_athlete_count": len(avg_top_athletes),
                "top_athletes": avg_top_athletes,
                "top_duos": top_duos,
                "holder": info.get("best_holder"),
                "holder_id": info.get("best_holder_id"),
                "holders": best_holders,
                "year": info.get("best_year"),
                "avg_year": info.get("avg_year"),
                "best_state_percentile": best_pct,
                "best_rank": best_rank,
                "best_total_marks": best_total,
                "avg_state_percentile": avg_pct,
                "avg_rank": avg_rank,
                "avg_total_marks": avg_total,
                # Backward-compatible fields (best metric)
                "state_percentile": best_pct,
                "rank": best_rank,
                "total_marks": best_total,
            }
        )

    return results


def _get_school_percentile_years(school_id: int) -> List[int]:
    """Return sorted list of years (descending) that a school has results (individual or relay)."""
    indiv_years = (
        db.session.query(Meet.year)
        .join(AthleteResult, AthleteResult.meet_id == Meet.meet_id)
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(
            Athlete.school_id == school_id,
            AthleteResult.result2.isnot(None),
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
            Meet.year.isnot(None),
        )
        .distinct()
        .all()
    )
    relay_years = (
        db.session.query(Meet.year)
        .join(RelayResult, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.school_id == school_id,
            RelayResult.result2.isnot(None),
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
            Meet.year.isnot(None),
        )
        .distinct()
        .all()
    )
    all_years = set(r.year for r in indiv_years) | set(r.year for r in relay_years)
    return sorted(all_years, reverse=True)


def _format_result_display(raw_value, event_type):
    """Format a raw numeric result for display."""
    if raw_value is None:
        return "—"
    if event_type == "Field":
        total_inches = raw_value
        feet = int(total_inches // 12)
        inches = total_inches % 12
        if inches == int(inches):
            return f"{feet}'{int(inches)}\""
        return f"{feet}'{inches:.2f}\""
    else:
        seconds = raw_value
        if seconds >= 60:
            minutes = int(seconds // 60)
            remaining = seconds % 60
            return f"{minutes}:{remaining:05.2f}"
        return f"{seconds:.2f}"


def _format_gap_display(raw_value, event_type):
    """Format a *difference* between two marks.

    A field gap under a foot comes back from _format_result_display as 0'4",
    which reads badly for a delta -- inches alone are what a coach thinks in at
    that range.
    """
    if raw_value is None:
        return None
    if event_type == CONST.EVENT_TYPE.FIELD and raw_value < 12:
        if raw_value == int(raw_value):
            return f'{int(raw_value)}"'
        return f'{raw_value:.2f}"'.replace('.00"', '"')
    display = _format_result_display(raw_value, event_type)
    # A running gap is a number of seconds and has to say so -- "0.29" on its own
    # reads as a placing or a wind reading. A gap long enough to be formatted with
    # a colon is already minutes and seconds, so it carries its own units; so does
    # a field gap of a foot or more, which comes back as 2'5.25" and must not be
    # handed a trailing s.
    if display and event_type != CONST.EVENT_TYPE.FIELD and ":" not in display:
        return f"{display}s"
    return display


def _compute_school_records(school_id: int):
    """Unofficial school records: best mark per event+gender from 2023 onwards."""

    individual_rows = (
        db.session.query(
            AthleteResult.event,
            AthleteResult.result,
            AthleteResult.result2,
            AthleteResult.athlete_id,
            Athlete.first,
            Athlete.last,
            Athlete.gender,
            Event.event_type,
            Meet.year,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .filter(
            Athlete.school_id == school_id,
            AthleteResult.result2.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
            Event.event_type != "Relay",
        )
        .all()
    )

    records_map = {}
    for row in individual_rows:
        key = (row.event, row.gender)
        lower_is_better = _is_lower_better(row.event_type)
        existing = records_map.get(key)
        if existing is None:
            records_map[key] = row
        elif lower_is_better and row.result2 < existing.result2:
            records_map[key] = row
        elif not lower_is_better and row.result2 > existing.result2:
            records_map[key] = row

    relay_rows = (
        db.session.query(
            RelayResult.event,
            RelayResult.result,
            RelayResult.result2,
            RelayResult.athlete_names,
            Meet.gender,
            Meet.year,
            Event.event_type,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .join(Event, RelayResult.event == Event.event)
        .filter(
            RelayResult.school_id == school_id,
            RelayResult.result2.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
        )
        .all()
    )

    relay_map = {}
    for row in relay_rows:
        key = (row.event, row.gender)
        lower_is_better = _is_lower_better(row.event_type)
        existing = relay_map.get(key)
        if existing is None:
            relay_map[key] = row
        elif lower_is_better and row.result2 < existing.result2:
            relay_map[key] = row
        elif not lower_is_better and row.result2 > existing.result2:
            relay_map[key] = row

    records = []
    for (event, gender), row in sorted(records_map.items()):
        event_type = row.event_type
        display_result = row.result or _format_result_display(row.result2, event_type)
        records.append({
            "event": event,
            "gender": gender,
            "event_type": event_type,
            "result": display_result,
            "result_raw": row.result2,
            "holder": f"{row.first} {row.last}".strip(),
            "holder_id": row.athlete_id,
            "year": row.year,
            "is_relay": False,
        })

    for (event, gender), row in sorted(relay_map.items()):
        event_type = row.event_type
        display_result = row.result or _format_result_display(row.result2, event_type)
        records.append({
            "event": event,
            "gender": gender,
            "event_type": event_type,
            "result": display_result,
            "result_raw": row.result2,
            "holder": row.athlete_names or "Relay Team",
            "holder_id": None,
            "year": row.year,
            "is_relay": True,
        })

    records.sort(key=lambda r: (r["gender"], r["event"]))
    return records


def _compute_avg_places(school_id: int):
    """
    Average place at Sectional, Regional, and State in the last 3 years.
    Includes both individual and relay results (Finals only).
    """

    current_year = db.session.query(func.max(Meet.year)).scalar() or 2025
    min_year = current_year - 2

    meet_types_list = ("Sectional", "Regional", "State")

    individual_rows = (
        db.session.query(
            Meet.gender,
            Meet.meet_type,
            AthleteResult.place,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Athlete.school_id == school_id,
            AthleteResult.result_type == "Final",
            AthleteResult.place.isnot(None),
            AthleteResult.place > 0,
            Meet.year >= min_year,
            Meet.meet_type.in_(meet_types_list),
        )
        .all()
    )

    relay_rows = (
        db.session.query(
            Meet.gender,
            Meet.meet_type,
            RelayResult.place,
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .filter(
            RelayResult.school_id == school_id,
            RelayResult.place.isnot(None),
            RelayResult.place > 0,
            Meet.year >= min_year,
            Meet.meet_type.in_(meet_types_list),
        )
        .all()
    )

    # {gender: {meet_type: [places]}}
    places_data = {}
    for rows in (individual_rows, relay_rows):
        for gender, meet_type, place in rows:
            gender_data = places_data.setdefault(gender, {})
            type_list = gender_data.setdefault(meet_type, [])
            type_list.append(place)

    result = {}
    for gender, types_dict in places_data.items():
        gender_result = {}
        for mt in meet_types_list:
            places = types_dict.get(mt, [])
            if places:
                gender_result[mt.lower()] = {
                    "avg_place": round(sum(places) / len(places), 1),
                    "count": len(places),
                }
            else:
                gender_result[mt.lower()] = None
        result[gender] = gender_result

    return result


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


def _resolve_school_enrollment_for_year(school: School, year: Optional[int]) -> Dict[str, Any]:
    enrollments = sorted(
        [item for item in getattr(school, "enrollments", []) if item.year is not None],
        key=lambda item: item.year,
    )
    if not enrollments:
        return {
            "value": None,
            "source_year": None,
            "is_exact": False,
        }

    if year is None:
        latest = enrollments[-1]
        return {
            "value": latest.enrollment,
            "source_year": latest.year,
            "is_exact": True,
        }

    exact = next((item for item in enrollments if item.year == year), None)
    if exact:
        return {
            "value": exact.enrollment,
            "source_year": exact.year,
            "is_exact": True,
        }

    nearest = sorted(
        enrollments,
        key=lambda item: (
            abs(item.year - year),
            0 if item.year <= year else 1,
            -item.year,
        ),
    )[0]
    return {
        "value": nearest.enrollment,
        "source_year": nearest.year,
        "is_exact": False,
    }


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


def _is_valid_postseason_mark(result_value, event_type: str) -> bool:
    if result_value is None:
        return False
    if event_type == CONST.EVENT_TYPE.FIELD:
        return result_value > 0
    return 0 < result_value < 9999


def _format_points_value(points: Optional[float]) -> Optional[str]:
    if points is None:
        return None
    rounded = round(points, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


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


def _normalize_rank_to_score(rank: Optional[int], total_marks: int) -> float:
    if rank is None or total_marks <= 0:
        return 0.0
    if total_marks == 1:
        return 100.0
    return round(((total_marks - rank) / (total_marks - 1)) * 100, 1)


# Cached: one cold dashboard calls this eight times over with repeating
# arguments -- once per season for the rank history, again per school for the
# scorecard -- and each call re-runs the join and rebuilds every row as a dict.
# Verified output-identical across 60 dashboard payloads before being added; the
# returned list is treated as read-only by every caller, so they share it.
@lru_cache(maxsize=64)
def _resolve_postseason_individual_rows(
    *,
    gender: Optional[str] = None,
    year: Optional[int] = None,
    school_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    query = (
        db.session.query(
            Athlete.school_id.label("school_id"),
            School.school_name.label("school_name"),
            Athlete.athlete_id.label("athlete_id"),
            Athlete.first.label("first"),
            Athlete.last.label("last"),
            Athlete.gender.label("gender"),
            AthleteResult.event.label("event"),
            AthleteResult.meet_id.label("meet_id"),
            AthleteResult.result_type.label("result_type"),
            AthleteResult.result.label("result"),
            AthleteResult.result2.label("result_value"),
            AthleteResult.place.label("place"),
            Meet.meet_type.label("meet_type"),
            Meet.year.label("year"),
            Event.event_type.label("event_type"),
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .join(Event, AthleteResult.event == Event.event)
        .outerjoin(School, Athlete.school_id == School.school_id)
        .filter(
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
            Event.event_type != CONST.EVENT_TYPE.RELAY,
            AthleteResult.result2.isnot(None),
        )
    )
    if gender:
        query = query.filter(Athlete.gender == gender, Meet.gender == gender)
    if year is not None:
        query = query.filter(Meet.year == year)
    if school_id is not None:
        query = query.filter(Athlete.school_id == school_id)

    per_meet: Dict[Tuple[int, str, int], Dict[str, Any]] = {}
    for row in query.all():
        candidate = {
            "school_id": row.school_id,
            "school_name": row.school_name,
            "athlete_id": row.athlete_id,
            "athlete_name": f"{(row.first or '').strip()} {(row.last or '').strip()}".strip(),
            "gender": row.gender,
            "event": row.event,
            "meet_id": row.meet_id,
            "meet_type": row.meet_type,
            "year": row.year,
            "event_type": row.event_type or CONST.EVENT_TYPE.TRACK,
            "result_type": row.result_type,
            "result": row.result,
            "result_value": row.result_value,
            "place": row.place,
        }
        key = (row.athlete_id, row.event, row.meet_id)
        lower_is_better = _is_lower_better(candidate["event_type"])
        per_meet[key] = _choose_result_entry(per_meet.get(key), candidate, lower_is_better)
    return list(per_meet.values())


# Cached: one cold dashboard calls this eight times over with repeating
# arguments -- once per season for the rank history, again per school for the
# scorecard -- and each call re-runs the join and rebuilds every row as a dict.
# Verified output-identical across 60 dashboard payloads before being added; the
# returned list is treated as read-only by every caller, so they share it.
@lru_cache(maxsize=64)
def _resolve_postseason_relay_rows(
    *,
    gender: Optional[str] = None,
    year: Optional[int] = None,
    school_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    query = (
        db.session.query(
            RelayResult.school_id.label("school_id"),
            School.school_name.label("school_name"),
            Meet.gender.label("gender"),
            RelayResult.event.label("event"),
            RelayResult.meet_id.label("meet_id"),
            Meet.meet_type.label("meet_type"),
            Meet.year.label("year"),
            RelayResult.result.label("result"),
            RelayResult.result2.label("result_value"),
            RelayResult.place.label("place"),
            RelayResult.athlete_names.label("athlete_names"),
        )
        .join(Meet, RelayResult.meet_id == Meet.meet_id)
        .outerjoin(School, RelayResult.school_id == School.school_id)
        .filter(
            Meet.meet_type.in_(CONST.MEET_TYPE.ALL),
            Meet.year.isnot(None),
            Meet.year >= MIN_RECORDS_YEAR,
            RelayResult.result2.isnot(None),
        )
    )
    if gender:
        query = query.filter(Meet.gender == gender)
    if year is not None:
        query = query.filter(Meet.year == year)
    if school_id is not None:
        query = query.filter(RelayResult.school_id == school_id)

    return [
        {
            "school_id": row.school_id,
            "school_name": row.school_name,
            "gender": row.gender,
            "event": row.event,
            "meet_id": row.meet_id,
            "meet_type": row.meet_type,
            "year": row.year,
            "event_type": CONST.EVENT_TYPE.RELAY,
            "result": row.result,
            "result_value": row.result_value,
            "place": row.place,
            "athlete_names": row.athlete_names,
            "lineup": _extract_relay_names(row.athlete_names or ""),
        }
        for row in query.all()
    ]


# Scores an entire meet for every school in it, so two schools that ran the same
# sectional were each paying for the identical computation. One core request
# triggers 5-8 of these via stage summary and sectional group points. There are
# 328 meets in the corpus, so maxsize=512 holds all of them.
@lru_cache(maxsize=512)
def _compute_team_scores_for_meet(meet_id: int) -> Dict[int, Dict[str, Any]]:
    meet = db.session.get(Meet, meet_id)
    if not meet:
        return {}

    points_table = _STATE_PLACE_POINTS if meet.meet_type == CONST.MEET_TYPE.STATE else _PLACE_POINTS
    scoring_limit = 9 if meet.meet_type == CONST.MEET_TYPE.STATE else 8

    individual_rows = (
        db.session.query(
            Athlete.school_id,
            AthleteResult.event,
            AthleteResult.place,
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(
            AthleteResult.meet_id == meet_id,
            AthleteResult.result_type == CONST.RESULT_TYPE.FINAL,
            AthleteResult.place.isnot(None),
            AthleteResult.place > 0,
            AthleteResult.place <= scoring_limit,
        )
        .all()
    )
    relay_rows = (
        db.session.query(
            RelayResult.school_id,
            RelayResult.event,
            RelayResult.place,
        )
        .filter(
            RelayResult.meet_id == meet_id,
            RelayResult.place.isnot(None),
            RelayResult.place > 0,
            RelayResult.place <= scoring_limit,
        )
        .all()
    )
    event_groups: Dict[str, List[Tuple[int, int]]] = {}
    for school_id_value, event_name, place in list(individual_rows) + list(relay_rows):
        event_groups.setdefault(event_name, []).append((school_id_value, place))

    points_by_school: Dict[int, float] = {}
    points_by_school_event: Dict[int, Dict[str, float]] = {}
    for event_name, placements in event_groups.items():
        by_place: Dict[int, List[int]] = {}
        for school_id_value, place in placements:
            by_place.setdefault(place, []).append(school_id_value)

        for actual_place, tied_schools in by_place.items():
            scoring_slots = [
                place_number
                for place_number in range(actual_place, actual_place + len(tied_schools))
                if place_number in points_table
            ]
            points_value = (
                sum(points_table[place_number] for place_number in scoring_slots) / len(tied_schools)
                if scoring_slots
                else 0
            )
            for school_id_value in tied_schools:
                points_by_school[school_id_value] = points_by_school.get(school_id_value, 0) + points_value
                per_event = points_by_school_event.setdefault(school_id_value, {})
                per_event[event_name] = per_event.get(event_name, 0.0) + points_value

    participants = {
        row[0]
        for row in db.session.query(Athlete.school_id)
        .join(AthleteResult, AthleteResult.athlete_id == Athlete.athlete_id)
        .filter(AthleteResult.meet_id == meet_id)
        .distinct()
        .all()
    }
    participants.update(
        row[0]
        for row in db.session.query(RelayResult.school_id)
        .filter(RelayResult.meet_id == meet_id)
        .distinct()
        .all()
    )

    school_names = dict(
        db.session.query(School.school_id, School.school_name)
        .filter(School.school_id.in_(participants))
        .all()
    ) if participants else {}

    ranked = {}
    ordered = sorted(
        participants,
        key=lambda school_id_value: (
            -points_by_school.get(school_id_value, 0),
            school_names.get(school_id_value, ""),
        ),
    )
    for index, school_id_value in enumerate(ordered, start=1):
        ranked[school_id_value] = {
            "points": round(points_by_school.get(school_id_value, 0), 1),
            "rank": index,
            "total_teams": len(participants),
            "points_by_event": {
                event: round(value, 1)
                for event, value in points_by_school_event.get(school_id_value, {}).items()
            },
        }
    return ranked


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


# Half-width of the like-size peer window: each school is compared against the 30
# schools nearest below and 30 nearest above it by enrollment, with the shortfall
# pushed to the other side at the edges of the distribution.
#
# 60 rather than something larger because enrollment is the dominant confound in
# the composite (statewide correlation 0.745) and only a tight window removes it:
# inside a 60-window the residual enrollment/score correlation falls to ~0.20,
# while a 200-window still leaves ~0.49 -- and with roughly 400 ranked schools a
# 200-window is half the field, so ~49% of schools would share a clamped,
# uncentered peer set instead of a genuinely local one.
PEER_WINDOW_HALF = 30


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


def _prior_season_status_for_best_mark(
    *,
    school_id: int,
    event_name: str,
    current_year: int,
    current_row: Optional[Dict[str, Any]],
    history: Dict[Tuple[int, str, int], Dict[str, Any]],
):
    if not current_row:
        return {
            "label": "—",
            "tone": "muted",
            "tooltip": "No postseason mark this season.",
        }

    prior_years = sorted(
        [
            year
            for candidate_school_id, candidate_event, year in history.keys()
            if candidate_school_id == school_id and candidate_event == event_name and year < current_year
        ],
        reverse=True,
    )
    if not prior_years:
        if current_year == MIN_RECORDS_YEAR:
            return {
                "label": "—",
                "tone": "muted",
                "tooltip": f"No earlier covered postseason season before {current_year}.",
            }
        return {
            "label": "New",
            "tone": "accent",
            "tooltip": f"First covered postseason mark for this event: {current_year} ({current_row['result_display']}).",
        }

    prior_year = prior_years[0]
    prior_row = history[(school_id, event_name, prior_year)]
    lower_is_better = _is_lower_better(current_row["event_type"])
    if current_row["result_value"] == prior_row["result_value"]:
        label = "Same"
        tone = "muted"
    elif (lower_is_better and current_row["result_value"] < prior_row["result_value"]) or (
        not lower_is_better and current_row["result_value"] > prior_row["result_value"]
    ):
        label = "Improved"
        tone = "success"
    else:
        label = "—"
        tone = "muted"

    return {
        "label": label,
        "tone": tone,
        "tooltip": f"Compared with {prior_year}: {current_row['result_display']} vs {prior_row['result_display']}.",
        "compared_year": prior_year,
        "prior_mark": prior_row["result_display"],
    }


def _format_school_qualifier_row(row: Dict[str, Any], stage_name: str, event_name: Optional[str] = None):
    source_label = row.get("sectional_host")
    if row.get("sectional_num") is not None and not source_label:
        source_label = f"{stage_name} feed {row.get('sectional_num')}"
    return {
        "event": row.get("event") or event_name,
        "mark": row.get("result") or "—",
        "place": row.get("place"),
        "qualifier_type": row.get("qualifier_type"),
        "source_label": source_label,
        "school_id": row.get("school_id"),
        "school_name": row.get("school"),
        "athlete_id": row.get("athlete_id"),
        "name": row.get("name") or row.get("school"),
        "lineup": [],
    }


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


# -----------------------------------------------------------------------------
# Regional qualifier list (dynamic, current-year focused)
# -----------------------------------------------------------------------------

CURRENT_QUALIFIER_YEAR = 2026
REGIONAL_SECTIONAL_GROUPS = {
    1: (1, 2, 3, 4),
    2: (5, 6, 7, 8),
    3: (9, 10, 11, 12),
    4: (13, 14, 15, 16),
    5: (17, 18, 19, 20),
    6: (21, 22, 23, 24),
    7: (25, 26, 27, 28),
    8: (29, 30, 31, 32),
}
REGIONAL_TARGET_FIELD_SIZE = 16
STATE_TARGET_FIELD_SIZE_BY_YEAR = {
    2023: 27,
    2024: 27,
    2025: 27,
    2026: 30,
}


def _state_target_field_size(year: int) -> int:
    try:
        parsed_year = int(year)
    except (TypeError, ValueError):
        parsed_year = CURRENT_QUALIFIER_YEAR

    if parsed_year >= 2026:
        return 30
    return STATE_TARGET_FIELD_SIZE_BY_YEAR.get(parsed_year, 27)


def _regional_events_for_gender(gender: str):
    events = [
        "100 Meters",
        "200 Meters",
        "400 Meters",
        "800 Meters",
        "1600 Meters",
        "3200 Meters",
        "300 Hurdles",
        "High Jump",
        "Long Jump",
        "Shot Put",
        "Discus",
        "Pole Vault",
        "4 x 100 Relay",
        "4 x 400 Relay",
        "4 x 800 Relay",
    ]
    events.insert(6, "110 Hurdles" if gender == "Boys" else "100 Hurdles")
    return events


@lru_cache(maxsize=32)
def _ihsaa_regional_hosts(year: int, gender: str):
    gender_slug = "boys" if str(gender).strip().lower() == "boys" else "girls"
    parsed_year = int(year)
    season_slug = f"{parsed_year - 1}-{parsed_year % 100:02d}"
    url = f"https://www.ihsaa.org/sports/{gender_slug}/track-field/{season_slug}-tournament?round=regionals"

    try:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return {}

    hosts = {}

    # The tournament page includes sectional and regional rows together.
    # Regional rows include "Sectional Host:" in their text.
    paragraphs = re.findall(r"<p[^>]*>.*?</p>", html, flags=re.IGNORECASE | re.DOTALL)
    for block in paragraphs:
        lower_block = block.lower()
        if "in.milesplit.com" not in lower_block or "/results" not in lower_block:
            continue
        if "sectional host:" not in lower_block:
            continue

        text = re.sub(r"<[^>]+>", " ", block)
        text = html_lib.unescape(re.sub(r"\s+", " ", text)).strip()

        before_tickets = text.split("Tickets", 1)[0].strip()
        match = re.match(r"^(\d{1,2})\.\s*(.+)$", before_tickets)
        if not match:
            continue

        regional_num = int(match.group(1))
        host = re.sub(
            r"\s+\d{1,2}(?::\d{2})?\s*[ap]m(?:\s*[A-Z]{2})?$",
            "",
            match.group(2).strip(),
            flags=re.IGNORECASE,
        ).strip(" -")
        host = re.sub(r"\s*\(\d+\)\s*$", "", host).strip()
        if host and regional_num not in hosts:
            hosts[regional_num] = host

    return hosts


@lru_cache(maxsize=32)
def _ihsaa_sectional_hosts(year: int, gender: str):
    gender_slug = "boys" if str(gender).strip().lower() == "boys" else "girls"
    parsed_year = int(year)
    season_slug = f"{parsed_year - 1}-{parsed_year % 100:02d}"
    url = f"https://www.ihsaa.org/sports/{gender_slug}/track-field/{season_slug}-tournament?round=sectionals"

    try:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return {}

    hosts = {}
    paragraphs = re.findall(r"<p[^>]*>.*?</p>", html, flags=re.IGNORECASE | re.DOTALL)
    for block in paragraphs:
        lower_block = block.lower()
        if "in.milesplit.com" not in lower_block or "/results" not in lower_block:
            continue
        if "schools:" not in lower_block:
            continue

        text = re.sub(r"<[^>]+>", " ", block)
        text = html_lib.unescape(re.sub(r"\s+", " ", text)).strip()

        before_tickets = text.split("Tickets", 1)[0].strip()
        match = re.match(r"^(\d{1,2})\.\s*(.+)$", before_tickets)
        if not match:
            continue

        sectional_num = int(match.group(1))
        host = re.sub(
            r"\s+\d{1,2}(?::\d{2})?\s*[ap]m(?:\s*[A-Z]{2})?$",
            "",
            match.group(2).strip(),
            flags=re.IGNORECASE,
        ).strip(" -")
        host = re.sub(r"\s*\(\d+\)\s*$", "", host).strip()

        if 1 <= sectional_num <= 32 and host and sectional_num not in hosts:
            hosts[sectional_num] = host

    return hosts


def _display_sectional_host(host: Optional[str], meet_num: Optional[int], year: int, gender: str) -> str:
    raw_host = (host or "").strip()
    if raw_host and not re.match(r"^IHSAA\s+Sectional\s+\d+", raw_host, flags=re.IGNORECASE):
        return re.sub(r"\s*\(\d+\)\s*$", "", raw_host).strip()

    if meet_num is not None:
        fallback_host = _ihsaa_sectional_hosts(year, gender).get(int(meet_num))
        if fallback_host:
            return fallback_host

    if raw_host:
        return raw_host
    if meet_num is not None:
        return f"Sectional {meet_num}"
    return ""


def _regional_hosts_for_year(year: int, gender: str):
    regional_hosts = get_configured_regional_hosts(year, gender)

    regional_host_rows = (
        db.session.query(Meet.meet_num, Meet.host)
        .filter(
            Meet.meet_type == "Regional",
            Meet.year == year,
            Meet.gender == gender,
            Meet.meet_num.isnot(None),
        )
        .all()
    )

    for meet_num, host in regional_host_rows:
        if meet_num is None:
            continue
        if host:
            regional_hosts.setdefault(meet_num, host)

    # Fill any remaining gaps from IHSAA tournament hosts.
    for meet_num, host in _ihsaa_regional_hosts(year, gender).items():
        regional_hosts.setdefault(meet_num, host)

    return regional_hosts


def _regional_group_status(year: int, gender: str):
    meet_nums = (
        db.session.query(Meet.meet_num)
        .filter(
            Meet.meet_type == "Sectional",
            Meet.year == year,
            Meet.gender == gender,
            Meet.meet_num.isnot(None),
        )
        .distinct()
        .all()
    )
    loaded = {row[0] for row in meet_nums if row[0] is not None}

    regional_hosts = _regional_hosts_for_year(year, gender)

    regionals = []
    import sys
    logger.info(f"Loaded sectionals for {year} {gender}: {sorted(list(loaded))}")

    for regional_num, feeders in REGIONAL_SECTIONAL_GROUPS.items():
        feeder_set = set(feeders)
        completed = sorted(feeder_set.intersection(loaded))
        missing = sorted(feeder_set.difference(loaded))
        logger.info(f"Regional {regional_num}: completed={completed}, missing={missing}")
        if len(completed) == len(feeders):
            status = "ready"
        elif completed:
            status = "not_ready"
        else:
            status = "not_ready"

        regionals.append(
            {
                "regional_num": regional_num,
                "status": status,
                "completed_sectionals": len(completed),
                "total_sectionals": len(feeders),
                "missing_sectionals": missing,
                "loaded_sectionals": completed,
                "regional_host": regional_hosts.get(regional_num),
            }
        )

    total_completed = sum(item["completed_sectionals"] for item in regionals)
    ready_count = sum(1 for item in regionals if item["status"] == "ready")

    return {
        "year": year,
        "gender": gender,
        "ready_regionals": ready_count,
        "total_regionals": len(REGIONAL_SECTIONAL_GROUPS),
        "completed_sectionals": total_completed,
        "total_sectionals": 32,
        "generated_at": func.now(),
        "regionals": regionals,
    }


def get_regional_qualifiers_status(gender: str, year: int = CURRENT_QUALIFIER_YEAR):
    clean_gender = (gender or "").strip().title()
    if clean_gender not in ("Boys", "Girls"):
        raise ValueError("gender must be Boys or Girls")

    payload = _regional_group_status(year, clean_gender)
    payload["generated_at"] = str(db.session.query(func.datetime("now")).scalar())
    payload["disclaimer"] = "Unofficial until IHSAA confirmation."
    return payload


def _state_group_status(year: int, gender: str):
    meet_nums = (
        db.session.query(Meet.meet_num)
        .filter(
            Meet.meet_type == "Regional",
            Meet.year == year,
            Meet.gender == gender,
            Meet.meet_num.isnot(None),
        )
        .distinct()
        .all()
    )
    loaded = {row[0] for row in meet_nums if row[0] is not None}

    regional_hosts = _regional_hosts_for_year(year, gender)

    state_host_row = (
        db.session.query(Meet.host)
        .filter(
            Meet.meet_type == "State",
            Meet.year == year,
            Meet.gender == gender,
            Meet.host.isnot(None),
        )
        .first()
    )
    state_host = state_host_row[0] if state_host_row else ""

    all_regionals = sorted(REGIONAL_SECTIONAL_GROUPS.keys())
    loaded_regionals = [regional_num for regional_num in all_regionals if regional_num in loaded]
    missing_regionals = [regional_num for regional_num in all_regionals if regional_num not in loaded]
    ready = len(loaded_regionals) == len(all_regionals)

    return {
        "year": year,
        "gender": gender,
        "status": "ready" if ready else "pending",
        "ready_regionals": len(loaded_regionals),
        "total_regionals": len(all_regionals),
        "completed_regionals": len(loaded_regionals),
        "missing_regionals": missing_regionals,
        "loaded_regionals": loaded_regionals,
        "regional_hosts": regional_hosts,
        "state_host": state_host,
        "generated_at": func.now(),
    }


def get_state_qualifiers_status(gender: str, year: int = CURRENT_QUALIFIER_YEAR):
    clean_gender = (gender or "").strip().title()
    if clean_gender not in ("Boys", "Girls"):
        raise ValueError("gender must be Boys or Girls")

    payload = _state_group_status(year, clean_gender)
    payload["generated_at"] = str(db.session.query(func.datetime("now")).scalar())
    payload["disclaimer"] = "Unofficial until IHSAA confirmation."
    return payload


def _extend_to_cutoff_with_ties(rows, target_count):
    def _result_value(item):
        if isinstance(item, dict):
            return item.get("result2")
        return getattr(item, "result2", None)

    if target_count <= 0:
        return []
    if len(rows) <= target_count:
        return rows[:target_count]

    selected = list(rows[:target_count])
    last_value = _result_value(selected[-1])
    idx = target_count
    while idx < len(rows) and _result_value(rows[idx]) == last_value:
        selected.append(rows[idx])
        idx += 1
    return selected


def _missing_auto_slots_by_meet(rows, cutoff_place: int = 3):
    """Return placeholder slots needed per meet, handling ties correctly.

    MileSplit place labels can skip a place when there is a tie (for example,
    1st, 2nd, 2nd, no 3rd). In that case, there are already three automatic
    qualifiers represented, so no placeholder should be added.
    """
    meet_data = {}

    for row in rows:
        meet_num_raw = getattr(row, "meet_num", None)
        if meet_num_raw is None:
            continue

        try:
            meet_num = int(meet_num_raw)
        except (TypeError, ValueError):
            continue

        if meet_num not in meet_data:
            meet_data[meet_num] = {
                "top_count": 0,
                "places": set(),
                "host": getattr(row, "host", None),
            }

        place_raw = getattr(row, "place", None)
        try:
            place = int(place_raw)
        except (TypeError, ValueError):
            continue

        if 1 <= place <= cutoff_place:
            meet_data[meet_num]["top_count"] += 1
            meet_data[meet_num]["places"].add(place)

    missing = []
    for meet_num in sorted(meet_data.keys()):
        top_count = meet_data[meet_num]["top_count"]
        missing_slots = max(0, cutoff_place - top_count)
        if missing_slots == 0:
            continue

        missing_places = [
            place for place in range(1, cutoff_place + 1)
            if place not in meet_data[meet_num]["places"]
        ]
        while len(missing_places) < missing_slots:
            missing_places.append(cutoff_place)

        for place in missing_places[:missing_slots]:
            missing.append((meet_num, place, meet_data[meet_num]["host"]))

    return missing


def _qualifier_sort_key(row, lower_is_better: bool):
    value = row.get("result2")
    if value is None:
        return float("inf") if lower_is_better else float("-inf")
    return value


def _compute_event_qualifiers(
    event_name: str,
    gender: str,
    year: int,
    feeder_meet_nums: tuple,
    source_meet_type: str = "Sectional",
    target_field_size: int = REGIONAL_TARGET_FIELD_SIZE,
):
    event_type = _get_event_types_map().get(event_name, "Track")
    lower_is_better = event_type != "Field"

    if "Relay" in event_name:
        rows = (
            db.session.query(
                RelayResult.school_id.label("school_id"),
                School.school_name.label("school_name"),
                RelayResult.event.label("event"),
                RelayResult.result.label("result"),
                RelayResult.result2.label("result2"),
                RelayResult.place.label("place"),
                Meet.host.label("host"),
                Meet.meet_num.label("meet_num"),
            )
            .join(Meet, RelayResult.meet_id == Meet.meet_id)
            .join(School, RelayResult.school_id == School.school_id)
            .filter(
                Meet.meet_type == source_meet_type,
                Meet.year == year,
                Meet.gender == gender,
                Meet.meet_num.in_(feeder_meet_nums),
                RelayResult.event == event_name,
                RelayResult.result2.isnot(None),
                RelayResult.place.isnot(None),
            )
            .all()
        )

        # Detect which sectionals are missing the event entirely
        present_meet_nums = {row.meet_num for row in rows}
        missing_event_meet_nums = set(feeder_meet_nums) - present_meet_nums
        # Get host info for missing sectionals
        host_map = {row.meet_num: row.host for row in rows}
        for meet_num in missing_event_meet_nums:
            host_map.setdefault(meet_num, None)

        top3 = [row for row in rows if row.place is not None and row.place <= 3]
        missing_top3 = _missing_auto_slots_by_meet(rows)
        others = [row for row in rows if row.place is not None and row.place > 3]
        others_sorted = sorted(others, key=lambda row: row.result2, reverse=not lower_is_better)

        standard_qualifiers = [
            row for row in others_sorted
            if meets_state_standard(row.result2, gender, event_name, event_type, year=year)
        ]
        selected_school_ids = {row.school_id for row in top3}
        selected_school_ids.update(row.school_id for row in standard_qualifiers)

        remaining = [row for row in others_sorted if row.school_id not in selected_school_ids]
        auto_slots = len(top3) + len(missing_top3) + 3 * len(missing_event_meet_nums)
        needed_for_field_size = max(0, target_field_size - (auto_slots + len(standard_qualifiers)))
        fill_qualifiers = _extend_to_cutoff_with_ties(remaining, needed_for_field_size)

        formatted = []
        for row in top3:
            met_standard = meets_state_standard(row.result2, gender, event_name, event_type, year=year)
            formatted.append(
                {
                    "event": row.event,
                    "event_type": event_type,
                    "name": None,
                    "grade": None,
                    "school": row.school_name,
                    "school_id": row.school_id,
                    "result": row.result,
                    "result2": row.result2,
                    "place": row.place,
                    "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                    "sectional_num": row.meet_num,
                    "met_standard": met_standard,
                    "qualifier_type": "auto",
                    "is_callback": False,
                }
            )

        for meet_num, place, host in missing_top3:
            formatted.append(
                {
                    "event": event_name,
                    "event_type": event_type,
                    "name": None,
                    "grade": None,
                    "school": "-",
                    "result": "-",
                    "result2": None,
                    "place": place,
                    "sectional_host": _display_sectional_host(host, meet_num, year, gender),
                    "sectional_num": meet_num,
                    "met_standard": False,
                    "qualifier_type": "auto-missing",
                    "is_callback": False,
                    "is_placeholder": True,
                }
            )

        # Add placeholders for sectionals missing the event entirely
        for meet_num in missing_event_meet_nums:
            for place in (1, 2, 3):
                formatted.append(
                    {
                        "event": event_name,
                        "event_type": event_type,
                        "name": None,
                        "grade": None,
                        "school": "-",
                        "result": "-",
                        "result2": None,
                        "place": place,
                        "sectional_host": _display_sectional_host(host_map.get(meet_num), meet_num, year, gender),
                        "sectional_num": meet_num,
                        "met_standard": False,
                        "qualifier_type": "auto-missing",
                        "is_callback": False,
                        "is_placeholder": True,
                    }
                )

        for row in standard_qualifiers:
            formatted.append(
                {
                    "event": row.event,
                    "event_type": event_type,
                    "name": None,
                    "grade": None,
                    "school": row.school_name,
                    "school_id": row.school_id,
                    "result": row.result,
                    "result2": row.result2,
                    "place": row.place,
                    "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                    "sectional_num": row.meet_num,
                    "met_standard": True,
                    "qualifier_type": "standard",
                    "is_callback": False,
                }
            )

        for row in fill_qualifiers:
            formatted.append(
                {
                    "event": row.event,
                    "event_type": event_type,
                    "name": None,
                    "grade": None,
                    "school": row.school_name,
                    "school_id": row.school_id,
                    "result": row.result,
                    "result2": row.result2,
                    "place": row.place,
                    "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                    "sectional_num": row.meet_num,
                    "met_standard": False,
                    "qualifier_type": "fill",
                    "is_callback": True,
                }
            )

        return sorted(formatted, key=lambda row: _qualifier_sort_key(row, lower_is_better), reverse=not lower_is_better)

    rows = (
        db.session.query(
            AthleteResult.athlete_id.label("athlete_id"),
            Athlete.first.label("first"),
            Athlete.last.label("last"),
            Athlete.school_id.label("school_id"),
            AthleteResult.grade.label("grade"),
            School.school_name.label("school_name"),
            AthleteResult.event.label("event"),
            AthleteResult.result.label("result"),
            AthleteResult.result2.label("result2"),
            AthleteResult.place.label("place"),
            Meet.host.label("host"),
            Meet.meet_num.label("meet_num"),
        )
        .join(Athlete, AthleteResult.athlete_id == Athlete.athlete_id)
        .join(School, Athlete.school_id == School.school_id)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            Meet.meet_type == source_meet_type,
            Meet.year == year,
            Meet.gender == gender,
            Meet.meet_num.in_(feeder_meet_nums),
            AthleteResult.event == event_name,
            AthleteResult.result_type == "Final",
            AthleteResult.result2.isnot(None),
            AthleteResult.place.isnot(None),
        )
        .all()
    )

    # Detect which sectionals are missing the event entirely (individual events)
    present_meet_nums = {row.meet_num for row in rows}
    missing_event_meet_nums = set(feeder_meet_nums) - present_meet_nums
    # Get host info for missing sectionals
    host_map = {row.meet_num: row.host for row in rows}
    for meet_num in missing_event_meet_nums:
        host_map.setdefault(meet_num, None)

    top3 = [row for row in rows if row.place is not None and row.place <= 3]
    missing_top3 = _missing_auto_slots_by_meet(rows)
    others = [row for row in rows if row.place is not None and row.place > 3]
    others_sorted = sorted(others, key=lambda row: row.result2, reverse=not lower_is_better)

    standard_qualifiers = [
        row for row in others_sorted
        if meets_state_standard(row.result2, gender, event_name, event_type, year=year)
    ]
    selected_athlete_ids = {row.athlete_id for row in top3}
    selected_athlete_ids.update(row.athlete_id for row in standard_qualifiers)

    remaining = [row for row in others_sorted if row.athlete_id not in selected_athlete_ids]
    # Count placeholders as auto-qualifiers for callback math
    num_missing_event_placeholders = 3 * len(missing_event_meet_nums)
    auto_slots = len(top3) + len(missing_top3) + num_missing_event_placeholders
    needed_for_field_size = max(0, target_field_size - (auto_slots + len(standard_qualifiers)))
    fill_qualifiers = _extend_to_cutoff_with_ties(remaining, needed_for_field_size)

    formatted = []
    for row in top3:
        met_standard = meets_state_standard(row.result2, gender, event_name, event_type, year=year)
        formatted.append(
            {
                "event": row.event,
                "event_type": event_type,
                "name": f"{(row.last or '').strip()}, {(row.first or '').strip()}".strip(", "),
                "athlete_id": row.athlete_id,
                "grade": row.grade,
                "school": row.school_name,
                "school_id": row.school_id,
                "result": row.result,
                "result2": row.result2,
                "place": row.place,
                "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                "sectional_num": row.meet_num,
                "met_standard": met_standard,
                "qualifier_type": "auto",
                "is_callback": False,
            }
        )

    for meet_num, place, host in missing_top3:
        formatted.append(
            {
                "event": event_name,
                "event_type": event_type,
                "name": "Missing on MileSplit",
                "grade": "-",
                "school": "-",
                "result": "-",
                "result2": None,
                "place": place,
                "sectional_host": _display_sectional_host(host, meet_num, year, gender),
                "sectional_num": meet_num,
                "met_standard": False,
                "qualifier_type": "auto-missing",
                "is_callback": False,
                "is_placeholder": True,
            }
        )

    # Add placeholders for sectionals missing the event entirely (individual events)
    for meet_num in missing_event_meet_nums:
        for place in (1, 2, 3):
            formatted.append(
                {
                    "event": event_name,
                    "event_type": event_type,
                    "name": "Missing on MileSplit",
                    "grade": "-",
                    "school": "-",
                    "result": "-",
                    "result2": None,
                    "place": place,
                    "sectional_host": _display_sectional_host(host_map.get(meet_num), meet_num, year, gender),
                    "sectional_num": meet_num,
                    "met_standard": False,
                    "qualifier_type": "auto-missing",
                    "is_callback": False,
                    "is_placeholder": True,
                }
            )

    for row in standard_qualifiers:
        formatted.append(
            {
                "event": row.event,
                "event_type": event_type,
                "name": f"{(row.last or '').strip()}, {(row.first or '').strip()}".strip(", "),
                "athlete_id": row.athlete_id,
                "grade": row.grade,
                "school": row.school_name,
                "school_id": row.school_id,
                "result": row.result,
                "result2": row.result2,
                "place": row.place,
                "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                "sectional_num": row.meet_num,
                "met_standard": True,
                "qualifier_type": "standard",
                "is_callback": False,
            }
        )

    for row in fill_qualifiers:
        formatted.append(
            {
                "event": row.event,
                "event_type": event_type,
                "name": f"{(row.last or '').strip()}, {(row.first or '').strip()}".strip(", "),
                "athlete_id": row.athlete_id,
                "grade": row.grade,
                "school": row.school_name,
                "school_id": row.school_id,
                "result": row.result,
                "result2": row.result2,
                "place": row.place,
                "sectional_host": _display_sectional_host(row.host, row.meet_num, year, gender),
                "sectional_num": row.meet_num,
                "met_standard": False,
                "qualifier_type": "fill",
                "is_callback": True,
            }
        )

    return sorted(formatted, key=lambda row: _qualifier_sort_key(row, lower_is_better), reverse=not lower_is_better)


@lru_cache(maxsize=128)
def get_regional_qualifiers(gender: str, regional_num: int, year: int = CURRENT_QUALIFIER_YEAR):
    clean_gender = (gender or "").strip().title()
    if clean_gender not in ("Boys", "Girls"):
        raise ValueError("gender must be Boys or Girls")

    if regional_num not in REGIONAL_SECTIONAL_GROUPS:
        raise ValueError("regional_num must be an integer between 1 and 8")

    status_payload = _regional_group_status(year, clean_gender)
    status_map = {row["regional_num"]: row for row in status_payload["regionals"]}
    regional_status = status_map[regional_num]

    response = {
        "context": {
            "year": year,
            "gender": clean_gender,
            "regional_num": regional_num,
            "status": regional_status["status"],
            "completed_sectionals": regional_status["completed_sectionals"],
            "total_sectionals": regional_status["total_sectionals"],
            "missing_sectionals": regional_status["missing_sectionals"],
            "generated_at": str(db.session.query(func.datetime("now")).scalar()),
            "disclaimer": "Unofficial until IHSAA confirmation.",
        },
        "events": [],
    }


    # Allow predictions for regionals with all feeders present, mark others as pending
    if regional_status["status"] != "ready":
        response["context"]["note"] = "Pending: Not all feeder sectionals are loaded. Predictions below are only shown for completed sectionals."
        # Only show predictions for completed feeders
        feeder_meet_nums = REGIONAL_SECTIONAL_GROUPS[regional_num]
        events = _regional_events_for_gender(clean_gender)
        for event_name in events:
            # Only include results for sectionals that are loaded
            loaded_feeders = tuple(set(feeder_meet_nums).intersection(set(regional_status["loaded_sectionals"])))
            if not loaded_feeders:
                continue
            qualifiers = _compute_event_qualifiers(event_name, clean_gender, year, loaded_feeders)
            response["events"].append(
                {
                    "event": event_name,
                    "event_type": _get_event_types_map().get(event_name, "Track"),
                    "standard_mark": get_state_standard_display(clean_gender, event_name, year),
                    "qualifiers": qualifiers,
                }
            )
        return response

    feeder_meet_nums = REGIONAL_SECTIONAL_GROUPS[regional_num]
    events = _regional_events_for_gender(clean_gender)
    for event_name in events:
        qualifiers = _compute_event_qualifiers(event_name, clean_gender, year, feeder_meet_nums)
        response["events"].append(
            {
                "event": event_name,
                "event_type": _get_event_types_map().get(event_name, "Track"),
                "standard_mark": get_state_standard_display(clean_gender, event_name, year),
                "qualifiers": qualifiers,
            }
        )

    return response


def get_state_qualifiers(gender: str, year: int = CURRENT_QUALIFIER_YEAR):
    clean_gender = (gender or "").strip().title()
    if clean_gender not in ("Boys", "Girls"):
        raise ValueError("gender must be Boys or Girls")

    status_payload = _state_group_status(year, clean_gender)

    response = {
        "context": {
            "year": year,
            "gender": clean_gender,
            "status": status_payload["status"],
            "completed_regionals": status_payload["completed_regionals"],
            "total_regionals": status_payload["total_regionals"],
            "missing_regionals": status_payload["missing_regionals"],
            "generated_at": str(db.session.query(func.datetime("now")).scalar()),
            "disclaimer": "Unofficial until IHSAA confirmation.",
        },
        "events": [],
    }

    if status_payload["status"] != "ready":
        return response

    feeder_meet_nums = tuple(sorted(REGIONAL_SECTIONAL_GROUPS.keys()))
    events = _regional_events_for_gender(clean_gender)
    target_field_size = _state_target_field_size(year)
    for event_name in events:
        qualifiers = _compute_event_qualifiers(
            event_name,
            clean_gender,
            year,
            feeder_meet_nums,
            source_meet_type="Regional",
            target_field_size=target_field_size,
        )
        response["events"].append(
            {
                "event": event_name,
                "event_type": _get_event_types_map().get(event_name, "Track"),
                "standard_mark": get_state_standard_display(clean_gender, event_name, year),
                "qualifiers": qualifiers,
            }
        )

    return response


# ---------------------------------------------------------------------------
# School dashboard v3 -- coach-facing scorecard.
#
# v3 is additive: it never modifies the v2 functions above, and reuses their
# private helpers so both pages stay in agreement. The design goal is that every
# figure on the page is a real mark, a real rank, or real meet points -- no
# composite scores, which repeatedly proved to need a footnote to be read right.
# ---------------------------------------------------------------------------

_H2H_INDIVIDUAL_POINTS = (5, 3, 1)
_H2H_RELAY_POINTS = (5,)


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


def _score_h2h_meet(current_entries, prior_entries):
    """Score two seasons of the same school against each other as a dual meet.

    5-3-1 for individual events, 5-0 for relays. An event a side did not contest
    simply yields it no points -- the vacancy costs the same in every event,
    which is exactly how it works at a real meet.
    """
    points_current = 0.0
    points_prior = 0.0
    events_won = 0
    events_lost = 0
    uncontested_points = 0.0

    for event_name in sorted(set(current_entries) | set(prior_entries)):
        mine = current_entries.get(event_name, [])
        theirs = prior_entries.get(event_name, [])
        sample = (mine or theirs)[0]
        event_type = sample.get("event_type") or CONST.EVENT_TYPE.TRACK
        lower_is_better = _is_lower_better(event_type)

        field = [(row["result_value"], "current") for row in mine]
        field += [(row["result_value"], "prior") for row in theirs]
        field.sort(key=lambda item: item[0], reverse=not lower_is_better)

        table = _H2H_RELAY_POINTS if event_name in CONST.EVENT.ALL_RELAY else _H2H_INDIVIDUAL_POINTS
        event_current = 0.0
        event_prior = 0.0

        # Equal marks split the combined value of the places they occupy, the same
        # convention as _compute_cumulative_points. Without this, a stable sort hands
        # every tie to whichever season is listed first, which would inflate the
        # current season against every past one -- a season scored against itself
        # would "win" instead of tying.
        index = 0
        while index < len(field):
            value = field[index][0]
            tied = [entry for entry in field[index:] if entry[0] == value]
            slots = [
                table[place] for place in range(index, index + len(tied)) if place < len(table)
            ]
            if slots:
                share = sum(slots) / len(tied)
                for _value, side in tied:
                    if side == "current":
                        event_current += share
                    else:
                        event_prior += share
            index += len(tied)

        # Points scored in events the other season did not contest at all -- worth
        # reporting separately so a win is not misread as "everyone ran faster".
        if mine and not theirs:
            uncontested_points += event_current

        points_current += event_current
        points_prior += event_prior
        if event_current > event_prior:
            events_won += 1
        elif event_prior > event_current:
            events_lost += 1

    return {
        "points_for": round(points_current, 1),
        "points_against": round(points_prior, 1),
        "events_won": events_won,
        "events_lost": events_lost,
        "uncontested_points": round(uncontested_points, 1),
    }


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


# Sectional -> Regional -> State. Advancement is measured at whichever stage an
# athlete's season actually ended, so the same column means one thing on every row.
# A complete postseason: 32 sectionals, 8 regionals and one state final per gender.
# Every covered season (2023-2026) matches this, so the check is a no-op today and
# exists to keep a season that is still being run out of the dashboard.
_V3_EXPECTED_MEETS = {
    CONST.MEET_TYPE.SECTIONAL: 32,
    CONST.MEET_TYPE.REGIONAL: 8,
    CONST.MEET_TYPE.STATE: 1,
}


# Sectional -> Regional -> State.
_V3_STAGE_ORDER = (
    CONST.MEET_TYPE.SECTIONAL,
    CONST.MEET_TYPE.REGIONAL,
    CONST.MEET_TYPE.STATE,
)

# IHSAA advancement: the top three at each meet qualify automatically, then a fixed
# number of callback slots go to the best remaining marks pooled across the meets
# feeding the next round -- four into a regional (from its four feeder sectionals),
# six into the state finals (pooled statewide).
#
# Both numbers are confirmed by the field sizes that result: 4 sectionals x 3 auto
# + 4 callbacks = 16, the modal regional field, and 8 regionals x 3 + 6 = 30, the
# modal state field. Participation confirms the selection is strictly by mark --
# the top four non-auto marks in a regional group compete 82-96% of the time
# (the same rate as auto qualifiers) while the fifth-best drops to 18-35%.
_V3_AUTO_DEPTH = 3
_V3_CALLBACK_SLOTS = {
    CONST.MEET_TYPE.SECTIONAL: 4,
    CONST.MEET_TYPE.REGIONAL: 6,
}
_V3_SECTIONALS_PER_REGIONAL = 4


def _v4_stage_index(meet_type):
    try:
        return _V3_STAGE_ORDER.index(meet_type)
    except ValueError:
        return -1


def _v4_callback_group(stage, meet_num, event):
    """Which pool an entry competes in for a callback slot.

    Out of a sectional the pool is the four sectionals feeding one regional; out of
    a regional it is the whole state, so the group is the event alone.
    """
    if stage == CONST.MEET_TYPE.SECTIONAL and meet_num:
        regional_num = (meet_num - 1) // _V3_SECTIONALS_PER_REGIONAL + 1
        return (regional_num, event)
    return (None, event)


def _v4_is_better(value, other, lower_is_better):
    return value < other if lower_is_better else value > other


def _v4_easier(first, second, lower_is_better):
    """Of two qualifying marks, the one that is easier to achieve."""
    if first is None:
        return second
    if second is None:
        return first
    return second if _v4_is_better(first, second, lower_is_better) else first


def _v4_advancement_from_rows(rows, next_stage_pairs, pair_of, lower_is_better_of):
    """Where each entry's season ended, and the mark it needed to go further.

    The bar is the easier of two real, observed marks:

    * the **auto** path -- the third-place mark at their own meet, since beating it
      would have earned an automatic spot; and
    * the **callback** path -- the last mark to take a callback slot in their pool.

    The callback line is counted from the top (the Nth best non-auto mark), not up
    from the poorest athlete who turned up. Selection happens on marks before anyone
    withdraws, so counting from the bottom lets a withdrawal soften the bar: in the
    2026 Boys regional-2 3200, two auto qualifiers from one sectional did not run
    and their sectional's 4th and 5th places replaced them at 10:37 and 10:41, while
    the mark that actually took the last callback slot was 9:58.75. Counting from
    the top is immune to that.

    An entry that met its bar but never appeared at the next stage qualified and did
    not compete -- roughly one callback in eight -- so it is reported that way rather
    than being given a gap it never had.
    """
    by_stage: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if _v4_stage_index(row["meet_type"]) < 0:
            continue
        by_stage.setdefault(row["meet_type"], []).append(row)

    # ---- the two lines, per stage that has a next stage ---------------------
    auto_lines: Dict[Tuple[int, str], float] = {}
    callback_lines: Dict[Tuple[str, Tuple[Any, str]], float] = {}

    for stage, stage_rows in by_stage.items():
        stage_index = _v4_stage_index(stage)
        if stage_index >= len(_V3_STAGE_ORDER) - 1:
            continue

        finals = [
            row for row in stage_rows
            if row["result_type"] == CONST.RESULT_TYPE.FINAL
            and row.get("place")
            and row["place"] > 0
            and _is_valid_postseason_mark(row["result_value"], row["event_type"])
        ]

        # Auto line: the mark of the last automatic qualifying place at that meet.
        for row in finals:
            if row["place"] > _V3_AUTO_DEPTH:
                continue
            key = (row["meet_id"], row["event"])
            current = auto_lines.get(key)
            lower_is_better = lower_is_better_of(row)
            # The poorest of the automatic places is the bar to reach them.
            if current is None or _v4_is_better(current, row["result_value"], lower_is_better):
                auto_lines[key] = row["result_value"]

        # Callback line: the Nth best mark among those outside the automatic places.
        slots = _V3_CALLBACK_SLOTS.get(stage)
        pools: Dict[Tuple[Any, str], List[Dict[str, Any]]] = {}
        for row in finals:
            if row["place"] <= _V3_AUTO_DEPTH:
                continue
            group = _v4_callback_group(stage, row.get("meet_num"), row["event"])
            pools.setdefault(group, []).append(row)
        for group, pool in pools.items():
            lower_is_better = lower_is_better_of(pool[0])
            pool.sort(key=lambda item: item["result_value"], reverse=not lower_is_better)
            if not slots:
                continue
            # Fewer contenders than slots means everyone outside the automatic
            # places got in, so the poorest of them is the line.
            index = min(slots, len(pool)) - 1
            callback_lines[(stage, group)] = pool[index]["result_value"]

    # ---- furthest stage reached per entry -----------------------------------
    furthest: Dict[Any, Dict[str, Any]] = {}
    for row in rows:
        stage_index = _v4_stage_index(row["meet_type"])
        if stage_index < 0:
            continue
        pair = pair_of(row)
        current = furthest.get(pair)
        if current is None:
            furthest[pair] = row
            continue
        current_index = _v4_stage_index(current["meet_type"])
        if stage_index > current_index:
            furthest[pair] = row
        elif stage_index == current_index:
            # The final decides advancement, so it wins over a prelim.
            if (row["result_type"] == CONST.RESULT_TYPE.FINAL
                    and current["result_type"] != CONST.RESULT_TYPE.FINAL):
                furthest[pair] = row

    result: Dict[Any, Dict[str, Any]] = {}
    for pair, row in furthest.items():
        stage = row["meet_type"]
        stage_index = _v4_stage_index(stage)
        is_final = row["result_type"] == CONST.RESULT_TYPE.FINAL
        place = row.get("place")
        entry = {
            "final_stage": stage,
            "final_place": place if place and place > 0 else None,
            "final_round": CONST.RESULT_TYPE.FINAL if is_final else CONST.RESULT_TYPE.PRELIM,
            "final_mark_display": row.get("result"),
            "cutoff_display": None,
            "cutoff_path": None,
            "gap_display": None,
            # The raw numbers behind the two displays above. "0.29" in the 100 and
            # "10 inches" in the long jump cannot be ranked against each other,
            # but gap / cutoff can, and that ratio is what lets the dashboard say
            # which entries came closest across unlike events. Parsing it back out
            # of the formatted strings would mean re-reading feet and inches.
            "cutoff_value": None,
            "gap_value": None,
            "qualified_did_not_compete": False,
            "tied_cutoff": False,
        }

        can_advance = stage_index < len(_V3_STAGE_ORDER) - 1
        valid = _is_valid_postseason_mark(row["result_value"], row["event_type"])
        if can_advance and is_final and valid:
            lower_is_better = lower_is_better_of(row)
            auto = auto_lines.get((row["meet_id"], row["event"]))
            group = _v4_callback_group(stage, row.get("meet_num"), row["event"])
            callback = callback_lines.get((stage, group))
            bar = _v4_easier(auto, callback, lower_is_better)

            if bar is not None:
                entry["cutoff_display"] = _format_result_display(bar, row["event_type"])
                entry["cutoff_value"] = bar
                if auto is not None and bar == auto and (
                    callback is None or auto != callback
                ):
                    entry["cutoff_path"] = "auto"
                elif callback is not None and bar == callback:
                    entry["cutoff_path"] = "callback"

                # Strictly better than the bar yet absent from the next stage: they
                # had the mark and did not run it.
                #
                # Equalling the bar is deliberately not treated as qualifying. The
                # vertical jumps move in two-inch steps, so ties on the bar mark are
                # routine -- one 2026 sectional had four boys at 5-8 for places 5,
                # 5, 7 and 8 -- and which of them advanced was settled by misses,
                # which the results do not record. Those rows get the bar with no
                # gap and no claim either way.
                if _v4_is_better(row["result_value"], bar, lower_is_better):
                    entry["qualified_did_not_compete"] = True
                elif row["result_value"] == bar:
                    entry["tied_cutoff"] = True
                else:
                    gap = (
                        row["result_value"] - bar if lower_is_better
                        else bar - row["result_value"]
                    )
                    if gap > 0:
                        entry["gap_display"] = _format_gap_display(gap, row["event_type"])
                        entry["gap_value"] = gap

        result[pair] = entry

    return result


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


def _v4_stage_cells(rows, lower_is_better, event_type):
    """The one mark to show per stage, plus which stage holds the best of them.

    Every stage runs its own rounds, so a sprinter has a prelim and a final at each
    of them. The final is what the stage is judged on, so it wins; a prelim only
    surfaces when the athlete never reached the final, and is marked as such.
    """
    def _valid(row):
        return _is_valid_postseason_mark(row["result_value"], event_type)

    per_stage: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        stage = row.get("meet_type")
        if _v4_stage_index(stage) < 0:
            continue
        current = per_stage.get(stage)
        if current is None:
            per_stage[stage] = row
            continue
        # A real mark beats a sentinel (NT/DQ), a final beats a prelim, and past
        # that the better mark wins. Sentinel rows are kept rather than dropped:
        # a relay that reached the regional and ran NT still reached the regional,
        # and dropping the row made the season look like it ended a round earlier.
        row_valid, current_valid = _valid(row), _valid(current)
        if row_valid != current_valid:
            if row_valid:
                per_stage[stage] = row
            continue
        is_final = row.get("result_type") == CONST.RESULT_TYPE.FINAL
        was_final = current.get("result_type") == CONST.RESULT_TYPE.FINAL
        if is_final and not was_final:
            per_stage[stage] = row
        elif is_final == was_final and row_valid and _v4_is_better(
            row["result_value"], current["result_value"], lower_is_better
        ):
            per_stage[stage] = row

    cells = {}
    best_stage = None
    best_value = None
    for stage, row in per_stage.items():
        has_mark = _valid(row)
        cells[stage] = {
            # The sentinel token itself (NT, DQ) is the honest display: it says
            # what happened, where a blank cell would say they were never there.
            "mark_display": row.get("result") or (
                _format_result_display(row["result_value"], event_type) if has_mark else None
            ),
            "result_value": row["result_value"] if has_mark else None,
            "has_mark": has_mark,
            "place": row.get("place") if row.get("place") and row["place"] > 0 else None,
            "round": row.get("result_type"),
        }
        if has_mark and (
            best_value is None
            or _v4_is_better(row["result_value"], best_value, lower_is_better)
        ):
            best_value = row["result_value"]
            best_stage = stage
    return cells, best_stage, best_value


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


