"""Download the published dashboard_cache.db into web/data/.

For teammates (and fresh clones): the cache is not in git, it is published as a
GitHub release asset by whoever rebuilds the data (docs/publish.sh). This fetches
that same file, so rank popups, report pages and stored school pages all work
locally without running build_all. From web/:

    python -m app.jobs.get_cache

Safe to re-run: the download goes to a temporary file, is checked, and only then
replaces your cache, so a failed download leaves the old one in place. It then
says whether the cache matches your Track.db -- if you pulled newer results than
were published, or edited Track.db yourself, run build_all instead.
"""
import os
import sqlite3
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

from common import cache_db  # noqa: E402

# The same asset docs/deploy.sh downloads.
CACHE_URL = 'https://github.com/rtritz/trackinsights/releases/download/cache-latest/dashboard_cache.db'
REQUIRED_TABLES = {'meta', 'rankings', 'school_pages', 'artifacts'}


def _download(url, path):
    request = Request(url, headers={'User-Agent': 'trackinsights-get-cache'})
    with urlopen(request, timeout=120) as response, open(path, 'wb') as out:
        size = 0
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            size += len(chunk)
    return size


def _check(path):
    """Raise ValueError unless `path` is a cache this code can read."""
    with open(path, 'rb') as handle:
        if not handle.read(16).startswith(b'SQLite format 3'):
            raise ValueError('the download is not a SQLite database')
    conn = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    missing = REQUIRED_TABLES - tables
    if missing:
        raise ValueError('the published cache is missing %s -- it was built by older code; '
                         'run build_all instead' % ', '.join(sorted(missing)))


def main(url=CACHE_URL):
    target = os.path.abspath(cache_db.CACHE_DB_PATH)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    handle, temp = tempfile.mkstemp(suffix='.db.tmp', dir=os.path.dirname(target))
    os.close(handle)
    try:
        print('Downloading the published cache...')
        size = _download(url, temp)
        _check(temp)
        os.replace(temp, target)
    except (URLError, OSError, ValueError, sqlite3.Error) as exc:
        print('Cache not updated: %s' % exc)
        return 1
    finally:
        if os.path.exists(temp):
            os.remove(temp)
    print('Saved %s (%.0f MB).' % (target, size / 1e6))

    status = cache_db.cache_status()
    if status['built'] and not status['stale']:
        print('It matches your Track.db (built %s).' % status['generated_at'])
    else:
        print('Note: it was built from a different Track.db than yours (newer pulled results, or'
              ' local edits).\n  Pages still work; for numbers that match your data, run:'
              ' python -m app.jobs.build_all')
    return 0


if __name__ == '__main__':
    sys.exit(main())
