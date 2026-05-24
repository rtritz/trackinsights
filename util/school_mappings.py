# School name mappings for MileSplit API names to database school_name values
# This file centralizes all team name aliases to improve maintainability

SCHOOL_MAPPINGS = {
    # Raw-format truncations and known aliases not reliably resolved by normalization alone
    "Greencastle - A": "Greencastle",

    # Formatted API full names -> DB school_name
    "Cardinal Ritter High School": "Indianapolis Cardinal Ritter",
    "Crispus Attucks Medical Magnet High School": "Indianapolis Crispus Attucks",
    "Crispus Attucks Medical Magnet": "Indianapolis Crispus Attucks",
    "Southwestern High School (Shel": "Southwestern (Shelbyville)",
    "Covenant Christian High School (Indianapolis)": "Covenant Christian (Indpls)",

    # Sectional aliases still requiring explicit disambiguation
    "Shortridge High School Indianapolis": "Indianapolis Shortridge",
    "Purdue Polytechnic (Englewood)": "Purdue Polytechnic - Downtown",

    # --- User review needed: Sectional API names not found in DB ---
    "Saint Joseph High School": "South Bend Saint Joseph", 
    "Trinity Academy South Bend\"": "Trinity School at Greenlawn",  
    "Herron-Riverside High School": "Riverside",  
    "Cathedral High School": "Indianapolis Cathedral",  
    "Charles Tindley High School": "Tindley",  
    "Christel House Watanabe Manual HS": "Christel House",  
    "Mt. Vernon High School (Mt. Vernon)": "Mt. Vernon",  
    "FW Carroll High School": "Carroll (Fort Wayne)",
    "Thea Bowman Leadership Academy": "Bowman Leadership Academy",
    "South Bend John Adams High School": "South Bend Adams",
    "Brebeuf Jesuit Prep School": "Brebeuf Jesuit Preparatory",
    "Arsenal Technical High School": "Indianapolis Arsenal Technical",
    "Scecina Memorial High School": "Indianapolis Scecina Memorial",
    "Evansville Memorial High School": "Evansville Reitz Memorial",
    "George Washington High School": "Indianapolis George Washington Community",

}

def team_mapping(team):
    """
    Map MileSplit API team names to database school_name values.
    
    Args:
        team: Team name from MileSplit API or raw parser
        
    Returns:
        Corresponding database school_name, or original team name if no mapping exists
    """
    return SCHOOL_MAPPINGS.get(team, team)


