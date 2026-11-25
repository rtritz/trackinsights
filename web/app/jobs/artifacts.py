"""Storing the report data the site serves, and recording what built it.

Every job that produces report data (predictions, qualifier lists) stores it
here, as one named JSON document in dashboard_cache.db's `artifacts` table
(common/cache_db.py). The routes read it back by name; the API routes send the
stored JSON to the browser as is.

VALIDATED WHILE IT IS CHEAP
---------------------------
NaN or Infinity in a payload fails the build (cache_db.write_artifact uses
allow_nan=False). Payloads come from pandas and SQL aggregates, which produce
NaN whenever a mean is taken over nothing; catching it here stops a build,
catching it in the browser means a page that silently shows nothing.

STAMPED WITH THEIR SOURCE, SCOPED TO THE SEASON
-----------------------------------------------
Each artifact records a hash of the rows it was built from -- its season and
gender, not the whole of Track.db -- which is what `build_all --check` compares.
Scoped, loading 2027 results flags the 2027 artifacts and leaves 2026 alone;
correcting a 2026 mark flags 2026, exactly when those need rebuilding. A
whole-file hash would flag every past season on every new result, and a check
that always says "stale" teaches everyone to ignore it.

The scope covers everything an artifact reads: that season's meets, results and
relays, the athletes and schools appearing in them, and that year's enrollments.

The rankings and school pages are NOT scoped this way: a school page shows every
season at once, so the cache's whole-file stamp (cache_db.cache_status) is right
for them.
"""
import hashlib
import os
import sqlite3

from common import cache_db
from common.const import CONST

# Not derived from Track.db, so a Track.db hash says nothing about them: the
# tournament hosts come from ihsaa.org (app/jobs/precompute_tournament_hosts.py).
UNSTAMPED = frozenset({'tournament_hosts'})


# The rows each (year, gender) artifact is built from. Ordered explicitly --
# SQLite makes no promise about row order without it, and an unstable order
# would make the hash differ between runs over identical data.
_SCOPE_QUERIES = (
    ("""select meet_id, host, meet_type, meet_num, gender, year
          from meet where year=:year and gender=:gender
         order by meet_id""",),
    ("""select ar.athlete_id, ar.meet_id, ar.event, ar.result_type,
                ar.result, ar.result2, ar.place, ar.grade
          from athlete_result ar join meet m on m.meet_id = ar.meet_id
         where m.year=:year and m.gender=:gender
         order by ar.athlete_id, ar.meet_id, ar.event, ar.result_type""",),
    ("""select rr.school_id, rr.meet_id, rr.event, rr.result, rr.result2,
                rr.place, rr.athlete_names
          from relay_result rr join meet m on m.meet_id = rr.meet_id
         where m.year=:year and m.gender=:gender
         order by rr.school_id, rr.meet_id, rr.event""",),
    # Only the athletes who appear that season, so next season's intake does not
    # disturb this season's stamp.
    ("""select distinct a.athlete_id, a.first, a.last, a.school_id, a.gender,
                a.grad_year
          from athlete a
          join athlete_result ar on ar.athlete_id = a.athlete_id
          join meet m on m.meet_id = ar.meet_id
         where m.year=:year and m.gender=:gender
         order by a.athlete_id""",),
    # Likewise the schools: those fielding an athlete or a relay that season.
    ("""select distinct s.school_id, s.school_name, s.team_name, s.city, s.zip
          from school s
         where s.school_id in (
               select a.school_id from athlete a
                 join athlete_result ar on ar.athlete_id = a.athlete_id
                 join meet m on m.meet_id = ar.meet_id
                where m.year=:year and m.gender=:gender
               union
               select rr.school_id from relay_result rr
                 join meet m on m.meet_id = rr.meet_id
                where m.year=:year and m.gender=:gender)
         order by s.school_id""",),
    ("""select school_id, year, enrollment
          from school_enrollment where year=:year
         order by school_id""",),
)

_SCOPE_CACHE = {}


def season_fingerprint(year, gender, db_path=None):
    """SHA-256 of just the rows a (year, gender) artifact is built from.

    About 45ms per season, and memoized per process, so stamping or checking all
    ten artifacts costs a handful of queries rather than ten full table scans.
    """
    path = db_path or CONST.DB_PATH
    key = (path, int(year), str(gender))
    if key in _SCOPE_CACHE:
        return _SCOPE_CACHE[key]

    digest = hashlib.sha256()
    params = {'year': int(year), 'gender': str(gender)}
    try:
        uri = 'file:%s?mode=ro' % path.replace(os.sep, '/')
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        return ''
    try:
        for (sql,) in _SCOPE_QUERIES:
            # A separator between sections, so rows from one query cannot
            # run into the next and hash the same as a different arrangement.
            digest.update(b'|section|')
            for row in conn.execute(sql, params):
                digest.update(repr(row).encode('utf-8'))
    except sqlite3.Error:
        return ''
    finally:
        conn.close()

    _SCOPE_CACHE[key] = digest.hexdigest()
    return _SCOPE_CACHE[key]


def write_artifact(name, payload, year=None, gender=None, stamp=True):
    """Store `payload` under `name`, stamped with what it was built from.

    Pass the `year` and `gender` the payload covers, so it is stamped with just
    that season's rows. Omit them only for an artifact derived from the whole
    database. stamp=False for an artifact not derived from Track.db.
    Returns the stored size in bytes.
    """
    if not stamp or name in UNSTAMPED:
        source = None
    elif year is None:
        source = cache_db.source_hash()
    else:
        source = season_fingerprint(year, gender)
    return cache_db.write_artifact(name, payload, year=year, gender=gender, source_hash=source)


def check_artifacts():
    """Are the stored artifacts built from the results that are here now?

    Each is compared against its own scope -- the season and gender it covers.
    Returns (stale, messages).
    """
    stamps = cache_db.artifact_stamps()
    if not stamps:
        return True, ['no report data in dashboard_cache.db -- run build_all']
    problems = []
    for name, (year, gender, stamped, generated_at) in sorted(stamps.items()):
        if name in UNSTAMPED:
            continue
        if not stamped:
            problems.append('%s has no source stamp' % name)
            continue
        if year is not None:
            current = season_fingerprint(year, gender)
            label = '%s %s results changed' % (year, gender)
        else:
            current = cache_db.source_hash()
            label = 'the results changed'
        if current and stamped != current:
            problems.append('%s -- %s since it was built (%s)' % (name, label, generated_at or 'unknown date'))
    return bool(problems), problems
