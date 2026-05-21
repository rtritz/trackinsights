# School name mappings for MileSplit API names to database school_name values
# This file centralizes all team name aliases to improve maintainability

SCHOOL_MAPPINGS = {
    # Raw-format truncations (from raw page parser)
    "Indianapolis Scecina Memo": "Indianapolis Scecina Memorial",
    "Greencastle - A": "Greencastle",
    "Indianapolis Bishop Chata": "Indianapolis Bishop Chatard",
    "North Central (Indianapol": "North Central (Indianapolis)",
    "Indianapolis Arsenal Tech": "Indianapolis Arsenal Technical",
    "Indiana School for the De": "Indiana School for the Deaf",
    # Formatted API full names → DB school_name
    "Cardinal Ritter High School": "Indianapolis Cardinal Ritter",
    "Crispus Attucks Medical Magnet High School": "Indianapolis Crispus Attucks",
    "Crispus Attucks Medical Magnet": "Indianapolis Crispus Attucks",
    "Southwestern High School (Shel": "Southwestern (Shelbyville)",
    "Southwestern High School (Shelbyville)": "Southwestern (Shelbyville)",
    "Covenant Christian High School (Indianapolis)": "Covenant Christian (Indpls)",
    "George Washington High School": "Indianapolis George Washington Community",
    # Sectional 21 API names (Girls 2025)
    "Cathedral High School": "Indianapolis Cathedral",
    "North Central High School (Indianapolis)": "North Central (Indianapolis)",
    "Bishop Chatard Indianapolis": "Indianapolis Bishop Chatard",
    "Brebeuf Jesuit Prep School": "Brebeuf Jesuit Preparatory",
    "Arsenal Technical High School": "Indianapolis Arsenal Technical",
    "Shortridge High School Indianapolis": "Indianapolis Shortridge",
    "Purdue Polytechnic (Englewood)": "Purdue Polytechnic - Downtown",
    "Purdue Polytechnic High School Broad Ripple": "Purdue Polytechnic - Broad Ripple",
    "International High School": "International School of Indiana",
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
