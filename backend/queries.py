from .models import Athlete
try:
    from . import db
except Exception:
    db = None

# In-memory storage when DB is disabled
_IN_MEMORY = []


def get_athletes(limit=100):
    if db is not None:
        return Athlete.query.limit(limit).all()
    # return most recent from in-memory
    return list(_IN_MEMORY[:limit])


def get_athlete_by_id(aid):
    if db is not None:
        return Athlete.query.get(aid)
    for a in _IN_MEMORY:
        if a.id == aid:
            return a
    return None


def add_athlete(first_name, last_name, school=None):
    a = Athlete(first_name=first_name, last_name=last_name, school=school)
    if db is not None:
        db.session.add(a)
        db.session.commit()
        return a
    _IN_MEMORY.insert(0, a)  # insert at front so recent appear first
    return a
