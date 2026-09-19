"""Turning stored values into the strings a page prints.

A mark is stored twice -- `result` as it was recorded, `result2` as a float for
sorting -- and a page needs a third form: the one a reader expects to see, with
the right units, the right precision, and a sensible fallback when the value is
one of the non-numeric sentinels the scraping pipeline writes.

These are pure functions of their arguments. They are the bottom of the
package's dependency order: everything may call them, they call nothing here.
"""
from common.const import CONST


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _format_sectional_name(host, meet_num):
    if host and meet_num:
        return f"{host} (Meet {meet_num})"
    if host:
        return host
    if meet_num:
        return f"Meet {meet_num}"
    return "Unknown Sectional"


def _format_place_label(value):
    numeric = _safe_int(value)
    if numeric is None:
        return value
    return _ordinal(numeric)


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


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
