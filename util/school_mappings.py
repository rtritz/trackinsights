# School name mappings for MileSplit API names to database school_name values
# This file centralizes all team name aliases to improve maintainability
#
# Keys are matched AFTER "HS"/"High School" is stripped from the raw name (see
# team_mapping() below) -- MileSplit reports the same school with that suffix
# at some meet levels (e.g. Sectional/Regional: "Cathedral High School") and
# without it at others (e.g. State: "Cathedral"), so keys are written in the
# already-stripped form to match both without needing a duplicate entry.

import re

SCHOOL_MAPPINGS = {
    # Raw-format truncations and known aliases not reliably resolved by normalization alone
    "Greencastle - A": "Greencastle",

    # Formatted API full names -> DB school_name
    "Cardinal Ritter": "Indianapolis Cardinal Ritter",
    "Crispus Attucks Medical Magnet": "Indianapolis Crispus Attucks",
    "Southwestern (Shel": "Southwestern (Shelbyville)",
    "Covenant Christian (Indianapolis)": "Covenant Christian (Indpls)",

    # Sectional aliases still requiring explicit disambiguation
    "Shortridge Indianapolis": "Indianapolis Shortridge",
    "Purdue Polytechnic (Englewood)": "Purdue Polytechnic - Downtown",

    # --- User review needed: Sectional API names not found in DB ---
    "Saint Joseph": "South Bend Saint Joseph",
    "Trinity Academy South Bend\"": "Trinity School at Greenlawn",
    "Herron-Riverside": "Riverside",
    "Cathedral": "Indianapolis Cathedral",
    "Charles Tindley": "Tindley",
    "Christel House Watanabe Manual": "Christel House",
    "FW Carroll": "Carroll (Fort Wayne)",
    "Thea Bowman Leadership Academy": "Bowman Leadership Academy",
    "South Bend John Adams": "South Bend Adams",
    "Brebeuf Jesuit Prep School": "Brebeuf Jesuit Preparatory",
    "Arsenal Technical": "Indianapolis Arsenal Technical",
    "Scecina Memorial": "Indianapolis Scecina Memorial",
    "Evansville Memorial": "Evansville Reitz Memorial",
    "George Washington": "Indianapolis George Washington Community",
    "Trinity Academy South Bend": "Trinity School at Greenlawn",
}

def team_mapping(team):
    """
    Map MileSplit API team names to database school_name values.

    Strips the "HS"/"High School" suffix before looking the name up, since
    MileSplit includes it at some meet levels and omits it at others for the
    same school -- SCHOOL_MAPPINGS keys are written in the stripped form so
    one entry covers both.

    Args:
        team: Team name from MileSplit API or raw parser

    Returns:
        Corresponding database school_name, or the stripped team name if no
        mapping exists
    """
    stripped = re.sub(r"\b(?:HS|High School)\b", "", str(team), flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -")
    return SCHOOL_MAPPINGS.get(stripped, stripped)


