from functools import lru_cache

from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload

from .models import Athlete, School, AthleteResult, Meet
from . import db


def get_athletes(limit=100):
    return Athlete.query.limit(limit).all()


def get_athlete_by_id(aid):
    return Athlete.query.get(aid)


def add_athlete(first_name, last_name, school=None, gender=None, graduation_year=None):
    """Create a new athlete.

    The ``school`` argument can be either a ``School`` instance or a school name.
    When a string is provided the school will be looked up (or created) before
    associating it with the new athlete.
    """

    school_obj = None
    if isinstance(school, School):
        school_obj = school
    elif isinstance(school, str) and school.strip():
        school_obj = School.query.filter_by(school_name=school.strip()).first()
        if not school_obj:
            school_obj = School(school_name=school.strip())
            db.session.add(school_obj)
            db.session.flush()

    athlete = Athlete(
        first=first_name,
        last=last_name,
        school=school_obj,
        gender=gender,
        graduation_year=graduation_year,
    )
    db.session.add(athlete)
    db.session.commit()
    return athlete

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
                "gender": athlete.gender,
                "graduation_year": athlete.graduation_year,
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


def get_athlete_dashboard_data(athlete_id: int):
    """Aggregate the data needed to power the athlete dashboard."""

    athlete = (
        Athlete.query.options(joinedload(Athlete.school))
        .filter_by(athlete_id=athlete_id)
        .one_or_none()
    )
    if not athlete:
        return None

    badges = _compute_badges(athlete_id)
    playoff_history = _build_playoff_history(athlete_id)

    return {
        "athlete": {
            "id": athlete.athlete_id,
            "first": athlete.first,
            "last": athlete.last,
            "full_name": f"{athlete.first} {athlete.last}".strip(),
            "school": athlete.school.school_name if athlete.school else None,
            "gender": athlete.gender,
            "graduation_year": athlete.graduation_year,
        },
        "badges": badges,
        "playoff_history": playoff_history,
    }


def _compute_badges(athlete_id: int):
    stage_results = (
        db.session.query(AthleteResult, Meet)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            AthleteResult.athlete_id == athlete_id,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .all()
    )

    sectional = [item for item in stage_results if item[1].meet_type == "Sectional"]
    regional = [item for item in stage_results if item[1].meet_type == "Regional"]
    state = [item for item in stage_results if item[1].meet_type == "State"]

    return {
        "sectional": _compute_stage_badge("Sectional", sectional, placer_threshold=8),
        "regional": _compute_stage_badge("Regional", regional, placer_threshold=8),
        "state": _compute_stage_badge("State", state, placer_threshold=9),
    }


def _compute_sectional_badge(results):
    if not results:
        return None

    best_percentile = None

    for res, _meet in results:
        if res.place is None or res.place <= 0:
            continue

        field_size = _get_field_size(res.meet_id, res.event, res.result_type)
        if not field_size:
            continue

        percentile = (res.place / field_size) * 100
        best_percentile = percentile if best_percentile is None else min(best_percentile, percentile)

    if best_percentile is None:
        return None

    return {
        "stage": "Sectional",
        "best_percentile": best_percentile,
        "label": f"Top {_format_percentile(best_percentile)}% Sectional",
    }


def _compute_stage_badge(stage_name, results, placer_threshold):
    if not results:
        return None

    qualifier_count = 0
    placer_count = 0

    for res, _meet in results:
        qualifier_count += 1
        if res.place is not None and res.place > 0 and res.place <= placer_threshold:
            placer_count += 1

    if placer_count:
        count_prefix = f"{placer_count} x " if placer_count > 1 else ""
        return {
            "stage": stage_name,
            "achievement": "Placer",
            "count": placer_count,
            "label": f"{count_prefix}{stage_name} Placer",
        }

    if qualifier_count:
        count_prefix = f"{qualifier_count} x " if qualifier_count > 1 else ""
        return {
            "stage": stage_name,
            "achievement": "Qualifier",
            "count": qualifier_count,
            "label": f"{count_prefix}{stage_name} Qualifier",
        }

    return None


def _build_playoff_history(athlete_id: int):
    results = (
        db.session.query(AthleteResult, Meet)
        .join(Meet, AthleteResult.meet_id == Meet.meet_id)
        .filter(
            AthleteResult.athlete_id == athlete_id,
            Meet.meet_type.in_(("Sectional", "Regional", "State")),
        )
        .all()
    )

    if not results:
        return []

    history = {}

    for res, meet in results:
        key = (meet.year, res.event)
        entry = history.setdefault(
            key,
            {
                "year": meet.year,
                "event": res.event,
                "Sectional": None,
                "Regional": None,
                "State": None,
            },
        )

        candidate = {
            "result": res.result,
            "place": res.place,
            "result_type": res.result_type,
            "formatted": _format_stage_result(res.result, res.place),
        }
        entry[meet.meet_type] = _select_preferred_result(entry[meet.meet_type], candidate)

    history_rows = []
    for values in history.values():
        history_rows.append(
            {
                "year": values["year"],
                "event": values["event"],
                "sectional": values["Sectional"]["formatted"] if values["Sectional"] else "–",
                "regional": values["Regional"]["formatted"] if values["Regional"] else "–",
                "state": values["State"]["formatted"] if values["State"] else "–",
            }
        )

    history_rows.sort(key=lambda row: (-row["year"], row["event"]))
    return history_rows


def _select_preferred_result(existing, candidate):
    if existing is None:
        return candidate

    result_type_order = {"Final": 2, "Prelim": 1}
    existing_weight = result_type_order.get(existing.get("result_type"), 0)
    candidate_weight = result_type_order.get(candidate.get("result_type"), 0)

    if candidate_weight > existing_weight:
        return candidate
    if candidate_weight < existing_weight:
        return existing

    existing_place = existing.get("place")
    candidate_place = candidate.get("place")

    if candidate_place is not None and candidate_place > 0:
        if existing_place is None or candidate_place < existing_place:
            return candidate

    return existing


@lru_cache(maxsize=None)
def _get_field_size(meet_id, event, result_type):
    return (
        db.session.query(func.max(AthleteResult.place))
        .filter(
            AthleteResult.meet_id == meet_id,
            AthleteResult.event == event,
            AthleteResult.result_type == result_type,
            AthleteResult.place.isnot(None),
        )
        .scalar()
    )


def _format_percentile(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def _format_stage_result(result_value, place):
    if place is None or place <= 0:
        return result_value or "–"

    place_str = _ordinal(place)
    if result_value:
        return f"{result_value} ({place_str})"
    return place_str


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"

