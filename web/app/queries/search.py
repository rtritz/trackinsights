"""Search

The site-wide search that matches athletes and schools.
"""

from sqlalchemy import or_

from .. import db
from ..models import Athlete, School
from ..event_dashboards import EVENT_DASHBOARDS

from .search_scoring import (
    _calculate_combined_score,
    _calculate_score,
)



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
    school_filters = [School.school_name.ilike(f"%{word}%") for word in query_words]

    # Get filtered schools (all that match - no limit)
    schools_query = (
        db.session.query(School.school_id, School.school_name)
        .filter(or_(*school_filters))
    ) if school_filters else None
    schools = schools_query.all() if schools_query is not None else []
    
    # Build athlete filters - athlete matches ANY word in first, last, or school name
    athlete_filters = []
    for word in query_words:
        like_pattern = f"%{word}%"
        athlete_filters.extend([
            Athlete.first.ilike(like_pattern),
            Athlete.last.ilike(like_pattern),
            School.school_name.ilike(like_pattern),
        ])

    # Get filtered athletes (all that match - no limit)
    if athlete_filters:
        athletes_query = (
            db.session.query(
                Athlete.athlete_id,
                Athlete.first,
                Athlete.last,
                Athlete.gender,
                Athlete.graduation_year,
                School.school_name.label("school_name"),
            )
            .join(School, Athlete.school_id == School.school_id, isouter=True)
            .filter(or_(*athlete_filters))
        )
        athletes = athletes_query.all()
    else:
        athletes = []
    
    results = []

    # Put event pages first when the query matches a dashboard's search terms,
    # so common event names are not pushed out by athlete/school matches.
    for event_page in EVENT_DASHBOARDS:
        matched_term = next(
            (
                term for term in event_page["search_terms"]
                if all(word in term for word in query_words)
            ),
            None,
        )
        if matched_term:
            results.append({
                "type": "event",
                "id": event_page["slug"],
                "name": f"{event_page['label']} Leaderboard",
                "url": f"/{event_page['slug']}",
                "score": len(query_words) / len(matched_term.split()),
                "priority": 0,
            })
    
    # Score schools
    for school_id, school_name in schools:
        score = _calculate_score(school_name, query_words)
        if score > -20:  # Only include if at least one match
            results.append({
                "type": "school",
                "id": school_id,
                "name": school_name,
                "score": score,
                "priority": 1  # Schools have higher priority
            })
    
    # Score athletes
    for athlete in athletes:
        athlete_id = athlete.athlete_id
        athlete_name = f"{athlete.first} {athlete.last}".strip()
        school_name = getattr(athlete, "school_name", "") or ""
        
        # Calculate combined score: check if query words match across name + school
        score = _calculate_combined_score(athlete_name, school_name, query_words)
        
        if score > -20:  # Only include if at least one match
            results.append({
                "type": "athlete",
                "id": athlete_id,
                "name": athlete_name,
                "school": school_name or None,
                "gender": athlete.gender,
                "graduation_year": athlete.graduation_year,
                "classYear": athlete.graduation_year,
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
