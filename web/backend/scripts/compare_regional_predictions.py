"""
One-off comparison of projected vs actual 2026 Girls Regional team scores.

Reads:
  - Projected scores from frontend/static/data/regional_predictions/regional_predictions_2026_girls.json
  - Actual scores computed from Track.db using the same 10-8-6-5-4-3-2-1 regional
    scoring (with tie averaging across the top 8 places, individual + relay finals).

Run from web/backend/scripts/:  python compare_regional_predictions.py
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

YEAR = 2026
GENDER = "Girls"

REGIONAL_POINTS = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent.parent / "data" / "Track.db"
PRED_PATH = (
    HERE.parent.parent
    / "frontend"
    / "static"
    / "data"
    / "regional_predictions"
    / f"regional_predictions_{YEAR}_{GENDER.lower()}.json"
)


def _avg_tie_points(start_place: int, tie_count: int) -> float:
    return sum(REGIONAL_POINTS.get(start_place + i, 0) for i in range(tie_count)) / tie_count


def _score_event(rows):
    """
    rows: list of (school_id, result2) for ONE event at ONE meet, finals only.
    Returns {school_id: points}.
    Times: lower is better. Field events (already filtered out): higher better — not handled
    here because we sort by event_type instead.  This helper expects sort_ascending caller.
    """
    pass  # see _score_meet


def _score_meet(conn, meet_id: int):
    """Compute team scores for one regional meet."""
    scores: dict[int, float] = defaultdict(float)

    # Individual finals: (event, event_type, school_id, result2)
    indiv = conn.execute(
        """
        SELECT ar.event, e.event_type, a.school_id, ar.result2
        FROM athlete_result ar
        JOIN athlete a ON ar.athlete_id = a.athlete_id
        JOIN event   e ON ar.event = e.event
        WHERE ar.meet_id = ?
          AND ar.result_type = 'Final'
          AND ar.result2 IS NOT NULL
        """,
        (meet_id,),
    ).fetchall()

    # Relay rows: (event, school_id, result2)  -- always "Final"-equivalent
    relays = conn.execute(
        """
        SELECT rr.event, 'Relay' AS event_type, rr.school_id, rr.result2
        FROM relay_result rr
        WHERE rr.meet_id = ?
          AND rr.result2 IS NOT NULL
        """,
        (meet_id,),
    ).fetchall()

    by_event: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for event, etype, sid, r2 in indiv + relays:
        by_event[(event, etype)].append((sid, r2))

    # Field events: higher is better; track + relays: lower is better.
    for (event, etype), entries in by_event.items():
        ascending = etype != "Field"  # lower is better for Track & Relay
        # For each school, keep only their best 2 athletes? Actual meet scoring
        # uses all entered athletes; but our DB stores all finishers. Sort all,
        # apply ties.
        sorted_entries = sorted(entries, key=lambda x: x[1], reverse=not ascending)

        # Walk through entries assigning places with tie handling.
        i = 0
        place = 1
        while i < len(sorted_entries) and place <= 8:
            cur_val = sorted_entries[i][1]
            tie_group = [sorted_entries[i]]
            j = i + 1
            while j < len(sorted_entries) and sorted_entries[j][1] == cur_val:
                tie_group.append(sorted_entries[j])
                j += 1
            pts = _avg_tie_points(place, len(tie_group))
            for sid, _ in tie_group:
                scores[sid] += pts
            place += len(tie_group)
            i = j

    return scores


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")
    if not PRED_PATH.exists():
        raise SystemExit(f"Predictions not found: {PRED_PATH}")

    with open(PRED_PATH, "r", encoding="utf-8") as f:
        predictions = json.load(f)
    pred_by_regional = {p["regional_num"]: p["rows"] for p in predictions}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = None

    # Find each girls regional meet for the year.
    meets = conn.execute(
        """
        SELECT meet_id, meet_num, host
        FROM meet
        WHERE year = ? AND gender = ? AND meet_type = 'Regional'
        ORDER BY meet_num
        """,
        (YEAR, GENDER),
    ).fetchall()

    if not meets:
        raise SystemExit(f"No {YEAR} {GENDER} Regional meets found in DB.")

    # School lookup for school_id -> name
    school_name = dict(conn.execute("SELECT school_id, school_name FROM school").fetchall())

    print(f"\n=== {YEAR} {GENDER} Regional: Projected vs Actual (Top 5) ===\n")

    for meet_id, meet_num, host in meets:
        scores = _score_meet(conn, meet_id)
        actual_ranked = sorted(
            ((school_name.get(sid, f"<sid {sid}>"), pts) for sid, pts in scores.items()),
            key=lambda x: (-x[1], x[0]),
        )

        projected = sorted(
            pred_by_regional.get(meet_num, []),
            key=lambda r: r["place"],
        )

        print(f"--- Regional {meet_num}  ({host or 'unknown host'}) ---")
        print(f"{'Pl':>2}  {'Projected':<28} {'Proj Pts':>8}    "
              f"{'Actual':<28} {'Act Pts':>8}")
        for i in range(5):
            proj = projected[i] if i < len(projected) else {"team": "", "score": ""}
            act = actual_ranked[i] if i < len(actual_ranked) else ("", "")
            ppts = proj.get("score", "")
            ppts_s = f"{ppts:.1f}" if isinstance(ppts, (int, float)) else ""
            apts_s = f"{act[1]:.1f}" if isinstance(act[1], (int, float)) else ""
            print(
                f"{i+1:>2}  {proj.get('team',''):<28} {ppts_s:>8}    "
                f"{act[0]:<28} {apts_s:>8}"
            )
        # Hit / miss summary on top 5
        proj_top5 = {r["team"] for r in projected[:5]}
        act_top5 = {name for name, _ in actual_ranked[:5]}
        hits = proj_top5 & act_top5
        print(f"      Top-5 overlap: {len(hits)}/5  ({', '.join(sorted(hits)) or 'none'})")
        print()

    # Aggregate accuracy
    total_overlap = 0
    total = 0
    winner_hits = 0
    winner_total = 0
    for meet_id, meet_num, host in meets:
        scores = _score_meet(conn, meet_id)
        actual_ranked = sorted(
            ((school_name.get(sid, f"<sid {sid}>"), pts) for sid, pts in scores.items()),
            key=lambda x: (-x[1], x[0]),
        )
        projected = sorted(pred_by_regional.get(meet_num, []), key=lambda r: r["place"])
        proj_top5 = {r["team"] for r in projected[:5]}
        act_top5 = {name for name, _ in actual_ranked[:5]}
        total_overlap += len(proj_top5 & act_top5)
        total += 5
        if projected and actual_ranked:
            winner_total += 1
            if projected[0]["team"] == actual_ranked[0][0]:
                winner_hits += 1

    print("=== Summary ===")
    print(f"Top-5 overlap across all regionals: {total_overlap}/{total} "
          f"({100*total_overlap/total:.1f}%)")
    print(f"Winner picked correctly: {winner_hits}/{winner_total}")


if __name__ == "__main__":
    main()
