"""School Dashboard

Shared building blocks for the school page (services/school_page.py)
and the statewide rankings: the event groups and which seasons are covered.
"""
from typing import List, Tuple

from .. import db
from ..models import Athlete, AthleteResult, Meet, RelayResult
from common.const import CONST
from .shared import MIN_RECORDS_YEAR


def _event_groups(gender: str) -> List[Tuple[str, List[str]]]:
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


def _events_for_gender(gender: str) -> List[str]:
    events = []
    for _, group_events in _event_groups(gender):
        events.extend(group_events)
    return events


def _available_years(school_id: int, gender: str) -> List[int]:
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


def _covered_years(gender: str) -> List[int]:
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

