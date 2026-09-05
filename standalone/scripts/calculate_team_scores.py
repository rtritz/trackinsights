import html
import re
import os
import time
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urljoin
import pandas as pd

from common.db import Database
from common.const import CONST

try:
    import requests
    from bs4 import BeautifulSoup
    AUTO_FETCH_AVAILABLE = True
except ImportError:
    AUTO_FETCH_AVAILABLE = False

BASE = "https://in.milesplit.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Sectional/Regional score the top 8 places; State Finals scores the top 9 (per
# the IHSAA State Finals info packet: "The top 9 places will receive medals").
# Verified by least-squares fit against MileSplit's official 2026 Girls State
# team totals -- solved this exact table with ~0 residual across 62 teams.
SECTIONAL_REGIONAL_SCORING = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
STATE_SCORING = {1: 10, 2: 8, 3: 7, 4: 6, 5: 5, 6: 4, 7: 3, 8: 2, 9: 1}

def get_points(df, values, scores):
    """Award points per event using each row's actual recorded `place`, not
    its sequential position among that event's rows. A place can legitimately
    be absent -- a tie (handled below by splitting the tied places' combined
    value across the tied scorers) or a vacant place (DQ/scratch/missing
    result, which simply forfeits that place's points to no one). Reading
    points off row order instead of the real place value conflates these:
    it silently shifts every later scorer up to a higher point value
    whenever any place is skipped, tie or not.
    """
    for event in df["event"].unique():
        event_df = df[df["event"] == event].copy()
        event_df.sort_values("place", inplace=True)
        event_df["place"] = event_df["place"].astype(int)
        i = 0
        n = len(event_df)
        while i < n:
            actual_place = event_df.iloc[i]["place"]
            tie_group = event_df[event_df["place"] == actual_place]
            tie_size = len(tie_group)
            tie_indices = tie_group.index.tolist()
            scoring_slots = [p for p in range(actual_place, actual_place + tie_size) if p in values]
            pts_value = 0
            if scoring_slots:
                pts_value = sum(values[p] for p in scoring_slots) / tie_size
            for idx in tie_indices:
                school = event_df.loc[idx, "school_id"]
                scores[school] = scores.get(school, 0) + pts_value
            i += tie_size

def _parse_score_lines(ref_text):
    """Parse a contiguous block of "<rank> <school name...> <points>" lines
    into a raw (name, points) list -- duplicates preserved, in document order.

    MileSplit's copy/paste format isn't consistent (sometimes a "-" separates
    name from points, sometimes not; team abbreviation codes may be tacked on
    to the name). Rather than anchor on a specific separator, treat the first
    token as the rank and the last token as the points value, and take
    everything in between as the name -- exact name text doesn't matter since
    comparison is done by rank, not by name.

    Some meets post a single "raw" page that has the team-scores table
    followed by the full event-by-event individual results (which happen to
    match the same "<number> <name...> <number>" shape). To avoid pulling in
    those unrelated rows, only the first contiguous run of matching lines is
    collected -- parsing stops at the first non-matching line once the table
    has started, instead of scanning the whole document.

    An individual heat placing (e.g. "1 Ella McManomy 12 North Montgomery
    High School 12.65 1") also fits that shape on its own, since it starts
    with a place number and ends with a numeric heat/points-like value. What
    a genuine team name never has, though, is a digit embedded in the middle
    (a grade, a mark, a heat number) -- so any middle token containing a
    digit disqualifies the line as a team-scores row.
    """
    rows = []
    started = False
    for raw_line in ref_text.strip().splitlines():
        line = raw_line.strip()
        tokens = line.split() if line else []
        is_row = len(tokens) >= 3 and re.match(r"^\d+[.)]?$", tokens[0])
        pts = None
        if is_row:
            try:
                # Team points are never negative; a "-" sometimes glues onto the
                # score when it was meant as a name/table separator instead.
                pts = abs(float(tokens[-1]))
            except ValueError:
                is_row = False
        if is_row and any(any(ch.isdigit() for ch in tok) for tok in tokens[1:-1]):
            is_row = False
        if not is_row:
            if started:
                break
            continue
        started = True
        name_tokens = tokens[1:-1]
        if name_tokens and name_tokens[-1] == "-":
            name_tokens = name_tokens[:-1]
        name = " ".join(name_tokens).strip()
        if name:
            rows.append((name, pts))
    return rows

def parse_reference_scores(ref_text):
    """Parse "<rank> <school name...> <points>" lines into a {name: points}
    dict. See _parse_score_lines() for parsing details."""
    return dict(_parse_score_lines(ref_text))

def _extract_table_score_rows(html_text):
    """Extract (rank, name, points) rows from a MileSplit team-scores block
    rendered as an HTML table (<tr><td>PL</td><td>Team</td><td>Code</td>
    <td>Pts</td></tr>...) instead of a <pre> text listing -- some meets post
    it this way."""
    soup = BeautifulSoup(html_text, "html.parser")
    body = soup.find(id="meetResultsBody") or soup
    rows = []
    for tr in body.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 3 or not re.match(r"^\d+$", cells[0]):
            continue
        try:
            pts = abs(float(cells[-1]))
        except ValueError:
            continue
        name = cells[1]
        if name:
            rows.append((cells[0], name, pts))
    return rows

def _extract_hytek_team_rankings(text):
    """Extract (rank, name, points) rows from a HY-TEK "Team Rankings"
    block, which MileSplit sometimes appends at the bottom of a full raw
    results dump (after every individual/relay result) instead of posting a
    standalone team-scores page. Two "<rank>) <name> <points>" entries are
    laid out side by side per line, so scan for all matches rather than
    splitting by line."""
    idx = text.find("Team Rankings")
    if idx == -1:
        return []
    rows = []
    for m in re.finditer(r"(\d+)\)\s*(.+?)\s+(\d+(?:\.\d+)?)(?=\s|$)", text[idx:]):
        name = m.group(2).strip()
        if name:
            rows.append((m.group(1), name, float(m.group(3))))
    return rows

def _extract_columnar_score_rows(pre_text):
    """Extract (rank, name, points) rows from MileSplit's column-serialized
    team-scores block: instead of one row per line, the "Pl", "Team", "Code"
    and "Score" columns are each dumped as their own contiguous run of
    lines -- headers ("Pl"/"Team", later "Code"/"Score") appear back to
    back, followed by that many lines of values. A rank/name pair for a
    double-digit or tied place is sometimes collapsed onto a single
    "<rank> <name>" line instead of two separate lines -- so rather than
    assume one value per line, split any leading-digit line into its
    numeric prefix (a place) and text remainder (a name) and append each
    piece to its own column list; wherever two values share a line, they
    still land at the same position in both lists, so places[i]/names[i]
    stay paired by index. The Score column is the last one dumped, so its
    values are simply the final len(places) lines of the block.
    """
    lines = [l.strip() for l in pre_text.strip().splitlines() if l.strip()]
    if len(lines) < 4 or lines[1] != "Pl" or lines[2] != "Team":
        return []
    try:
        code_idx = lines.index("Code")
        score_idx = lines.index("Score")
    except ValueError:
        return []

    places, names = [], []
    for line in lines[3:code_idx]:
        m = re.match(r"^(\d+)(?:\s+(.*))?$", line)
        if m:
            places.append(m.group(1))
            if m.group(2):
                names.append(m.group(2))
        else:
            names.append(line)

    tail = lines[score_idx + 1:]
    if not places or len(places) != len(names) or len(tail) < len(places):
        return []
    scores_raw = tail[-len(places):]
    try:
        scores = [abs(float(s)) for s in scores_raw]
    except ValueError:
        return []
    return list(zip(places, names, scores))

def _truncate_to_tenth(value):
    """Truncate (not round) to one decimal place, matching MileSplit's own
    posted-score display convention. A tied last-scoring place split three
    or more ways lands on a repeating or two-decimal fraction (e.g. a 4-way
    tie for 8th splits 1 point into 0.25 each) that MileSplit's site prints
    chopped to one decimal rather than rounded -- 0.25 shows as ".2", not
    ".3". Comparing (and displaying) on this same truncated basis avoids
    flagging that display limit as a scoring mismatch, without touching the
    DB's own exact stored values.
    """
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_DOWN))

def compare_scores_by_rank(computed_ranked, reference_ranked, tolerance=0.01):
    """Compare two (name, points) lists by rank position rather than by name.

    School names can be formatted differently between the DB and whatever is
    pasted from MileSplit, so pairing is done purely by descending-score rank;
    the caller visually confirms the paired names refer to the same school.

    Both sides are compared (and reported) after truncating to one decimal --
    see _truncate_to_tenth() -- since MileSplit's own posted totals are
    already truncated to that precision, and our exact DB computation
    shouldn't be flagged as wrong just for carrying more precision than
    MileSplit's display does.
    """
    computed_sorted = sorted(computed_ranked, key=lambda x: x[1], reverse=True)
    reference_sorted = sorted(reference_ranked, key=lambda x: x[1], reverse=True)

    rows = []
    all_match = len(computed_sorted) == len(reference_sorted)
    for i in range(max(len(computed_sorted), len(reference_sorted))):
        comp = computed_sorted[i] if i < len(computed_sorted) else None
        ref = reference_sorted[i] if i < len(reference_sorted) else None
        comp_pts = _truncate_to_tenth(comp[1]) if comp else None
        ref_pts = _truncate_to_tenth(ref[1]) if ref else None
        match = comp_pts is not None and ref_pts is not None and abs(comp_pts - ref_pts) < tolerance
        all_match = all_match and match
        rows.append({
            "rank": i + 1,
            "computed_name": comp[0] if comp else None,
            "computed_pts": comp_pts,
            "reference_name": ref[0] if ref else None,
            "reference_pts": ref_pts,
            "match": match,
        })
    return rows, all_match

def _safe_get(session, url, retries=2):
    for attempt in range(retries + 1):
        time.sleep(0.5)
        try:
            r = session.get(url, timeout=20)
            r.raise_for_status()
            return r
        except Exception:
            if attempt == retries:
                return None
            time.sleep(1)

def _ihsaa_tournament_url(year, gender, meet_type):
    gender_slug = "boys" if str(gender).strip().lower() == "boys" else "girls"
    start_year = int(year) - 1
    season_slug = f"{start_year}-{int(year) % 100:02d}"
    mt = (meet_type or "").strip().lower()
    round_slug = "sectionals" if mt == "sectional" else "regionals" if mt == "regional" else "state-finals"
    return f"https://www.ihsaa.org/sports/{gender_slug}/track-field/{season_slug}-tournament?round={round_slug}"

def _extract_meet_num_from_row(text):
    s = re.sub(r"\s+", " ", text or "").strip()
    m = re.search(r"(?:^|\b)(\d{1,2})\.\s*[^|]+?\s*\(", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:^|\b)(\d{1,2})\.\s*.+?\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*(?:CT|ET)\b", s, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None

def _normalize_text(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()

def _is_target_meet_anchor(anchor_text, meet_type, meet_num, gender):
    t = _normalize_text(anchor_text)
    if "ihsaa" not in t:
        return False
    if gender.lower() not in t:
        return False

    mt = meet_type.lower()
    if mt == "state":
        return ("state" in t) and ("sectional" not in t) and ("regional" not in t)

    if mt not in t:
        return False

    return bool(re.search(rf"\b{re.escape(str(meet_num))}\b", t))

_INDEX_MONTHS = [5, 6]  # IHSAA track & field season runs May-June

def _find_meet_url_via_monthly_search(session, meet_type, meet_number, gender, year):
    """Fallback for meets IHSAA's tournament page doesn't link to a MileSplit
    page for -- State Finals results are posted as an IHSAA-hosted PDF and a
    separate timing site instead, so there's no MileSplit URL to find there.
    Searches MileSplit's own monthly results index directly instead."""
    for month in _INDEX_MONTHS:
        page = 1
        max_pages = 5
        while page <= max_pages:
            index_url = f"{BASE}/results?month={month}&year={year}&level=hs&page={page}"
            r = _safe_get(session, index_url)
            if r is None:
                break

            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                text = a.get_text(" ", strip=True)
                href = a.get("href", "").strip()
                if not text or "/meets/" not in href:
                    continue
                if not _is_target_meet_anchor(text, meet_type, meet_number, gender):
                    continue
                return href if href.startswith("http") else urljoin(BASE, href)

            if not soup.find("a", string=re.compile(r"next", re.IGNORECASE)):
                break
            page += 1

    return None

def find_meet_url(session, meet_type, meet_number, gender, year):
    """Find this meet's MileSplit results URL via the IHSAA tournament page,
    falling back to MileSplit's own monthly results index when IHSAA doesn't
    link to a MileSplit page for this meet at all (State Finals)."""
    r = _safe_get(session, _ihsaa_tournament_url(year, gender, meet_type))
    if r is None:
        return _find_meet_url_via_monthly_search(session, meet_type, meet_number, gender, year)

    mt = (meet_type or "").strip().lower()
    gender_lc = str(gender).strip().lower()
    year_int = int(year)

    if mt in ("regional", "state"):
        if mt == "regional":
            slug_re = rf"/meets/(\d+)-ihsaa-regional-?(\d*)-{re.escape(gender_lc)}-{year_int}"
        else:
            slug_re = rf"/meets/(\d+)-ihsaa-state(?:-finals?)?-?(\d*)-{re.escape(gender_lc)}-{year_int}"
        for m in re.finditer(slug_re, r.text):
            meet_id_str, num_str = m.group(1), m.group(2)
            num = int(num_str) if num_str else 1
            if num == int(meet_number):
                return f"{BASE}/meets/{meet_id_str}/results"
        return _find_meet_url_via_monthly_search(session, meet_type, meet_number, gender, year)

    # Sectional: bare-URL rows, meet number parsed from the row text.
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if "in.milesplit.com" not in href or "/results" not in href:
            continue
        if re.search(r"/meets/\d+-ihsaa-", href):
            continue
        anchor_label = a.get_text(" ", strip=True)
        if "result" not in re.sub(r"[^a-z0-9]+", " ", anchor_label.lower()):
            continue
        row_text = a.parent.get_text(" ", strip=True) if a.parent is not None else anchor_label
        t = re.sub(r"[^a-z0-9]+", " ", row_text.lower())
        wants_boys = gender_lc == "boys"
        has_boys, has_girls = "boys" in t, "girls" in t
        if (has_boys and not has_girls and not wants_boys) or (has_girls and not has_boys and wants_boys):
            continue
        if _extract_meet_num_from_row(row_text) == int(meet_number):
            return href if href.startswith("http") else f"{BASE}{href}"
    return _find_meet_url_via_monthly_search(session, meet_type, meet_number, gender, year)

def fetch_team_scores_text(meet_type, meet_number, gender, year, log_fn=print):
    """Best-effort auto-fetch of MileSplit's posted team-scores text for this
    meet. Returns the raw score-listing text on success, or None if any step
    fails -- the caller should fall back to manual paste in that case.
    """
    if not AUTO_FETCH_AVAILABLE:
        log_fn("  Auto-fetch skipped: 'requests'/'bs4' not installed in this environment.")
        return None

    session = requests.Session()
    session.headers.update(HEADERS)

    meet_url = find_meet_url(session, meet_type, meet_number, gender, year)
    if not meet_url:
        log_fn("  Auto-fetch: could not find this meet on the IHSAA tournament page.")
        return None

    r = _safe_get(session, meet_url)
    if r is None:
        log_fn("  Auto-fetch: could not load the meet's results page.")
        return None
    result_ids = re.findall(r"/results/(\d+)", r.text)
    if not result_ids:
        log_fn("  Auto-fetch: no results id found on the meet page.")
        return None

    r2 = _safe_get(session, f"{meet_url}/{result_ids[0]}/raw")
    if r2 is None:
        log_fn("  Auto-fetch: could not load the results detail page.")
        return None
    candidate_ids = []
    for rid, _label in re.findall(
        r'<option value="[^"]*?/results/(\d+)[^"]*"[^>]*>\s*([^<]+?)\s*</option>', r2.text
    ):
        if rid not in candidate_ids:
            candidate_ids.append(rid)
    if not candidate_ids:
        log_fn("  Auto-fetch: no results options found in the More Results dropdown.")
        return None

    # Dropdown labels aren't consistent ("Team Scores" vs "...Team S" vs
    # nothing at all), so don't filter by label -- try every option and keep
    # whichever one's raw page actually contains a parseable score listing.
    # Some meets post a single combined raw page (team scores followed by the
    # full event-by-event heat sheets); parse_reference_scores only reads the
    # first contiguous block, but a heat sheet's placings can *themselves*
    # look like a short score table. The real tiebreaker: a team can only
    # appear once in an actual team-scores table, while heat results
    # routinely repeat a school (teammates in the same event) -- so reject
    # any candidate whose parsed names contain a duplicate.
    for rid in candidate_ids:
        r3 = _safe_get(session, f"{meet_url}/{rid}/raw")
        if r3 is None:
            continue

        m = re.search(r"<pre>(.*?)</pre>", r3.text, re.DOTALL)
        pre_text = html.unescape(m.group(1)) if m else ""

        if pre_text:
            rows = _parse_score_lines(pre_text)
            names = [name for name, _ in rows]
            if len(rows) >= 2 and len(names) == len(set(names)):
                return pre_text

            # Some meets post a single combined raw page (a HY-TEK "Team
            # Rankings" block appended after the full event-by-event heat
            # sheets) instead of a standalone score table.
            hytek_rows = _extract_hytek_team_rankings(pre_text)
            names = [name for _, name, _ in hytek_rows]
            if len(hytek_rows) >= 2 and len(names) == len(set(names)):
                return "\n".join(f"{rank} {name} {pts}" for rank, name, pts in hytek_rows)

            # Some meets post the score table column-serialized (Pl/Team/
            # Code/Score each dumped as their own run of lines) instead of
            # one row per line.
            col_rows = _extract_columnar_score_rows(pre_text)
            names = [name for _, name, _ in col_rows]
            if len(col_rows) >= 2 and len(names) == len(set(names)):
                return "\n".join(f"{rank} {name} {pts}" for rank, name, pts in col_rows)

        # Some meets post the score table as an HTML <table> instead of a
        # <pre> text listing.
        table_rows = _extract_table_score_rows(r3.text)
        names = [name for _, name, _ in table_rows]
        if len(table_rows) >= 2 and len(names) == len(set(names)):
            return "\n".join(f"{rank} {name} {pts}" for rank, name, pts in table_rows)

    log_fn(f"  Auto-fetch: none of the {len(candidate_ids)} dropdown options produced team scores.")
    return None

def process_meet(db, meet_type, meet_number, gender, year, out):
    """Compute DB team scores, auto-fetch MileSplit's posted scores, and
    write a comparison block for one meet via out(). Returns a short status
    string: "match", "mismatch", "not_found", or "fetch_failed".
    """
    out(f"Year: {year}")
    out(f"Gender: {gender}")
    out(f"{meet_type} #: {meet_number}")
    out("-" * 40)

    scoring = STATE_SCORING if (meet_type or "").strip().lower() == "state" else SECTIONAL_REGIONAL_SCORING
    top_n = len(scoring)
    meet_id = db.get_meet_id(meet_type, meet_number, year, gender)
    if meet_id is None:
        out("No such meet found in Track.db.")
        out("RESULT: SKIPPED - meet not in DB\n")
        return "not_found"

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
    # Alphabetical-by-school-name secondary sort for equal-points ties --
    # standardizes on the tiebreak convention used by the regional/state/
    # projected-team-scores prediction scripts.
    scores = dict(
        sorted(
            scores.items(),
            key=lambda item: (-item[1], db.get_school_name(int(item[0])) or ""),
        )
    )

    reference_scores_text = fetch_team_scores_text(meet_type, meet_number, gender, year, log_fn=out)
    if not reference_scores_text:
        out("RESULT: SKIPPED - auto-fetch failed\n")
        return "fetch_failed"

    computed_ranked = [
        (db.get_school_name(int(sid)) or str(sid), pts) for sid, pts in scores.items()
    ]
    reference_ranked = list(parse_reference_scores(reference_scores_text).items())
    rows, all_match = compare_scores_by_rank(computed_ranked, reference_ranked)

    out("{:<30}{:>8}   {:<30}{:>8}".format("Team (DB)", "Pts", "Team (MileSplit)", "Pts"))
    for r in rows:
        comp_name = r["computed_name"] or "-"
        comp_pts = f'{r["computed_pts"]:.1f}' if r["computed_pts"] is not None else "-"
        ref_name = r["reference_name"] or "-"
        ref_pts = f'{r["reference_pts"]:.1f}' if r["reference_pts"] is not None else "-"
        out("{:<30}{:>8}   {:<30}{:>8}".format(comp_name, comp_pts, ref_name, ref_pts))

    out(f"\nRESULT: {'MATCH' if all_match else 'NOT MATCH'}\n")
    return "match" if all_match else "mismatch"

def main():
    year = 2026
    gender = "Boys"
    meet_type = "State"
    meet_numbers = range(1, 2)

    db = Database(CONST.DB_PATH)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(script_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{year}_{gender}_{meet_type}.log")

    status_labels = {
        "match": "MATCH",
        "mismatch": "NOT MATCH",
        "not_found": "SKIPPED - meet not in DB",
        "fetch_failed": "SKIPPED - auto-fetch failed",
    }

    with open(log_path, "w", encoding="utf-8") as log_file:
        def out(msg=""):
            log_file.write(str(msg) + "\n")

        for meet_number in meet_numbers:
            meet_label = f"{meet_type} {meet_number} {year} {gender}"
            status = process_meet(db, meet_type, meet_number, gender, year, out)
            print(f"[{meet_label}] {status_labels[status]}")

    print(f"\nDone. Full results in {log_path}")

if __name__ == "__main__":
    main()
