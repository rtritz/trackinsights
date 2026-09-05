"""
State Predictions

Projects state-meet team scores by pooling final results from all 8
regionals and applying state-meet scoring (top 9 places: 10-8-7-6-5-4-3-2-1).

Mirrors the structure and fractional tie-splitting of
``regional_predictions.py`` (see ``_score_event``) but reads regional
finals across the entire state and produces a single ranked list per
year/gender instead of one list per regional.
"""

import sqlite3
from collections import defaultdict

from common.const import CONST


STATE_POINTS = {1: 10, 2: 8, 3: 7, 4: 6, 5: 5, 6: 4, 7: 3, 8: 2, 9: 1}
NUM_REGIONALS = 8

DB_PATH = CONST.DB_PATH


def _is_track_like_event(event_name):
    return bool(event_name) and event_name[0].isdigit()


def _score_event(rows, ascending):
    """
    rows is a list of (school_id, school_name, result2). Returns {school_id: points}.

    Ties on the exact same mark share a place and split that place's (plus
    any following places the tie group occupies) combined point value
    evenly across the tied schools (matches the convention used by
    regional_predictions.py and calculate_team_scores.py).
    """
    cleaned = [
        (sid, name or "", r)
        for sid, name, r in rows
        if r is not None and r not in (0, 9999)
    ]
    if not cleaned:
        return {}
    cleaned.sort(key=lambda x: (x[2] if ascending else -x[2]))

    scores = defaultdict(float)
    i = 0
    n = len(cleaned)
    while i < n:
        place = i + 1
        mark = cleaned[i][2]
        tie_group = [cleaned[i]]
        j = i + 1
        while j < n and cleaned[j][2] == mark:
            tie_group.append(cleaned[j])
            j += 1
        tie_size = len(tie_group)
        scoring_slots = [p for p in range(place, place + tie_size) if p in STATE_POINTS]
        pts_value = (sum(STATE_POINTS[p] for p in scoring_slots) / tie_size) if scoring_slots else 0
        if pts_value:
            for sid, _name, _value in tie_group:
                scores[sid] += pts_value
        i = j
    return scores


def _fetch_individual_rows(conn, year, gender):
    sql = """
        SELECT ar.event, s.school_id, s.school_name, ar.result2
        FROM athlete_result ar
        JOIN athlete a ON ar.athlete_id = a.athlete_id
        JOIN school s ON a.school_id = s.school_id
        JOIN meet m ON ar.meet_id = m.meet_id
        WHERE m.year = ?
          AND m.gender = ?
          AND m.meet_type = 'Regional'
          AND ar.result_type = 'Final'
          AND ar.result2 IS NOT NULL
          AND ar.result2 NOT IN (0, 9999)
    """
    return conn.execute(sql, (year, gender)).fetchall()


def _fetch_relay_rows(conn, year, gender):
    sql = """
        SELECT rr.event, s.school_id, s.school_name, rr.result2
        FROM relay_result rr
        JOIN school s ON rr.school_id = s.school_id
        JOIN meet m ON rr.meet_id = m.meet_id
        WHERE m.year = ?
          AND m.gender = ?
          AND m.meet_type = 'Regional'
          AND rr.result2 IS NOT NULL
          AND rr.result2 NOT IN (0, 9999)
    """
    return conn.execute(sql, (year, gender)).fetchall()


def _present_regionals(conn, year, gender):
    sql = """
        SELECT DISTINCT m.meet_num
        FROM athlete_result ar
        JOIN meet m ON ar.meet_id = m.meet_id
        WHERE m.year = ? AND m.gender = ? AND m.meet_type = 'Regional'
    """
    return {row[0] for row in conn.execute(sql, (year, gender)).fetchall()}


def _project_state(conn, year, gender):
    individual = _fetch_individual_rows(conn, year, gender)
    relays = _fetch_relay_rows(conn, year, gender)

    if not individual and not relays:
        return []

    school_names = {row[1]: row[2] for row in individual}
    for row in relays:
        school_names.setdefault(row[1], row[2])

    by_event = defaultdict(list)
    for event, sid, name, result2 in individual:
        by_event[event].append((sid, name, result2))
    for event, sid, name, result2 in relays:
        by_event[event].append((sid, name, result2))

    totals = defaultdict(float)
    for event, rows in by_event.items():
        event_scores = _score_event(rows, ascending=_is_track_like_event(event))
        for sid, pts in event_scores.items():
            totals[sid] += pts

    ranked = sorted(
        ((sid, round(pts, 2)) for sid, pts in totals.items() if pts > 0),
        key=lambda x: (-x[1], school_names.get(x[0], "")),
    )

    output = []
    last_score = None
    last_place = 0
    for idx, (sid, score) in enumerate(ranked, start=1):
        if score != last_score:
            last_place = idx
            last_score = score
        output.append({
            "place": last_place,
            "team": school_names.get(sid, f"School #{sid}"),
            "score": score,
        })
    return output


def get_state_predictions(year, gender, top_n=None, db_path=None):
    """
    Compute projected state-meet team scores by pooling all 8 regional finals.

    Args:
        year: season year.
        gender: "Boys" or "Girls".
        top_n: cap on rows returned (None = no cap).
        db_path: override path to Track.db.

    Returns a dict:
        {
            "year": year,
            "gender": gender,
            "ready": True/False,
            "regionals_loaded": <int 0..8>,
            "missing_regionals": [list of missing regional_nums],
            "rows": [{place, team, score}, ...]
        }
    ``ready`` is True only when all 8 regionals have at least one result in the DB.
    """
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        present = _present_regionals(conn, year, gender)
        expected = set(range(1, NUM_REGIONALS + 1))
        missing = sorted(expected - present)
        ready = not missing

        rows = []
        if ready:
            rows = _project_state(conn, year, gender)
            if top_n is not None:
                rows = rows[:top_n]

        return {
            "year": year,
            "gender": gender,
            "ready": ready,
            "regionals_loaded": len(present & expected),
            "missing_regionals": missing,
            "rows": rows,
        }
    finally:
        conn.close()
