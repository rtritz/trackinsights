from __future__ import annotations

import re


class Conversion:
    """Utility functions for converting time and distance inputs."""

    time_pattern = re.compile(r"^\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)\s*$")
    distance_pattern = re.compile(
        r"^\s*(?:(?P<feet>\d+)\s*(?:'|ft)\s*)?(?:(?P<inches>\d+(?:\.\d+)?)\s*(?:\"|in)?)?\s*$"
    )

    @staticmethod
    def time_to_seconds(value: str) -> float:
        match = Conversion.time_pattern.match(value)
        if not match:
            raise ValueError(f"Invalid time format: {value!r}")

        parts = match.groups(default="0")
        hours = int(parts[0]) if match.group(2) else 0
        minutes = int(parts[1]) if match.group(2) else int(parts[0] or 0)
        seconds = float(parts[2])

        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def distance_to_inches(value: str) -> float:
        match = Conversion.distance_pattern.match(value)
        if not match:
            raise ValueError(f"Invalid distance format: {value!r}")

        feet = int(match.group("feet") or 0)
        inches = float(match.group("inches") or 0.0)
        return feet * 12 + inches
