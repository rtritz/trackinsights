"""Shared

Helpers used across every feature: database access, result
resolution, formatting and the constants the rest of the package shares.
"""

import os


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


from urllib.request import Request, urlopen

from sqlalchemy import or_, func, and_, text as sqlalchemy_text

from sqlalchemy.orm import joinedload

from ..models import (
    Athlete,
    School,
    AthleteResult,
    RelayResult,
    Meet,
    Event,
    SchoolEnrollment,
)

from .. import db

from common.conversion import Conversion

from common.regional_hosts import get_configured_regional_hosts

from common.standards import meets_state_standard, get_state_standard_display

from common.const import CONST

from ..analytics.percentiles import get_percentiles as _script_get_percentiles

# Display helpers. These are the bottom of this package's import
# order: everything may call them, they call nothing here.
from .formatting import (  # noqa: F401
    _format_result_display,
)

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

_RELAY_NAME_DELIMITER = re.compile(r"\band\b|&|/|;|,|\+", re.IGNORECASE)

# Fallback constants in case CONST is not available
_FALLBACK_EVENTS = {
    "ALL_TRACK": ["100 Meters", "200 Meters", "400 Meters", "800 Meters", "1600 Meters", "3200 Meters"],
    "ALL_FIELD": ["High Jump", "Long Jump", "Pole Vault", "Shot Put", "Discus"],
    "ALL_GIRLS_HURDLES": ["100 Hurdles", "300 Hurdles"],
    "ALL_BOYS_HURDLES": ["110 Hurdles", "300 Hurdles"],
}

_FALLBACK_GENDERS = ["Boys", "Girls"]

# Points awarded by place for cumulative scoring
_PLACE_POINTS = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}

# State Finals score the top 9 places (3rd=7, not 6th) -- see
# standalone/scripts/calculate_team_scores.py's STATE_SCORING, verified
# against MileSplit's official state team totals.
_STATE_PLACE_POINTS = {1: 10, 2: 8, 3: 7, 4: 6, 5: 5, 6: 4, 7: 3, 8: 2, 9: 1}

MIN_RECORDS_YEAR = 2023


_SCHOOL_LOGO_DIR = os.path.join(CONST.WEB_DIR, "app", "static", CONST.SCHOOL_LOGO_STATIC_SUBDIR)

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

_H2H_INDIVIDUAL_POINTS = (5, 3, 1)

_H2H_RELAY_POINTS = (5,)

# Sectional -> Regional -> State. Advancement is measured at whichever stage an
# athlete's season actually ended, so the same column means one thing on every row.
# A complete postseason: 32 sectionals, 8 regionals and one state final per gender.
# Every covered season (2023-2026) matches this, so the check is a no-op today and
# exists to keep a season that is still being run out of the dashboard.
_EXPECTED_MEETS = {
    CONST.MEET_TYPE.SECTIONAL: 32,
    CONST.MEET_TYPE.REGIONAL: 8,
    CONST.MEET_TYPE.STATE: 1,
}

# Sectional -> Regional -> State.
_STAGE_ORDER = (
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
_AUTO_DEPTH = 3

_CALLBACK_SLOTS = {
    CONST.MEET_TYPE.SECTIONAL: 4,
    CONST.MEET_TYPE.REGIONAL: 6,
}

_SECTIONALS_PER_REGIONAL = 4


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


def _select_best_result_entry(items, event_type):
    if not items:
        return None

    valid = [item for item in items if item[0].result2 is not None]
    if not valid:
        return None

    lower_is_better = _is_lower_better(event_type)
    key_func = lambda pair: pair[0].result2
    return min(valid, key=key_func) if lower_is_better else max(valid, key=key_func)


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


def _count_result_types(entries):
    counts = {}
    for entry in entries:
        label = entry.get("result_type") or "Unknown"
        counts[label] = counts.get(label, 0) + 1
    return counts

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
    so a file's existence at static/<CONST.SCHOOL_LOGO_STATIC_SUBDIR>/
    <school_id>.<CONST.SCHOOL_LOGO_EXT> IS the "has a logo" signal -- no DB
    column needed.
    """
    if not school or school.school_id not in _schools_with_logos():
        return None
    return f"/static/{CONST.SCHOOL_LOGO_STATIC_SUBDIR}/{school.school_id}.{CONST.SCHOOL_LOGO_EXT}"

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

def _is_valid_postseason_mark(result_value, event_type: str) -> bool:
    if result_value is None:
        return False
    if event_type == CONST.EVENT_TYPE.FIELD:
        return result_value > 0
    return 0 < result_value < 9999


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

def _state_target_field_size(year: int) -> int:
    try:
        parsed_year = int(year)
    except (TypeError, ValueError):
        parsed_year = CURRENT_QUALIFIER_YEAR

    if parsed_year >= 2026:
        return 30
    return STATE_TARGET_FIELD_SIZE_BY_YEAR.get(parsed_year, 27)

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

def _callback_group(stage, meet_num, event):
    """Which pool an entry competes in for a callback slot.

    Out of a sectional the pool is the four sectionals feeding one regional; out of
    a regional it is the whole state, so the group is the event alone.
    """
    if stage == CONST.MEET_TYPE.SECTIONAL and meet_num:
        regional_num = (meet_num - 1) // _SECTIONALS_PER_REGIONAL + 1
        return (regional_num, event)
    return (None, event)

def _is_better(value, other, lower_is_better):
    return value < other if lower_is_better else value > other

def _easier(first, second, lower_is_better):
    """Of two qualifying marks, the one that is easier to achieve."""
    if first is None:
        return second
    if second is None:
        return first
    return second if _is_better(first, second, lower_is_better) else first
