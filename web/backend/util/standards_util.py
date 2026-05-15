from __future__ import annotations

from .conversion_util import Conversion


CONVERSION = Conversion()

# 3 Participant Standards used for sectional -> regional advancement.
# Values are year-specific and keyed by the season start year.
_STATE_STANDARD_VALUES = {
    2023: {
        "Boys": {
            "4 x 800 Relay": "7:55.23",
            "110 Hurdles": "14.68",
            "100 Meters": "10.90",
            "1600 Meters": "4:15.36",
            "4 x 100 Relay": "42.23",
            "400 Meters": "48.61",
            "300 Hurdles": "39.35",
            "800 Meters": "1:54.52",
            "200 Meters": "21.95",
            "3200 Meters": "9:09.87",
            "4 x 400 Relay": "3:21.83",
            "Discus": "166' 9\"",
            "Shot Put": "56' 4\"",
            "Long Jump": "22' 1\"",
            "High Jump": "6' 6\"",
            "Pole Vault": "14' 9\"",
        },
        "Girls": {
            "4 x 800 Relay": "9:21.68",
            "100 Hurdles": "14.84",
            "100 Meters": "12.12",
            "1600 Meters": "4:59.62",
            "4 x 100 Relay": "48.27",
            "400 Meters": "57.11",
            "300 Hurdles": "45.86",
            "800 Meters": "2:14.61",
            "200 Meters": "25.23",
            "3200 Meters": "10:57.43",
            "4 x 400 Relay": "3:58.74",
            "Discus": "124' 5\"",
            "Shot Put": "41' 11.25\"",
            "Long Jump": "18' 1.5\"",
            "High Jump": "5' 5\"",
            "Pole Vault": "11' 6\"",
        },
    },
    2024: {
        "Boys": {
            "4 x 800 Relay": "7:58.41",
            "110 Hurdles": "14.77",
            "100 Meters": "11.23",
            "1600 Meters": "4:18.87",
            "4 x 100 Relay": "42.65",
            "400 Meters": "49.40",
            "300 Hurdles": "39.24",
            "800 Meters": "1:56.28",
            "200 Meters": "22.69",
            "3200 Meters": "9:11.15",
            "4 x 400 Relay": "3:22.38",
            "Discus": "158' 8\"",
            "Shot Put": "55' 3.75\"",
            "Long Jump": "21' 8\"",
            "High Jump": "6' 6\"",
            "Pole Vault": "15' 0\"",
        },
        "Girls": {
            "4 x 800 Relay": "9:23.34",
            "100 Hurdles": "15.05",
            "100 Meters": "12.42",
            "1600 Meters": "4:55.90",
            "4 x 100 Relay": "48.44",
            "400 Meters": "57.42",
            "300 Hurdles": "45.03",
            "800 Meters": "2:13.33",
            "200 Meters": "25.42",
            "3200 Meters": "10:37.94",
            "4 x 400 Relay": "3:57.23",
            "Discus": "131' 10\"",
            "Shot Put": "42' 2.25\"",
            "Long Jump": "17' 9.25\"",
            "High Jump": "5' 5\"",
            "Pole Vault": "11' 0\"",
        },
    },
    2025: {
        "Boys": {
            "4 x 800 Relay": "7:56.28",
            "110 Hurdles": "14.77",
            "100 Meters": "11.01",
            "1600 Meters": "4:16.70",
            "4 x 100 Relay": "42.44",
            "400 Meters": "49.07",
            "300 Hurdles": "39.35",
            "800 Meters": "1:55.21",
            "200 Meters": "22.21",
            "3200 Meters": "9:10.91",
            "4 x 400 Relay": "3:21.92",
            "Discus": "161' 4\"",
            "Shot Put": "56' 4\"",
            "Long Jump": "21' 11.5\"",
            "High Jump": "6' 5\"",
            "Pole Vault": "14' 6\"",
        },
        "Girls": {
            "4 x 800 Relay": "9:23.63",
            "100 Hurdles": "14.81",
            "100 Meters": "12.24",
            "1600 Meters": "4:58.87",
            "4 x 100 Relay": "48.41",
            "400 Meters": "57.44",
            "300 Hurdles": "45.44",
            "800 Meters": "2:14.68",
            "200 Meters": "25.34",
            "3200 Meters": "10:47.57",
            "4 x 400 Relay": "3:58.35",
            "Discus": "127' 3\"",
            "Shot Put": "41' 9.25\"",
            "Long Jump": "18' 0.25\"",
            "High Jump": "5' 4\"",
            "Pole Vault": "11' 3\"",
        },
    },
    2026: {
        "Boys": {
            "4 x 800 Relay": "7:55.14",
            "110 Hurdles": "14.62",
            "100 Meters": "10.97",
            "1600 Meters": "4:15.49",
            "4 x 100 Relay": "42.36",
            "400 Meters": "48.87",
            "300 Hurdles": "39.10",
            "800 Meters": "1:55.30",
            "200 Meters": "22.15",
            "3200 Meters": "9:09.20",
            "4 x 400 Relay": "3:21.72",
            "Discus": "165' 8\"",
            "Shot Put": "56' 3.25\"",
            "Long Jump": "22' 3\"",
            "High Jump": "6' 6\"",
            "Pole Vault": "14' 9\"",
        },
        "Girls": {
            "4 x 800 Relay": "9:20.44",
            "100 Hurdles": "14.87",
            "100 Meters": "12.23",
            "1600 Meters": "4:57.56",
            "4 x 100 Relay": "48.05",
            "400 Meters": "57.39",
            "300 Hurdles": "45.07",
            "800 Meters": "2:13.68",
            "200 Meters": "25.20",
            "3200 Meters": "10:45.74",
            "4 x 400 Relay": "3:57.56",
            "Discus": "130' 6\"",
            "Shot Put": "41' 6.75\"",
            "Long Jump": "18' 0\"",
            "High Jump": "5' 5\"",
            "Pole Vault": "11' 3\"",
        },
    },
}

DEFAULT_STATE_STANDARD_YEAR = 2026


def _is_field_event(event_name: str) -> bool:
    return event_name in {"High Jump", "Long Jump", "Shot Put", "Discus", "Pole Vault"}


def _resolve_standard_year(year: int | None) -> int:
    try:
        parsed_year = int(year) if year is not None else DEFAULT_STATE_STANDARD_YEAR
    except (TypeError, ValueError):
        parsed_year = DEFAULT_STATE_STANDARD_YEAR

    if parsed_year not in _STATE_STANDARD_VALUES:
        return DEFAULT_STATE_STANDARD_YEAR
    return parsed_year


def get_state_standard(gender: str, event_name: str, year: int | None = None) -> float | None:
    resolved_year = _resolve_standard_year(year)
    clean_gender = (gender or "").strip().title()
    year_values = _STATE_STANDARD_VALUES.get(resolved_year, {})
    if clean_gender not in year_values:
        return None

    raw_value = year_values[clean_gender].get(event_name)
    if raw_value is None:
        return None

    if _is_field_event(event_name):
        return CONVERSION.distance_to_inches(raw_value)

    return CONVERSION.time_to_seconds(raw_value)


def get_state_standard_display(gender: str, event_name: str, year: int | None = None) -> str | None:
    resolved_year = _resolve_standard_year(year)
    clean_gender = (gender or "").strip().title()
    year_values = _STATE_STANDARD_VALUES.get(resolved_year, {})
    if clean_gender not in year_values:
        return None
    return year_values[clean_gender].get(event_name)


def meets_state_standard(result2: float, gender: str, event_name: str, event_type: str, year: int | None = None) -> bool:
    standard = get_state_standard(gender, event_name, year=year)
    if standard is None:
        return False

    if event_type == "Field":
        return result2 >= standard
    return result2 <= standard
