"""
Regional Predictions

Projects regional team scores by combining final-round sectional results
from the four sectionals that feed each regional.

This mirrors the scoring logic in ``projected_team_scores.py`` but reads
directly from Track.db without joining on ``school_enrollment``, so it
produces predictions even before the current-year enrollment rows have
been loaded.
"""

import os
import sqlite3
from collections import defaultdict


REGIONAL_POINTS = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_BASE_DIR, "data", "Track.db")


def _is_track_like_event(event_name):
    return bool(event_name) and event_name[0].isdigit()


def _score_event(rows, ascending):
    """
    rows is a list of (school_id, school_name, result2). Returns {school_id: points}.

    Ties on the mark are broken alphabetically by school name and assigned
    sequential places — matching how meets actually score (no half-points
    awarded for tied marks; a real meet uses jump-off / countback, but we
    don't have that data, so alphabetical is a stable deterministic stand-in).
    """
    cleaned = [
        (sid, name or "", r)
        for sid, name, r in rows
        if r is not None and r not in (0, 9999)
    ]
    if not cleaned:
        return {}
    # Primary: result2 (best first), secondary: school name (alphabetical).
    cleaned.sort(key=lambda x: (x[2] if ascending else -x[2], x[1]))

    scores = defaultdict(float)
    for place, (sid, _name, _value) in enumerate(cleaned, start=1):
        pts = REGIONAL_POINTS.get(place, 0)
        if pts:
            scores[sid] += pts
    return scores


def _feeder_sectional_nums(regional_num):
    start = ((regional_num - 1) * 4) + 1
    return list(range(start, start + 4))


def _fetch_individual_rows(conn, year, gender, sectional_nums):
    placeholders = ",".join("?" * len(sectional_nums))
    sql = f"""
        SELECT ar.event, s.school_id, s.school_name, ar.result2
        FROM athlete_result ar
        JOIN athlete a ON ar.athlete_id = a.athlete_id
        JOIN school s ON a.school_id = s.school_id
        JOIN meet m ON ar.meet_id = m.meet_id
        WHERE m.year = ?
          AND m.gender = ?
          AND m.meet_type = 'Sectional'
          AND m.meet_num IN ({placeholders})
          AND ar.result_type = 'Final'
          AND ar.result2 IS NOT NULL
          AND ar.result2 NOT IN (0, 9999)
    """
    return conn.execute(sql, (year, gender, *sectional_nums)).fetchall()


def _fetch_relay_rows(conn, year, gender, sectional_nums):
    placeholders = ",".join("?" * len(sectional_nums))
    sql = f"""
        SELECT rr.event, s.school_id, s.school_name, rr.result2
        FROM relay_result rr
        JOIN school s ON rr.school_id = s.school_id
        JOIN meet m ON rr.meet_id = m.meet_id
        WHERE m.year = ?
          AND m.gender = ?
          AND m.meet_type = 'Sectional'
          AND m.meet_num IN ({placeholders})
          AND rr.result2 IS NOT NULL
          AND rr.result2 NOT IN (0, 9999)
    """
    return conn.execute(sql, (year, gender, *sectional_nums)).fetchall()


def _project_regional(conn, year, gender, regional_num):
    sectional_nums = _feeder_sectional_nums(regional_num)
    individual = _fetch_individual_rows(conn, year, gender, sectional_nums)
    relays = _fetch_relay_rows(conn, year, gender, sectional_nums)

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


def has_sectional_data(conn, year, gender):
    row = conn.execute(
        """
        SELECT COUNT(*) FROM athlete_result ar
        JOIN meet m ON ar.meet_id = m.meet_id
        WHERE m.year = ? AND m.gender = ? AND m.meet_type = 'Sectional'
        """,
        (year, gender),
    ).fetchone()
    return bool(row and row[0])


def get_regional_predictions(year, gender, top_n=10, hosts=None, db_path=None):
    """
    Compute projected regional team scores for all 8 regionals.

    Args:
        year: season year.
        gender: "Boys" or "Girls".
        top_n: cap on rows returned per regional (None = no cap).
        hosts: optional ``{regional_num: host_name}`` mapping for labels.
        db_path: override path to Track.db.

    Returns a list of dicts:
        [{"regional_num": 1, "host": "...", "rows": [...]}, ...]
    where ``rows`` is a list of ``{place, team, score}``.
    Returns an empty list if no sectional data exists for the year/gender.
    """
    hosts = hosts or {}
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        if not has_sectional_data(conn, year, gender):
            return []
        results = []
        for regional_num in range(1, 9):
            rows = _project_regional(conn, year, gender, regional_num)
            if top_n is not None:
                rows = rows[:top_n]
            results.append({
                "regional_num": regional_num,
                "host": hosts.get(regional_num),
                "rows": rows,
            })
        return results
    finally:
        conn.close()
