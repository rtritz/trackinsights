from __future__ import annotations

import re


class Conversion:
    """Utility functions for converting time and distance marks.

    Handles hand-timed marks with a trailing "h" (e.g. "23.5h") and
    non-numeric sentinel tokens (e.g. "NT", "DNF", "DNS", "DQ") by mapping
    them to the same sentinel values (9999 seconds / 0 inches) the MileSplit
    and TFRRS ingestion pipeline already writes into the database's result2
    column, so scoring/ranking code doesn't need to special-case bad marks
    differently depending on which part of the codebase produced them.
    """

    time_pattern = re.compile(r"^\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)\s*$")
    distance_pattern = re.compile(
        r"^\s*(?:(?P<feet>\d+)\s*(?:'|ft)\s*)?(?:(?P<inches>\d+(?:\.\d+)?)\s*(?:\"|in)?)?\s*$"
    )

    @staticmethod
    def time_to_seconds(value: str) -> float:
        if value is None:
            raise ValueError("Invalid time format: None")

        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError(f"Invalid time format: {value!r}")

        if cleaned.isalpha():
            return 9999.0

        if cleaned[-1] in ("h", "H"):
            cleaned = cleaned[:-1]

        match = Conversion.time_pattern.match(cleaned)
        if not match:
            raise ValueError(f"Invalid time format: {value!r}")

        parts = match.groups(default="0")
        hours = int(parts[0]) if match.group(2) else 0
        minutes = int(parts[1]) if match.group(2) else int(parts[0] or 0)
        seconds = float(parts[2])

        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def distance_to_inches(value: str) -> float:
        if value is None:
            raise ValueError("Invalid distance format: None")

        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError(f"Invalid distance format: {value!r}")

        if cleaned.isalpha():
            return 0.0

        match = Conversion.distance_pattern.match(cleaned)
        if not match:
            raise ValueError(f"Invalid distance format: {value!r}")

        feet = int(match.group("feet") or 0)
        inches = float(match.group("inches") or 0.0)
        return feet * 12 + inches

    @staticmethod
    def inches_to_distance(total_inches):
        """Format a total-inches Decimal as a "F' I\"" distance string.

        Only used against Decimal values returned by
        Database.get_state_standard() (see standalone/notebooks/Qualifier
        List.ipynb) — total_inches is expected to be a decimal.Decimal.
        """
        feet = total_inches // 12
        inches = total_inches % 12

        if inches == inches.to_integral_value():
            inches_str = f"{int(inches)}\""
        else:
            inches_str = f"{inches:.2f}\"".rstrip('0').rstrip('.')

        return f"{int(feet)}' {inches_str}"

    @staticmethod
    def seconds_to_time(total_seconds):
        """Format a total-seconds Decimal as a "M:SS.ss" time string.

        Only used against Decimal values returned by
        Database.get_state_standard() (see standalone/notebooks/Qualifier
        List.ipynb) — total_seconds is expected to be a decimal.Decimal.
        """
        minutes = int(total_seconds) // 60
        seconds = total_seconds % 60

        if seconds == seconds.to_integral_value():
            seconds_str = f"{int(seconds)}"
        else:
            seconds_str = f"{seconds:.2f}"

        if minutes == 0:
            return f"{seconds_str}"
        else:
            return f"{minutes}:{seconds_str}"
