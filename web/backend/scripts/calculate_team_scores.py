import re
import sys
import os
import pandas as pd

# Allow running as a standalone script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
try:
    from backend.util.db_util import Database
except ModuleNotFoundError:
    from util.db_util import Database

def get_points(df, values, scores):
    for event in df["event"].unique():
        event_df = df[df["event"] == event].copy()
        event_df.sort_values("place", inplace=True)
        event_df["place"] = event_df["place"].astype(int)
        scoring_place = 1
        i = 0
        n = len(event_df)
        while i < n:
            actual_place = event_df.iloc[i]["place"]
            tie_group = event_df[event_df["place"] == actual_place]
            tie_size = len(tie_group)
            tie_indices = tie_group.index.tolist()
            scoring_slots = []
            for k in range(tie_size):
                sp = scoring_place + k
                if sp in values:
                    scoring_slots.append(sp)
            pts_value = 0
            if scoring_slots:
                pts_value = sum(values[p] for p in scoring_slots) / tie_size
            for idx in tie_indices:
                school = event_df.loc[idx, "school_id"]
                scores[school] = scores.get(school, 0) + pts_value
            scoring_place += tie_size
            i += tie_size

def parse_reference_scores(ref_text):
    """Parse pasted "<rank> <school name...> <points>" lines.

    MileSplit's copy/paste format isn't consistent (sometimes a "-" separates
    name from points, sometimes not; team abbreviation codes may be tacked on
    to the name). Rather than anchor on a specific separator, treat the first
    token as the rank and the last token as the points value, and take
    everything in between as the name -- exact name text doesn't matter since
    comparison is done by rank, not by name.
    """
    ref_scores = {}
    for raw_line in ref_text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) < 3 or not re.match(r"^\d+[.)]?$", tokens[0]):
            continue
        try:
            pts = float(tokens[-1])
        except ValueError:
            continue
        name_tokens = tokens[1:-1]
        if name_tokens and name_tokens[-1] == "-":
            name_tokens = name_tokens[:-1]
        name = " ".join(name_tokens).strip()
        if name:
            ref_scores[name] = pts
    return ref_scores

def compare_scores_by_rank(computed_ranked, reference_ranked, tolerance=0.01):
    """Compare two (name, points) lists by rank position rather than by name.

    School names can be formatted differently between the DB and whatever is
    pasted from MileSplit, so pairing is done purely by descending-score rank;
    the caller visually confirms the paired names refer to the same school.
    """
    computed_sorted = sorted(computed_ranked, key=lambda x: x[1], reverse=True)
    reference_sorted = sorted(reference_ranked, key=lambda x: x[1], reverse=True)

    rows = []
    all_match = len(computed_sorted) == len(reference_sorted)
    for i in range(max(len(computed_sorted), len(reference_sorted))):
        comp = computed_sorted[i] if i < len(computed_sorted) else None
        ref = reference_sorted[i] if i < len(reference_sorted) else None
        match = comp is not None and ref is not None and abs(comp[1] - ref[1]) < tolerance
        all_match = all_match and match
        rows.append({
            "rank": i + 1,
            "computed_name": comp[0] if comp else None,
            "computed_pts": comp[1] if comp else None,
            "reference_name": ref[0] if ref else None,
            "reference_pts": ref[1] if ref else None,
            "match": match,
        })
    return rows, all_match

def main():
    year = 2026
    gender = "Girls"
    meet_type = "Sectional"
    meet_number = 5

    # Use path relative to this script's location so it works from any CWD
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.abspath(os.path.join(script_dir, '../../data/Track.db'))
    db = Database(db_path)

    scoring = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
    top_n = len(scoring)
    meet_id = db.get_meet_id(meet_type, meet_number, year, gender)
    if meet_id is None:
        print("No such meet found.")
        sys.exit(1)
    indiv_query = "select first, last, athlete.gender, event, grade, result, result2, place, school.school_name, school.school_id, host, meet_type, meet_num, meet.year, meet.gender from athlete_result inner join athlete on athlete_result.athlete_id = athlete.athlete_id inner join school on athlete.school_id = school.school_id inner join meet on meet.meet_id = athlete_result.meet_id where meet.meet_id = ? and athlete_result.place <= ? and athlete_result.result_type = ?"
    indiv_params = (meet_id, top_n, "Final")
    indiv_df = pd.read_sql_query(indiv_query, db.conn, params=indiv_params)
    relay_query = "select relay_result.school_id, event, result, result2, place, athlete_names, school.school_name, school.team_name, school.school_type, meet.meet_type, meet.meet_num, meet.gender, meet.year from relay_result inner join school on relay_result.school_id = school.school_id inner join meet on meet.meet_id = relay_result.meet_id where meet.meet_id = ? and relay_result.place <= ?"
    relay_params = (meet_id, top_n)
    relay_df = pd.read_sql_query(relay_query, db.conn, params=relay_params)
    if 'enrollment' not in indiv_df.columns:
        indiv_df['enrollment'] = None
    if 'enrollment' not in relay_df.columns:
        relay_df['enrollment'] = None
    scores = {}
    get_points(indiv_df, scoring, scores)
    get_points(relay_df, scoring, scores)
    scores = dict(sorted(scores.items(), key=lambda item: item[1], reverse=True))
    print(f"Team Scores for {meet_type} {meet_number} {year} {gender}:")
    print("{:<30} {:>8}".format("School", "Points"))
    print("-" * 40)
    for school_id, pts in scores.items():
        sid = int(school_id) if school_id is not None else None
        school_name = db.get_school_name(sid)
        print("{:<30} {:>8.1f}".format(school_name if school_name else str(sid), pts))
    print("\nPaste your reference scores below (end with an empty line):")
    ref_lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            break
        ref_lines.append(line)
    if ref_lines:
        reference_scores_text = "\n".join(ref_lines)
        computed_ranked = [
            (db.get_school_name(int(sid)) or str(sid), pts) for sid, pts in scores.items()
        ]
        reference_ranked = list(parse_reference_scores(reference_scores_text).items())
        rows, all_match = compare_scores_by_rank(computed_ranked, reference_ranked)

        print("\n--- RANK-BY-RANK SCORE COMPARISON ---")
        print("{:<5}{:<30}{:>8}   {:<30}{:>8}   {}".format(
            "Rank", "Computed (DB)", "Pts", "Reference (MileSplit)", "Pts", ""))
        for r in rows:
            comp_name = r["computed_name"] or "-"
            comp_pts = f'{r["computed_pts"]:.1f}' if r["computed_pts"] is not None else "-"
            ref_name = r["reference_name"] or "-"
            ref_pts = f'{r["reference_pts"]:.1f}' if r["reference_pts"] is not None else "-"
            flag = "" if r["match"] else "  <-- MISMATCH"
            print("{:<5}{:<30}{:>8}   {:<30}{:>8}{}".format(
                r["rank"], comp_name, comp_pts, ref_name, ref_pts, flag))

        if all_match:
            print(f"\nMEET STATUS: DONE - all {len(rows)} ranks match. No further action needed.")
        else:
            first_bad = next(r["rank"] for r in rows if not r["match"])
            print(f"\nMEET STATUS: NEEDS INVESTIGATION - scores diverge starting at rank {first_bad}.")
            print("Check the DB for missing/incorrect results around that rank (e.g. a dropped event or place).")

if __name__ == "__main__":
    main()
