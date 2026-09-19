"""Fuzzy match scoring for the site-wide search box.

Pure string work: no database, no models, no Flask. Split out of shared.py
because nothing else in the package needs it and it needs nothing else -- it
can be read, and tested, entirely on its own.
"""
import re


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


def _normalize_name_text(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", value)
    return " ".join(cleaned.lower().split())
