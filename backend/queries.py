from .models import Athlete, School
from sqlalchemy import or_, and_
from . import db


def get_athletes(limit=100):
    return Athlete.query.limit(limit).all()


def get_athlete_by_id(aid):
    return Athlete.query.get(aid)


def add_athlete(first_name, last_name, school=None):
    a = Athlete(first_name=first_name, last_name=last_name, school=school)
    db.session.add(a)
    db.session.commit()
    return a

def search_bar(query_text: str):
    """
    Search for schools and athletes matching the query.
    Returns a list of dicts with results sorted by a scoring algorithm:
    - +2 for exact word matches (bonus)
    - +1 for prefix matches
    - -999 for mismatches
    - Score divided by length of item
    - Position bonus for matches at start
    - Schools prioritized in ties
    """
    q = (query_text or "").strip().lower()
    if not q:
        return []
    
    query_words = q.split()
    
    # Build SQL filters for performance - only fetch potential matches
    # Use OR to get all records that match ANY query word
    school_filters = []
    for word in query_words:
        school_filters.append(School.school_name.ilike(f"%{word}%"))
    
    # Get filtered schools (all that match - no limit)
    schools = School.query.filter(or_(*school_filters)).all() if school_filters else []
    
    # Build athlete filters - athlete matches ANY word in first, last, or school name
    athlete_filters = []
    for word in query_words:
        athlete_filters.append(Athlete.first.ilike(f"%{word}%"))
        athlete_filters.append(Athlete.last.ilike(f"%{word}%"))
        athlete_filters.append(School.school_name.ilike(f"%{word}%"))
    
    # Get filtered athletes (all that match - no limit)
    athletes = Athlete.query.join(School).filter(or_(*athlete_filters)).all() if athlete_filters else []
    
    results = []
    
    # Score schools
    for school in schools:
        score = _calculate_score(school.school_name, query_words)
        if score > -20:  # Only include if at least one match
            results.append({
                "type": "school",
                "id": school.school_id,
                "name": school.school_name,
                "score": score,
                "priority": 1  # Schools have higher priority
            })
    
    # Score athletes
    for athlete in athletes:
        athlete_name = f"{athlete.first} {athlete.last}"
        school_name = athlete.school.school_name if athlete.school else ""
        
        # Calculate combined score: check if query words match across name + school
        score = _calculate_combined_score(athlete_name, school_name, query_words)
        
        if score > -20:  # Only include if at least one match
            results.append({
                "type": "athlete",
                "id": athlete.athlete_id,
                "name": athlete_name,
                "school": athlete.school.school_name if athlete.school else None,
                "score": score,
                "priority": 2  # Athletes have lower priority
            })
    
    # Sort by priority first (schools before athletes), then by score
    results.sort(key=lambda x: (x["priority"], -x["score"]))
    
    # Remove score and priority from final results
    for r in results:
        del r["score"]
        del r["priority"]
    
    return results[:20]  # Limit to top 20 results


def _calculate_score(text: str, query_words: list) -> float:
    """
    Calculate score for a text based on query words.
    Algorithm:
    - +2 for each exact word match (bonus for exact match)
    - +1 for word that starts with query word (prefix match)
    - +0.5 bonus for matches at the beginning of text (position bonus)
    - -999 for each query word that doesn't match
    - Final score divided by length of text
    """
    text_lower = text.lower()
    text_words = text_lower.split()
    
    if not text_words:
        return -999
    
    score = 0
    for query_word in query_words:
        matched = False
        # Check for exact match or prefix match
        for idx, text_word in enumerate(text_words):
            if text_word == query_word:
                score += 2  # Exact match gets bonus
                # Position bonus: first word gets extra boost
                if idx == 0:
                    score += 0.5
                matched = True
                break
            elif text_word.startswith(query_word):
                score += 1  # Prefix match gets standard score
                # Position bonus: first word gets extra boost
                if idx == 0:
                    score += 0.5
                matched = True
                break
        
        if not matched:
            score -= 999
    
    # Divide by length of text (use length of words to normalize)
    text_length = len(text_words)
    return score / text_length


def _calculate_combined_score(name: str, school: str, query_words: list) -> float:
    """
    Calculate score for an athlete by checking if query words match across name and school.
    Allows queries like "owen park" to match "Owen Zhang" from "Park Tudor".
    
    Algorithm:
    - Check each query word against both name and school
    - +3 for exact match in name (with position bonus)
    - +2 for exact match in name
    - +1 for exact match in school
    - Prefix matches worth less
    - -999 if query word matches neither
    - Heavily favor all-name matches over name+school matches
    """
    name_lower = name.lower()
    school_lower = school.lower()
    name_words = name_lower.split()
    school_words = school_lower.split()
    
    if not name_words and not school_words:
        return -999
    
    score = 0
    name_matches = 0
    school_matches = 0
    
    for query_word in query_words:
        matched_in_name = False
        matched_in_school = False
        
        # Check name first (higher priority)
        for idx, name_word in enumerate(name_words):
            if name_word == query_word:
                score += 3 if idx == 0 else 2  # Bonus for first position
                matched_in_name = True
                name_matches += 1
                break
            elif name_word.startswith(query_word):
                score += 1.5 if idx == 0 else 1
                matched_in_name = True
                name_matches += 1
                break
        
        # If not matched in name, check school
        if not matched_in_name:
            for school_word in school_words:
                if school_word == query_word:
                    score += 1  # School matches worth less
                    matched_in_school = True
                    school_matches += 1
                    break
                elif school_word.startswith(query_word):
                    score += 0.5
                    matched_in_school = True
                    school_matches += 1
                    break
        
        if not matched_in_name and not matched_in_school:
            score -= 999
    
    # Bonus: if ALL query words matched in name, add big bonus
    if name_matches == len(query_words):
        score += 5  # Big bonus for complete name match
    
    # Normalize by number of query words (not total text length)
    # This keeps scores comparable regardless of school name length
    return score / len(query_words)

