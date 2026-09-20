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

The stamp lives in a sidecar, not in the payloads, because the payloads have
different shapes -- some are objects, some are bare lists -- and because the
routes forward them to the browser untouched. Nothing the browser receives
changes because of this.
"""
import json
import os
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
    """SHA-256 of the results database these artifacts are built from.

    Delegates to the dashboard cache's implementation rather than repeating it,
    so the JSON and the cache can never disagree about what "the same Track.db"
    means. It is cached there on (size, mtime), so building ten artifacts hashes
    Track.db once.
    """
    from app.services.dashboard_v4 import source_hash
    return source_hash()


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


def _record(key, size):
    """Add this artifact's entry to the manifest, leaving the others alone."""
    artifacts = read_manifest()
    artifacts[key] = {
        'source_hash': source_fingerprint(),
        'source_size': os.path.getsize(CONST.DB_PATH) if os.path.exists(CONST.DB_PATH) else 0,
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'bytes': size,
    }
    _write_atomic(MANIFEST_PATH, json.dumps(
        {'artifacts': dict(sorted(artifacts.items()))},
        indent=2, sort_keys=True) + '\n')


def write_json_artifact(path, payload, stamp=True):
    """Write `payload` to `path` as compact JSON. Returns the path.

    Raises ValueError if the payload contains NaN or Infinity, before anything
    is written -- a failed build is the point.

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
        _record(key, len(text.encode('utf-8')))
    return path


def check_artifacts():
    """Are the JSON artifacts built from the Track.db that is here now?

    Returns (stale, messages). `stale` is True if any artifact is missing,
    unstamped, or stamped with a different Track.db.
    """
    current = source_fingerprint()
    manifest = read_manifest()

    on_disk = set()
    for root, _dirs, files in os.walk(DATA_DIR):
        for name in files:
            if name.endswith('.json') and name != 'manifest.json':
                on_disk.add(_relative(os.path.join(root, name)))

    problems = []

    if not manifest:
        return True, ['no manifest.json -- the JSON artifacts have never been stamped']

    for key in sorted(on_disk - set(manifest) - UNSTAMPED):
        problems.append('%s is not in the manifest (built by an older job?)' % key)

    for key, entry in sorted(manifest.items()):
        if key not in on_disk:
            problems.append('%s is in the manifest but missing from disk' % key)
            continue
        stamped = entry.get('source_hash')
        if not stamped:
            problems.append('%s has no source_hash' % key)
        elif current and stamped != current:
            problems.append('%s was built from a different Track.db (%s, %s)'
                            % (key, entry.get('generated_at', 'unknown date'),
                               stamped[:12]))

    return bool(problems), problems
