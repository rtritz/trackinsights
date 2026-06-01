import re
import sys
import os
import pandas as pd
import difflib

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
    ref_scores = {}
    for line in ref_text.strip().splitlines():
        m = re.match(r"\d+\s+(.+?)\s*-\s*([\d.]+)", line.strip())
        if m:
            name = m.group(1).strip()
            pts = float(m.group(2))
            ref_scores[name] = pts
    return ref_scores

def compare_scores(computed, reference, fuzzy_threshold=0.4):
    matches = []
    mismatches = []
    missing_in_computed = []
    missing_in_reference = []
    fuzzy_matches = []
    def norm(s):
        return s.lower().replace('(', '').replace(')', '').replace('-', ' ').replace('.', '').replace(',', '').replace('  ', ' ').strip()
    computed_norm = {norm(k): (k, v) for k, v in computed.items()}
    reference_norm = {norm(k): (k, v) for k, v in reference.items()}
    matched_ref_norms = set()
    matched_comp_norms = set()

    # For each reference, look for any computed with >=0.4 similarity and matching score
    for ref_norm, (ref_name, ref_pts) in reference_norm.items():
        found_match = False
        for comp_norm, (comp_name, comp_pts) in computed_norm.items():
            similarity = difflib.SequenceMatcher(None, ref_norm, comp_norm).ratio()
            if similarity >= fuzzy_threshold:
                if abs(comp_pts - ref_pts) < 0.01:
                    matches.append((f"{ref_name} (≈ {comp_name})", ref_pts))
                    fuzzy_matches.append((ref_name, comp_name))
                    matched_ref_norms.add(ref_norm)
                    matched_comp_norms.add(comp_norm)
                    found_match = True
                    break
                else:
                    mismatches.append((f"{ref_name} (≈ {comp_name})", ref_pts, comp_pts))
                    fuzzy_matches.append((ref_name, comp_name))
                    matched_ref_norms.add(ref_norm)
                    matched_comp_norms.add(comp_norm)
                    found_match = True
                    break
        if not found_match:
            missing_in_computed.append((ref_name, ref_pts))

    # Any computed not matched to a reference
    for comp_norm, (comp_name, comp_pts) in computed_norm.items():
        if comp_norm not in matched_comp_norms:
            missing_in_reference.append((comp_name, comp_pts))

    return matches, mismatches, missing_in_computed, missing_in_reference, fuzzy_matches

def main():
    year = 2026
    gender = "Boys"
    meet_type = "Regional"
    meet_number = 8

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
        computed_scores = {db.get_school_name(int(sid)) if db.get_school_name(int(sid)) else str(sid): pts for sid, pts in scores.items()}
        ref_scores = parse_reference_scores(reference_scores_text)
        matches, mismatches, missing_in_computed, missing_in_reference, fuzzy_matches = compare_scores(computed_scores, ref_scores)
        print("\n--- SCORE COMPARISON SUMMARY ---")
        print(f"Matches ({len(matches)}):")
        for name, pts in matches:
            print(f"  {name}: {pts}")
        print(f"\nMismatches ({len(mismatches)}):")
        for name, ref_pts, comp_pts in mismatches:
            print(f"  {name}: reference={ref_pts}, computed={comp_pts}")
        print(f"\nMissing in computed ({len(missing_in_computed)}):")
        for name, pts in missing_in_computed:
            print(f"  {name}: {pts}")
        print(f"\nMissing in reference ({len(missing_in_reference)}):")
        for name, pts in missing_in_reference:
            print(f"  {name}: {pts}")
        if fuzzy_matches:
            print(f"\nFuzzy matched schools (≈ means fuzzy match):")
            for ref_name, comp_name in fuzzy_matches:
                print(f"  {ref_name} ≈ {comp_name}")

if __name__ == "__main__":
    main()
