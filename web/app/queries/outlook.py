"""Outlook

What the season implies about the next one: each athlete's class year,
which tells the school page who is returning.
"""

from functools import lru_cache
from typing import Dict

from .. import db
from ..models import Athlete, AthleteResult, Meet

from common.const import CONST


@lru_cache(maxsize=64)
def _grades_for_season(gender: str, year: int):
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

