"""School Dashboard V4 -- precomputed payloads, and the lookup that serves them.

    Raw results ──► build_payload() ──► dashboard_cache.db ──► load_payload() ──► template

WHY A DATABASE AND NOT JSON FILES
---------------------------------
There are roughly 5,000 payloads (414 schools x 2 genders x 6 season choices).
Sharded into one JSON file per gender/season, each file is 6-12MB and a worker
has to parse the whole thing to answer for one school -- which on PythonAnywhere
means megabytes of parsing and resident memory per worker, for one row. SQLite
answers the same question with one indexed lookup in about a millisecond, at
constant memory, and is already a dependency. The cache is a derived artifact, so
it lives in its own file rather than in Track.db: regenerating it never risks the
source data, and deleting it is always safe.

WHAT IS PRECOMPUTED VS WHAT HAPPENS PER REQUEST
-----------------------------------------------
Everything expensive is precomputed: statewide rankings, qualifier lists, the
near-miss selection, head-to-head, returning athletes, and the season summary.
A request does exactly one indexed SELECT, one json.loads, and renders. No
analysis of any kind happens while a visitor waits.

ON REUSING THE QUERY LAYER
--------------------------
build_payload() calls the existing query functions. That is deliberate. What
made V3 slow was running that analysis *per request*, not the analysis itself -- and those functions encode the scoring rules, advancement
rules and ranking methodology, which are the parts that must not change. Rewriting
them from scratch would risk quietly altering published results to no benefit,
since this code now runs offline where its speed barely matters. The request path
below shares nothing with V3.
"""
import hashlib
import json
import os
import re
import sqlite3
import time
import zlib
from datetime import datetime, timezone
from functools import lru_cache

from common.const import CONST

# Bumped when the shape of a payload changes, so a cache written by older code is
# recognised as unreadable rather than rendering into a template that has moved on.
DATA_VERSION = 1
# Bumped when the numbers themselves would change -- a new ranking formula, a
# different near-miss rule. Lets "why does this say 166th" be answered later.
METHODOLOGY_VERSION = 1

CACHE_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'dashboard_cache.db')

# The near-miss rule, measured across the 2026 postseason: entries within 3% of
# the cut sit a median of one place out of it, and the cut itself falls at a
# median place of 4th. Below the floor the list would be empty for the many
# schools with nobody close, which is exactly when "who came nearest" is asked;
# above the cap it stops being a shortlist.
CLOSEST_SHARE = 0.03
CLOSEST_MIN = 3
CLOSEST_MAX = 8


# --------------------------------------------------------------------- reading

def _connect(readonly=True):
    path = os.path.abspath(CACHE_DB_PATH)
    if readonly:
        # A read-only handle cannot create an empty database by accident, which
        # is what turns "cache missing" into "cache silently always empty".
        return sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return sqlite3.connect(path)


def load_payload(school_id, gender, season):
    """The whole dashboard for one school/gender/season, or None.

    One indexed lookup. This is the entire request-time data path.
    """
    try:
        conn = _connect(readonly=True)
    except sqlite3.OperationalError:
        return None
    try:
        row = conn.execute(
            "SELECT payload FROM dashboard WHERE school_id=? AND gender=? AND season=?",
            (int(school_id), str(gender), str(season)),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row:
        return None
    return _decode(row[0])


def _encode(payload):
    """JSON, deflated.

    The payloads are repetitive JSON -- the same event names, grades and keys in
    every one -- so they compress about 80%, taking the whole cache from 45MB to
    roughly 9MB. That is the difference between an artifact that is awkward to
    commit and one that ships with the code like Track.db does. Decompressing one
    costs about 12 microseconds, which is nothing against a page render.
    """
    return zlib.compress(
        json.dumps(payload, separators=(',', ':'), default=str).encode('utf-8'), 6)


def _decode(blob):
    """Read a payload, compressed or not.

    Plain text is still accepted so a cache written before compression keeps
    working rather than turning every page into an error.
    """
    try:
        if isinstance(blob, bytes):
            try:
                blob = zlib.decompress(blob)
            except zlib.error:
                pass
            blob = blob.decode('utf-8')
        return json.loads(blob)
    except (ValueError, UnicodeDecodeError):
        return None


def load_rankings(gender, season, event=''):
    """One ranked list: the statewide program table, or one event's field.

    Same shape as load_payload -- a single indexed lookup -- but fetched by the
    page only when a reader actually opens a rank.
    """
    try:
        conn = _connect(readonly=True)
    except sqlite3.OperationalError:
        return None
    try:
        row = conn.execute(
            "SELECT payload FROM rankings WHERE gender=? AND season=? AND event=?",
            (str(gender), str(season), str(event or '')),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return _decode(row[0]) if row else None


def cache_meta():
    """Provenance of the cache: when it was built, and from what."""
    try:
        conn = _connect(readonly=True)
    except sqlite3.OperationalError:
        return {}
    try:
        return dict(conn.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def season_choices(school_id, gender):
    """Which seasons this school actually has a payload for."""
    try:
        conn = _connect(readonly=True)
    except sqlite3.OperationalError:
        return []
    try:
        rows = conn.execute(
            "SELECT season FROM dashboard WHERE school_id=? AND gender=?",
            (int(school_id), str(gender)),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [r[0] for r in rows]


# ------------------------------------------------------------------ live build

def live_seasons(school_id, gender):
    """Seasons a reader could pick, from the database rather than the cache.

    season_choices() answers from the cache, so it returns nothing when there is
    no cache -- which is exactly when this is needed. Mirrors the job's own
    seasons_for(): every ranked season newest first, then all-time.
    """
    from .. import queries
    years = sorted(queries._covered_rank_seasons(), reverse=True)
    return [str(y) for y in years] + ['all-time']


def live_payload(school_id, gender, season=None):
    """Build a payload now instead of reading one, or None if there is nothing.

    For development only -- see allow_live_build(). Roughly 2s for the first
    school in a process (it builds the statewide ranking tables, which are then
    cached) and about 0.2s for each one after.

    With no season, tries the newest first and takes the first that produces
    anything, since a school need not have competed in every season.
    """
    seasons = [season] if season else live_seasons(school_id, gender)
    for candidate in seasons:
        try:
            payload = build_payload(school_id, gender, candidate)
        except Exception:  # noqa: BLE001
            # One unbuildable season should not stop the page finding another.
            continue
        if payload:
            return payload
    return None


def allow_live_build(app):
    """Whether this process may compute a dashboard instead of reading one.

    Never on the deployed site. The whole reason the cache exists is that this
    analysis took seconds per page, and PythonAnywhere measured 15-25x slower
    than a development machine -- so a fallback that quietly turned itself on in
    production would restore the exact problem V4 was built to remove, and it
    would do it silently, under load, one worker at a time.

    So: debug mode, or an explicit opt-in. Same shape as the timings flag above
    it, and for the same reason.
    """
    import os
    if os.environ.get('TI_LIVE_DASHBOARD') == '1':
        return True
    return bool(app.debug)


# --------------------------------------------------------------------- shaping

ROMAN_SUFFIX = re.compile(r'^(?:II|III|IV|VI{0,3}|IX|XI{0,3})$')
GEN_SUFFIX = re.compile(r'^(JR|SR)(\.?)$')


def _person_name(value):
    """Athlete names are stored shouting; print them as names.

    The rules are the ones V3 arrived at by looking at real data: roman-numeral
    suffixes stay capitalised, "Mc" takes a capital after it but "Mac" does not
    (MACIAS and MACKENZIE are ordinary names), and an apostrophe capitalises the
    next letter only when a single letter precedes it -- O'Brien does, Ahli'yla
    does not.
    """
    if not value:
        return ''
    words = []
    for word in str(value).split(' '):
        if not word:
            words.append(word)
            continue
        bare = word.upper()
        if ROMAN_SUFFIX.match(bare):
            words.append(bare)
            continue
        gen = GEN_SUFFIX.match(bare)
        if gen:
            words.append(gen.group(1)[0] + gen.group(1)[1].lower() + gen.group(2))
            continue
        parts = []
        for part in word.split('-'):
            lower = part.lower()
            if not lower:
                parts.append(part)
                continue
            out = re.sub(r'[a-z]', lambda m: m.group(0).upper(), lower, count=1)
            out = re.sub(r'^(\W*)Mc([a-z])',
                         lambda m: m.group(1) + 'Mc' + m.group(2).upper(), out)
            out = re.sub(r"^(\W*[A-Za-z])'([a-z])",
                         lambda m: m.group(1) + "'" + m.group(2).upper(), out)
            parts.append(out)
        words.append('-'.join(parts))
    return ' '.join(words)


def _display_name(row):
    """A relay is named "Relay", not by its school.

    The payload carries the school name, which on this page is the school the
    reader is already looking at -- printed once per relay row under a masthead
    that says it. One word instead answers what the cell is for: this entry is a
    squad, not a person, so there is nobody to click.
    """
    if row.get('entry_type') == 'relay' or not row.get('athlete_id'):
        return 'Relay'
    return _person_name(row.get('name'))


def _entry(row, stage):
    """One qualifying entry, flattened to what the table prints."""
    cell = (row.get('stages') or {}).get(stage) or {}
    place = cell.get('place')
    return {
        'name': _display_name(row),
        'athlete_id': row.get('athlete_id'),
        'grade': row.get('grade'),
        'event': row.get('event'),
        'is_relay': row.get('entry_type') == 'relay' or not row.get('athlete_id'),
        'mark': cell.get('mark_display'),
        'has_mark': cell.get('has_mark', True),
        'place': place,
        'prelim': cell.get('round') == 'Prelim',
    }


def _sort_entries(entries):
    """Named athletes first by surname, then relays by distance."""
    def surname(name):
        parts = str(name or '').strip().split()
        return (parts[-1] if parts else '').lower()

    def relay_distance(event):
        import re
        m = re.search(r'x\s*(\d+)', str(event or ''), re.I)
        return int(m.group(1)) if m else 9999

    people = [e for e in entries if not e['is_relay']]
    relays = [e for e in entries if e['is_relay']]
    people.sort(key=lambda e: (surname(e['name']), e['name'] or '', e['event'] or ''))
    relays.sort(key=lambda e: relay_distance(e['event']))
    return people + relays


def _just_missed(rows):
    """Entries nearest the regional cut, ordered by how near.

    Ranked on the gap as a share of the cutoff rather than the raw gap: 0.29s in
    the 100 and 10 inches in the long jump are not the same distance from
    qualifying, and raw numbers would put the sprints on top every time. Entries
    past the threshold are kept only to reach the floor, and marked so the page
    can show that they were not actually close.
    """
    scored = []
    for row in rows:
        gap, cut = row.get('gap_value'), row.get('cutoff_value')
        if row.get('final_stage') != 'Sectional':
            continue
        if not (isinstance(gap, (int, float)) and gap > 0):
            continue
        if not (isinstance(cut, (int, float)) and cut > 0):
            continue
        scored.append((gap / cut, row))
    scored.sort(key=lambda pair: pair[0])

    inside = sum(1 for share, _ in scored if share <= CLOSEST_SHARE)
    keep = scored[:min(CLOSEST_MAX, max(CLOSEST_MIN, inside))]

    out = []
    for share, row in keep:
        out.append({
            'name': _display_name(row),
            'athlete_id': row.get('athlete_id'),
            'grade': row.get('grade'),
            'event': row.get('event'),
            'is_relay': row.get('entry_type') == 'relay' or not row.get('athlete_id'),
            'gap': row.get('gap_display'),
            'share_pct': round(share * 100, 1),
            'cutoff': row.get('cutoff_display'),
            'cutoff_path': row.get('cutoff_path'),
            # Outside the line, present only to reach the floor.
            'far': share > CLOSEST_SHARE,
        })
    return out


def _spark(history):
    """Geometry for the rank trend line, prepared here rather than in the page.

    Rank 1 is the best but the smallest number, so the line is inverted: better
    seasons sit higher. Toned on the most recent three seasons rather than the
    whole span -- a program that was 60th eight years ago and has slid every year
    since still ends "up" against its first season, and a green line over a
    falling plot says the opposite of what the plot shows.
    """
    if not history or len(history) < 2:
        return None
    width, height, pad_x, pad_y = 900, 132, 26, 16
    ranks = [h['rank'] for h in history]
    best, worst = min(ranks), max(ranks)
    span = max(1, worst - best)
    points = []
    for i, h in enumerate(history):
        points.append({
            'x': round(pad_x + (i / (len(history) - 1)) * (width - pad_x * 2), 1),
            'y': round(pad_y + ((h['rank'] - best) / span) * (height - pad_y * 2), 1),
            'season': h['season'],
            'rank': h['rank'],
            'total': h['total_schools'],
        })
    recent = history[max(0, len(history) - 3)]
    return {
        'width': width,
        'height': height,
        'path': ' '.join(('M' if i == 0 else 'L') + '%s %s' % (p['x'], p['y'])
                         for i, p in enumerate(points)),
        'points': points,
        # Two tones only: green when the recent seasons are climbing, amber
        # otherwise. Flat and falling are the same message to a coach.
        'tone': 'up' if recent['rank'] - history[-1]['rank'] > 0 else 'down',
        'seasons': len(history),
    }


def _results_rows(rows, stages_present):
    """The complete playoff table, one row per entry."""
    out = []
    for row in rows:
        if row.get('entry_type') in (None, 'none'):
            out.append({'event': row.get('event'), 'empty': True})
            continue
        cells = row.get('stages') or {}
        out.append({
            'event': row.get('event'),
            'name': _display_name(row),
            'athlete_id': row.get('athlete_id'),
            'grade': row.get('grade'),
            'is_relay': row.get('entry_type') == 'relay' or not row.get('athlete_id'),
            'badge': 'SQ' if 'State' in cells else ('RQ' if 'Regional' in cells else None),
            'rank': row.get('rank'),
            'rank_total': row.get('rank_total'),
            'best_stage': row.get('best_stage'),
            'gap': row.get('gap_display'),
            'final_stage': row.get('final_stage'),
            'tied_cutoff': row.get('tied_cutoff'),
            'cells': {
                stage: {
                    'mark': (cells.get(stage) or {}).get('mark_display'),
                    'place': (cells.get(stage) or {}).get('place'),
                    'prelim': (cells.get(stage) or {}).get('round') == 'Prelim',
                    'has_mark': (cells.get(stage) or {}).get('has_mark', True),
                }
                for stage in stages_present if cells.get(stage)
            },
        })
    return out


# -------------------------------------------------------------------- building

def build_payload(school_id, gender, season):
    """Assemble everything the V4 page renders for one school/gender/season.

    Only the precompute job calls this. The query layer is imported here rather
    than at module scope so that a route importing this module for load_payload()
    -- the only thing a request needs -- does not pay for the whole query layer.
    """
    from .. import queries

    core = queries.get_school_season_core(school_id, gender=gender, season=season)
    if not core:
        return None

    filters = core['filters']
    selected = filters['selected_season']
    is_all_time = str(selected) == 'all-time'

    payload = {
        'school': core['school'],
        'filters': {
            'selected_gender': filters['selected_gender'],
            'selected_season': str(selected),
            'genders': filters.get('genders') or [],
            'seasons': [str(s) for s in (filters.get('seasons') or [])],
            'season_labels': {str(k): v for k, v in (filters.get('season_labels') or {}).items()},
        },
        'overview': {'stages': [], 'deltas': {}},
        'regional': {'qualifiers': [], 'just_missed': []},
        'state': {'qualifiers': []},
        'rank': None,
        'outlook': {'h2h': None, 'returning': None},
        'results': {'stages': [], 'rows': []},
    }

    stage_results = core.get('stage_results')
    if stage_results:
        # The rounds do not mean the same thing, so they are not labelled the
        # same. An entry at the sectional is somebody the school entered; an
        # entry at the regional is somebody who earned their way there, which is
        # the number a coach is counting.
        labels = {
            'Sectional': ('Sectionals', 'Entries', 'Placers'),
            'Regional': ('Regionals', 'Qualifiers', 'Placers'),
            'State': ('State', 'Qualifiers', 'Placers'),
        }
        stages = []
        for stage in (stage_results.get('stages') or []):
            heading, count_label, scoring_label = labels.get(
                stage.get('stage'), (stage.get('stage'), 'Entries', 'Placers'))
            stages.append({
                'heading': heading,
                'count_label': count_label,
                'count': stage.get('entries') or 0,
                'scoring_label': scoring_label,
                'scoring': stage.get('scoring_finishes') or 0,
                'attended': stage.get('attended'),
                'points': stage.get('points_display'),
                'team_rank': stage.get('team_rank'),
                'total_teams': stage.get('total_teams'),
            })
        payload['overview']['stages'] = stages
        payload['overview']['year'] = stage_results.get('year')

    # The per-entry table drives three of the five tabs, so it is fetched once.
    scorecard = queries.get_athlete_scorecard(
        school_id, gender, str(selected))
    rows = (scorecard or {}).get('rows') or []
    stages_present = (scorecard or {}).get('stages_present') or []
    entered = [r for r in rows if r.get('entry_type') and r.get('entry_type') != 'none']

    payload['results']['stages'] = stages_present
    payload['results']['rows'] = _results_rows(rows, stages_present)
    payload['results']['mode'] = (scorecard or {}).get('mode')

    if not is_all_time and (scorecard or {}).get('mode') != 'records':
        payload['regional']['qualifiers'] = _sort_entries(
            [_entry(r, 'Regional') for r in entered if (r.get('stages') or {}).get('Regional')])
        payload['state']['qualifiers'] = _sort_entries(
            [_entry(r, 'State') for r in entered if (r.get('stages') or {}).get('State')])
        payload['regional']['just_missed'] = _just_missed(entered)

        year = int(selected)
        rank = queries.get_program_rank(school_id, gender, year)
        if rank:
            history = rank.get('rank_history') or []
            prior = rank.get('prior_rank') or None
            payload['rank'] = {
                'rank': rank.get('rank'),
                'is_ranked': rank.get('is_ranked'),
                'total_schools': rank.get('total_schools'),
                'percentile': rank.get('percentile'),
                'composite_score': rank.get('composite_score'),
                'entry_slots': rank.get('entry_slots'),
                'history': [
                    {'season': h['season'], 'rank': h['rank'], 'total': h['total_schools']}
                    for h in history
                ],
                'prior': ({'season': prior['season'], 'rank': prior['rank']} if prior else None),
                'movement': rank.get('rank_movement'),
                'spark': _spark(history),
            }

        h2h = queries.get_season_h2h(school_id, gender, str(selected))
        if h2h and h2h.get('available') and h2h.get('seasons'):
            latest = h2h['seasons'][0]
            payload['outlook']['h2h'] = {
                'season': latest['season'],
                'result': latest['result'],
                'points_for': latest['points_for'],
                'points_against': latest['points_against'],
                'events_won': latest['events_won'],
                'events_lost': latest['events_lost'],
            }
        elif h2h:
            payload['outlook']['h2h'] = {'reason': h2h.get('reason')}

        ret = queries.get_returning_athletes(school_id, gender, str(selected))
        if ret and ret.get('available'):
            points = ret.get('points') or {}
            payload['outlook']['returning'] = {
                'next_year': ret.get('next_year'),
                'athletes_returning': (ret.get('retention') or {}).get('athletes_returning'),
                'athletes_total': (ret.get('retention') or {}).get('athletes_total'),
                'points_returning': points.get('points_returning'),
                'points_total': points.get('points_total'),
            }
        elif ret:
            payload['outlook']['returning'] = {'reason': ret.get('reason')}

    # The State tab is not rendered at all when nobody reached it, so the tab
    # strip can decide without inspecting the lists.
    payload['has_state'] = bool(payload['state']['qualifiers'])
    payload['has_regional'] = bool(
        payload['regional']['qualifiers'] or payload['regional']['just_missed'])
    return payload


def build_rankings(gender, season):
    """Every ranked list for one gender/season, as (event, payload) pairs.

    Trimmed to what the popup prints. The underlying rows carry meet ids, event
    types and lineups that no reader sees, and keeping them would multiply the
    size of the one artifact that has to stay small enough to commit.
    """
    from sqlalchemy.orm import joinedload

    from ..models import School
    from ..queries.program_rankings import _build_statewide_program_rankings
    from ..queries.scorecard import _event_ranked_rows, _relay_ranked_rows
    from ..queries.shared import _resolve_school_enrollment_for_year

    if str(season) == 'all-time':
        return []
    year = int(season)
    out = []

    # Enrollment for every school, resolved once. The popup filters on it, and
    # looking it up per row would be 394 lookups for the program table alone.
    enrollments = {}
    for school in School.query.options(joinedload(School.enrollments)).all():
        meta = _resolve_school_enrollment_for_year(school, year)
        enrollments[school.school_id] = meta.get('value')

    table = _build_statewide_program_rankings(gender, year)
    out.append(('', {
        'kind': 'program',
        'title': 'Statewide Program Rankings',
        'subtitle': '%s %s \u2014 %d ranked programs' % (
            gender, year, len(table['leaderboard'])),
        'columns': ['Rank', 'School', 'Composite', 'Enrollment'],
        'rows': [
            {
                'rank': row['rank'],
                'school_id': row['school_id'],
                'name': row['school_name'],
                'value': round(row['composite_score'], 1)
                if isinstance(row.get('composite_score'), (int, float)) else None,
                'enrollment': enrollments.get(row['school_id']),
            }
            for row in table['leaderboard']
        ],
    }))

    for source, is_relay in ((_event_ranked_rows, False),
                             (_relay_ranked_rows, True)):
        for event, rows in (source(gender, year) or {}).items():
            out.append((event, {
                'kind': 'event',
                'title': event,
                'subtitle': '%s %s \u2014 %d %s ranked' % (
                    gender, year, len(rows), 'relays' if is_relay else 'athletes'),
                'columns': ['Rank', 'Relay' if is_relay else 'Athlete', 'School',
                            'Mark', 'Enrollment'],
                'rows': [
                    {
                        'rank': row.get('rank'),
                        'athlete_id': None if is_relay else row.get('athlete_id'),
                        'name': 'Relay' if is_relay else _person_name(row.get('athlete_name')),
                        'school_id': row.get('school_id'),
                        'school': row.get('school_name'),
                        'mark': row.get('result'),
                        'enrollment': enrollments.get(row.get('school_id')),
                    }
                    for row in rows
                ],
            }))
    return out


# --------------------------------------------------------------------- writing

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS dashboard (
    school_id INTEGER NOT NULL,
    gender    TEXT    NOT NULL,
    season    TEXT    NOT NULL,
    payload   TEXT    NOT NULL,
    PRIMARY KEY (school_id, gender, season)
);
-- The lists a rank came out of. Shared by every school, so they are stored once
-- per gender/season rather than copied into 414 payloads -- the statewide
-- leaderboard alone would have added megabytes to a cache that is 10MB whole.
-- Fetched only when a reader opens one.
CREATE TABLE IF NOT EXISTS rankings (
    gender  TEXT NOT NULL,
    season  TEXT NOT NULL,
    event   TEXT NOT NULL,   -- '' for the statewide program leaderboard
    payload TEXT NOT NULL,
    PRIMARY KEY (gender, season, event)
);
"""


def write_cache(rows, source_size, ranking_rows=()):
    """Replace the cache with `rows` of (school_id, gender, season, payload).

    Built into a temporary file and moved into place, so a half-written cache is
    never visible to a running app and readers are never blocked by the build.
    """
    path = os.path.abspath(CACHE_DB_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = '%s.%d.tmp' % (path, os.getpid())
    if os.path.exists(temp_path):
        os.remove(temp_path)

    conn = sqlite3.connect(temp_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO dashboard (school_id,gender,season,payload) VALUES (?,?,?,?)",
            rows)
        conn.executemany(
            "INSERT OR REPLACE INTO rankings (gender,season,event,payload) VALUES (?,?,?,?)",
            ranking_rows)
        conn.executemany(
            "INSERT OR REPLACE INTO meta (key,value) VALUES (?,?)",
            [
                ('generated_at', datetime.now(timezone.utc).isoformat(timespec='seconds')),
                ('data_version', str(DATA_VERSION)),
                ('methodology_version', str(METHODOLOGY_VERSION)),
                # Size rather than mtime: a deploy clones the repository fresh and
                # git stamps every file with the time of the clone, so an mtime
                # recorded here could never match what the server sees.
                ('source_size', str(source_size)),
                # The content fingerprint. Size alone misses an edit that
                # rewrites a mark without changing how large the file is.
                ('source_hash', source_hash()),
                ('rows', str(len(rows))),
                ('ranking_rows', str(len(ranking_rows))),
            ])
        conn.commit()
    finally:
        conn.close()
    os.replace(temp_path, path)
    return path


def source_size():
    try:
        return os.stat(CONST.DB_PATH).st_size
    except OSError:
        return 0


def _stat_key():
    """Cheap identity of the source file: size and modification time."""
    try:
        stat = os.stat(CONST.DB_PATH)
        return '%d:%d' % (stat.st_size, stat.st_mtime_ns)
    except OSError:
        return ''


@lru_cache(maxsize=4)
def _hash_for(stat_key):
    """SHA-256 of Track.db, computed once per distinct (size, mtime).

    Size alone is not enough to notice a change. Correcting a mark rewrites a
    page in place and the file often ends up exactly as large as it was -- which
    is precisely the edit most likely to be made quietly and forgotten. Hashing
    catches it; keying the cache on (size, mtime) means a running worker hashes
    once and then answers for free.

    mtime is fine *here* because it is only ever compared against itself within
    one process. The value stored in the cache and compared across machines is
    the hash, which travels with the bytes.
    """
    if not stat_key:
        return ''
    digest = hashlib.sha256()
    try:
        with open(CONST.DB_PATH, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                digest.update(chunk)
    except OSError:
        return ''
    return digest.hexdigest()


def source_hash():
    """Content fingerprint of the results database."""
    return _hash_for(_stat_key())


def cache_status():
    """Whether the cache still matches the database it was built from.

    Returns {'built': bool, 'stale': bool, 'generated_at': str, 'reason': str}.
    Costs one os.stat per request, plus one hash per worker per change.
    """
    meta = cache_meta()
    if not meta:
        return {'built': False, 'stale': True, 'generated_at': None,
                'reason': 'The dashboard cache has not been built.'}
    stored = meta.get('source_hash')
    if not stored:
        # Written by an older build that recorded only the size.
        stale = str(meta.get('source_size')) != str(source_size())
        reason = 'Results have changed since this cache was built.' if stale else ''
        return {'built': True, 'stale': stale,
                'generated_at': meta.get('generated_at'), 'reason': reason}
    current = source_hash()
    stale = bool(current) and current != stored
    return {
        'built': True,
        'stale': stale,
        'generated_at': meta.get('generated_at'),
        'reason': 'Results have changed since this cache was built.' if stale else '',
    }
