"""Writing the precomputed JSON the site serves, and recording what built it.

One function, used by every job that produces a file under static/data/, so the
things that matter about these files are decided once.

COMPACT, NOT INDENTED
---------------------
The routes send these files to the browser *verbatim* -- the file is the
response -- so the bytes on disk are the bytes on the wire. Indented, the
largest was 1093KB; compact it is 635KB. That is 42% off every one of those
responses, off the repository, and off the deploy.

The cost is that the files stop being line-diffable. They are machine artifacts,
rebuilt whole on every run, and a 600KB JSON diff was never going to be read by
a human anyway. `python -m json.tool <file>` prints one readably when needed.

VALIDATED WHILE IT IS CHEAP
---------------------------
`allow_nan=False` makes the dump fail rather than emit `NaN` or `Infinity`,
which json.dumps will happily write and no JSON parser will accept. Payloads
here come from pandas and SQL aggregates, which produce NaN whenever a mean is
taken over nothing at all -- so this is a real failure mode, not a theoretical
one. Catching it here stops a build; catching it in the browser means a page
that silently shows nothing.

WRITTEN ATOMICALLY
------------------
Serialize fully, write a temporary file beside the target, then os.replace it
into place -- which is atomic, so a reader either sees the whole old file or the
whole new one. A job interrupted halfway can no longer leave a truncated file
behind, which matters now that the routes forward the bytes without parsing them
and would otherwise forward the truncation.

STAMPED WITH THEIR SOURCE
-------------------------
Every write also records, in manifest.json beside the artifacts, the SHA-256 of
the Track.db the payload was derived from. That is what lets
`build_all --check` answer the question the check exists for: *were these built
from the results currently in the repository?*

It could not answer that before. Only dashboard_cache.db recorded its source, so
running `precompute_dashboard_v4` alone -- rebuilding the cache but not the JSON
-- left ten stale files on disk and `--check` still reported "current". A false
all-clear is worse than no check.

A stamp per artifact rather than one for the whole directory, and updated in
place rather than rewritten, because jobs are run individually: rebuilding one
artifact must not claim the others are fresh too.

SCOPED TO THE SEASON, NOT THE WHOLE DATABASE
--------------------------------------------
The stamp is a hash of the rows the artifact was actually built from -- one
season and gender -- not of Track.db as a whole.

A whole-file hash answers "did Track.db change?", which is the wrong question.
During a postseason every new result changes it, so every artifact of every past
season reads as stale at once. Told that its 2026 files are out of date each time
a 2027 sectional lands, the only thing anyone learns is to ignore the check.

Scoped, the answer is the one worth having: loading 2027 results flags the 2027
artifacts and leaves 2026 alone; correcting a 2026 mark flags 2026, which is
exactly when those files do need rebuilding.

The scope covers everything an artifact reads: that season's meets, results and
relays, the athletes and schools appearing in them, and that year's enrollments.
Adding a 2027 athlete at a school that never competed in 2026 does not disturb
2026; renaming a school that did, does.

dashboard_cache.db is deliberately NOT scoped this way -- see
services/dashboard_v4.py. A school dashboard shows every season at once and its
statewide ranking moves when any of them move, so a new 2027 result really does
make the 2026 view of it stale. Its whole-file hash is correct.

The stamp lives in a sidecar, not in the payloads, because the payloads have
different shapes -- some are objects, some are bare lists -- and because the
routes forward them to the browser untouched. Nothing the browser receives
changes because of this.
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

from common.const import CONST

# Beside the artifacts it describes.
DATA_DIR = os.path.join(CONST.WEB_DIR, 'app', 'static', 'data')
MANIFEST_PATH = os.path.join(DATA_DIR, 'manifest.json')

# Artifacts that are not derived from Track.db, so a Track.db hash would say
# nothing about them. tournament_hosts.json comes from ihsaa.org and changes
# once a year; app/jobs/precompute_tournament_hosts.py writes it through
# common/tournament_hosts.py, which has no business knowing about Track.db.
UNSTAMPED = frozenset({'tournament_hosts/tournament_hosts.json'})


def _relative(path):
    """The artifact's key in the manifest: its path under static/data/.

    None when the file is not under static/data/ at all. The manifest describes
    that directory and nothing else, so a path outside it has no key -- without
    this, os.path.relpath cheerfully returns '../../../..' strings and they end
    up recorded as artifacts that then read as permanently missing.
    """
    absolute = os.path.abspath(path)
    rel = os.path.relpath(absolute, DATA_DIR)
    if rel.startswith(os.pardir) or os.path.isabs(rel):
        return None
    return rel.replace(os.sep, '/')


def source_fingerprint():
    """SHA-256 of the whole results database.

    For artifacts with no season scope. Delegates to the dashboard cache's
    implementation rather than repeating it, so the two can never disagree about
    what "the same Track.db" means; it is cached there on (size, mtime).
    """
    from app.services.dashboard_v4 import source_hash
    return source_hash()


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


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp_path = '%s.tmp' % path
    # newline='' so the bytes are exactly what was serialized; without it Python
    # rewrites every \n as \r\n on Windows, which is how these files came to be
    # 3% larger on one developer's machine than another's.
    with open(tmp_path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def read_manifest():
    """What each artifact was built from, or {} if nothing has been stamped."""
    try:
        with open(MANIFEST_PATH, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    artifacts = data.get('artifacts')
    return artifacts if isinstance(artifacts, dict) else {}


def _record(key, size, year, gender):
    """Add this artifact's entry to the manifest, leaving the others alone."""
    artifacts = read_manifest()
    entry = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'bytes': size,
    }
    if year is None:
        entry['scope'] = 'all'
        entry['source_hash'] = source_fingerprint()
    else:
        entry['scope'] = {'year': int(year), 'gender': str(gender)}
        entry['source_hash'] = season_fingerprint(year, gender)
    artifacts[key] = entry
    _write_atomic(MANIFEST_PATH, json.dumps(
        {'artifacts': dict(sorted(artifacts.items()))},
        indent=2, sort_keys=True) + '\n')


def write_json_artifact(path, payload, year=None, gender=None, stamp=True):
    """Write `payload` to `path` as compact JSON. Returns the path.

    Raises ValueError if the payload contains NaN or Infinity, before anything
    is written -- a failed build is the point.

    Pass the `year` and `gender` the payload covers. The artifact is then stamped
    with a hash of just that season's rows, so next season's results do not make
    it read as stale. Omit them only for an artifact genuinely derived from the
    whole database.

    Pass stamp=False for an artifact not derived from Track.db. Anything written
    outside static/data/ is never stamped -- the manifest describes that
    directory, and a test writing to a tmp_path is not a site artifact.
    """
    # Fully serialized before the target is touched, so a serialization error
    # leaves the previous build in place.
    text = json.dumps(payload, separators=(',', ':'), allow_nan=False, default=str)
    _write_atomic(path, text)

    key = _relative(path)
    if stamp and key is not None and key not in UNSTAMPED:
        _record(key, len(text.encode('utf-8')), year, gender)
    return path


def check_artifacts():
    """Are the JSON artifacts built from the results that are here now?

    Each artifact is compared against its own scope -- the season and gender it
    covers -- so loading a new season flags that season's files and leaves every
    earlier one alone.

    Returns (stale, messages).
    """
    manifest = read_manifest()

    on_disk = set()
    for root, _dirs, files in os.walk(DATA_DIR):
        for name in files:
            if name.endswith('.json') and name != 'manifest.json':
                key = _relative(os.path.join(root, name))
                if key is not None:
                    on_disk.add(key)

    if not manifest:
        return True, ['no manifest.json -- the JSON artifacts have never been stamped']

    problems = []

    for key in sorted(on_disk - set(manifest) - UNSTAMPED):
        problems.append('%s is not in the manifest (built by an older job?)' % key)

    for key, entry in sorted(manifest.items()):
        if key not in on_disk:
            problems.append('%s is in the manifest but missing from disk' % key)
            continue

        stamped = entry.get('source_hash')
        if not stamped:
            problems.append('%s has no source_hash' % key)
            continue

        scope = entry.get('scope')
        if isinstance(scope, dict):
            current = season_fingerprint(scope.get('year'), scope.get('gender'))
            label = '%s %s results changed' % (scope.get('year'), scope.get('gender'))
        else:
            current = source_fingerprint()
            label = 'the results changed'

        if current and stamped != current:
            problems.append('%s -- %s since it was built (%s)'
                            % (key, label, entry.get('generated_at', 'unknown date')))

    return bool(problems), problems
