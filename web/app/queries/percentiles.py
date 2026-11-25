"""Percentiles

Percentile tables and the percentile query tools.
"""


from .. import db
from ..analytics.percentile_tables import get_percentiles as _percentile_tables

from common.const import CONST

from .shared import (
    DEFAULT_PERCENTILES,
    GRADE_LEVELS,
    PERCENTILE_CHOICES,
    _coerce_sequence,
    _tuple_or_none,
    _unique_events,
)

from .meets import (
    _available_meet_years,
)


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

    # The app's own connection, so the read sits inside the request's
    # transaction rather than opening a second handle to the same file.
    df = _percentile_tables(db.session.connection(), **kwargs)
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

def _format_percentile(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"

