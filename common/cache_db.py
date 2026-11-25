"""dashboard_cache.db: everything the site precomputes, in one file.

    Track.db --(build_all, on a developer's machine)--> dashboard_cache.db --> the site

Why: PythonAnywhere runs the analysis 15-25x slower than a development machine,
so pages and reports are built offline and the site only reads them. The cache
is derived from Track.db, so it lives in its own file: rebuilding it never risks
the source data, and deleting it is always safe (build_all makes it again). It
is not in git; it ships as a GitHub release asset (docs/publish.sh), which the
deploy downloads (docs/deploy.sh).

Tables
------
meta          key/value: when the cache was built and from which Track.db
              (source_hash, source_size, generated_at), school_pages_format
rankings      statewide ranked lists per gender/season/event ('' = programs),
              shown in the school page's rank popups
school_pages  one stored school page per school/gender/season ('all-time' too)
artifacts     the report data (predictions, qualifier lists, tournament hosts),
              one JSON document per name, each stamped with what it was built from

Payloads are JSON, zlib-compressed (encode/decode). This module lives in
common/ because both the site and common/tournament_hosts.py read it.
"""
import hashlib
import json
import os
import sqlite3
import zlib
from datetime import datetime, timezone
from functools import lru_cache

from common.const import CONST

CACHE_DB_PATH = os.path.join(CONST.WEB_DIR, 'data', 'dashboard_cache.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS rankings (
    gender  TEXT NOT NULL,
    season  TEXT NOT NULL,
    event   TEXT NOT NULL,   -- '' for the statewide program leaderboard
    payload BLOB NOT NULL,
    PRIMARY KEY (gender, season, event)
);
CREATE TABLE IF NOT EXISTS school_pages (
    school_id INTEGER NOT NULL,
    gender    TEXT    NOT NULL,
    season    TEXT    NOT NULL,   -- a year, or 'all-time'
    payload   BLOB    NOT NULL,
    PRIMARY KEY (school_id, gender, season)
);
CREATE TABLE IF NOT EXISTS artifacts (
    name         TEXT PRIMARY KEY,   -- e.g. 'state_qualifiers_2026_boys'
    payload      BLOB NOT NULL,      -- compact JSON, compressed
    year         INTEGER,            -- the season it covers (NULL: not season-scoped)
    gender       TEXT,
    source_hash  TEXT,               -- what it was built from (NULL: not from Track.db)
    generated_at TEXT NOT NULL
);
"""


# ------------------------------------------------------------------ the file

def connect(readonly=True):
    """A connection to the cache. Read-only handles never create an empty file,
    which would turn "cache missing" into "cache silently empty"."""
    path = os.path.abspath(CACHE_DB_PATH)
    if readonly:
        return sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def _read_one(sql, params):
    """One row from the cache, or None when the cache or table is missing."""
    try:
        conn = connect(readonly=True)
    except sqlite3.OperationalError:
        return None
    try:
        return conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def encode(payload):
    """Compact JSON, deflated (payloads are repetitive and shrink ~80%)."""
    return zlib.compress(json.dumps(payload, separators=(',', ':'), default=str).encode('utf-8'), 6)


def decode(blob):
    """The payload, or None if it cannot be read."""
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


def read_meta():
    try:
        conn = connect(readonly=True)
    except sqlite3.OperationalError:
        return {}
    try:
        return dict(conn.execute('SELECT key, value FROM meta').fetchall())
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


# ------------------------------------------------------------------ rankings

def load_rankings(gender, season, event=''):
    """One ranked list: the statewide program table ('') or one event's field."""
    row = _read_one('SELECT payload FROM rankings WHERE gender=? AND season=? AND event=?',
                    (str(gender), str(season), str(event or '')))
    return decode(row[0]) if row else None


# ------------------------------------------------------------------ artifacts

def artifact_json(name):
    """An artifact's JSON text exactly as stored (routes send it as is), or None."""
    row = _read_one('SELECT payload FROM artifacts WHERE name=?', (name,))
    if not row:
        return None
    try:
        return zlib.decompress(row[0])
    except zlib.error:
        return None


def load_artifact(name, default=None):
    """An artifact's payload, or `default` when it has not been built."""
    text = artifact_json(name)
    if text is None:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


def write_artifact(name, payload, year=None, gender=None, source_hash=None):
    """Store one artifact, replacing any earlier version in one transaction.

    Raises ValueError for NaN or Infinity before anything is written: json.dumps
    would emit them and no JSON parser accepts them.
    """
    text = json.dumps(payload, separators=(',', ':'), allow_nan=False, default=str)
    with connect(readonly=False) as conn:
        conn.execute(
            'INSERT OR REPLACE INTO artifacts (name, payload, year, gender, source_hash, generated_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (name, zlib.compress(text.encode('utf-8'), 6), None if year is None else int(year),
             None if gender is None else str(gender), source_hash,
             datetime.now(timezone.utc).isoformat(timespec='seconds')))
    return len(text)


def delete_artifacts(names):
    """Remove the named artifacts (missing names are ignored)."""
    conn = connect(readonly=False)
    try:
        with conn:
            conn.executemany('DELETE FROM artifacts WHERE name=?', [(name,) for name in names])
    finally:
        conn.close()


def artifact_stamps():
    """{name: (year, gender, source_hash, generated_at)} for every artifact."""
    try:
        conn = connect(readonly=True)
    except sqlite3.OperationalError:
        return {}
    try:
        return {row[0]: row[1:] for row in conn.execute(
            'SELECT name, year, gender, source_hash, generated_at FROM artifacts')}
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


# ------------------------------------------------------------------ freshness

def source_size():
    try:
        return os.stat(CONST.DB_PATH).st_size
    except OSError:
        return 0


def _stat_key():
    try:
        stat = os.stat(CONST.DB_PATH)
        return '%d:%d' % (stat.st_size, stat.st_mtime_ns)
    except OSError:
        return ''


@lru_cache(maxsize=4)
def _hash_for(stat_key):
    """SHA-256 of Track.db, once per distinct (size, mtime). Size alone misses a
    corrected mark that leaves the file the same size."""
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


def stamp(conn):
    """Record that the cache was built from the current Track.db."""
    conn.executemany('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', [
        ('generated_at', datetime.now(timezone.utc).isoformat(timespec='seconds')),
        ('source_hash', source_hash()),
        ('source_size', str(source_size())),
    ])


def cache_status():
    """Whether the rankings and school pages match the current Track.db.

    {'built': bool, 'stale': bool, 'generated_at': str|None}. The artifacts are
    checked separately, per season (app/jobs/artifacts.py).
    """
    meta = read_meta()
    if not meta.get('source_hash'):
        return {'built': False, 'stale': True, 'generated_at': None}
    current = source_hash()
    return {'built': True, 'stale': bool(current) and current != meta['source_hash'],
            'generated_at': meta.get('generated_at')}
