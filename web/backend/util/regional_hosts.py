"""Manual regional host mappings used before dynamic fallbacks."""

from typing import Dict, Tuple

# Keys: (year, gender)
# Values: {regional_num: host_name}
REGIONAL_HOSTS_BY_YEAR_GENDER: Dict[Tuple[int, str], Dict[int, str]] = {
    (2026, "Girls"): {
        1: "Portage",
        2: "Goshen",
        3: "Carroll (Fort Wayne)",
        4: "Lafayette Jefferson",
        5: "Ben Davis",
        6: "Greenfield-Central",
        7: "Bloomington South",
        8: "Evansville Central",
    },
    (2026, "Boys"): {
        1: "Valparaiso",
        2: "Warsaw Community",
        3: "Carroll (Fort Wayne)",
        4: "Lafayette Jefferson",
        5: "Plainfield",
        6: "Greenfield-Central",
        7: "Bloomington North",
        8: "Evansville Central",
    },
}


def get_configured_regional_hosts(year: int, gender: str) -> Dict[int, str]:
    """Return configured hosts for a given qualifier year and gender."""
    key = (int(year), (gender or "").strip().title())
    return dict(REGIONAL_HOSTS_BY_YEAR_GENDER.get(key, {}))
