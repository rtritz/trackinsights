"""Cache invalidation, keyed on the database itself.

Every expensive query in this package is wrapped in an lru_cache keyed on its
arguments. Nothing in that key describes the *data*, so when Track.db is
replaced -- which is how results are published -- a running worker would go on
serving figures it computed at start-up. These functions notice the swap and
empty the caches, which is why updating results no longer means remembering to
reload the web app.

The check is one small read per request; the clearing happens only when the
fingerprint actually moves.
"""
import hashlib
import logging
import os

from common.const import CONST

logger = logging.getLogger(__name__)

# SQLite's file header. Its change counter, freelist count and schema cookie all
# live in here, which is what makes a 100-byte read a usable stamp of the whole
# file. https://www.sqlite.org/fileformat2.html#the_database_header
_SQLITE_HEADER_BYTES = 100

# Module-level, so the fingerprint survives between requests in one worker.
_LAST_SEEN_DB = {'fingerprint': None}


def _active_db_path():
    """The database this app is actually reading.

    Not necessarily CONST.DB_PATH: Flask takes its URI from config.py, and the
    test suite points it at a fixture. Fingerprinting CONST.DB_PATH while the app
    served a different database meant the precomputed payloads looked valid for
    data they were never built from -- which is how a test fixture got answered
    with production rows.
    """
    try:
        from flask import current_app
        uri = current_app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    except Exception:
        uri = ''
    if uri.startswith('sqlite:///'):
        return uri[len('sqlite:///'):]
    return CONST.DB_PATH


def _db_fingerprint():
    """A cheap stamp of the database's current state.

    Derived from the file's *contents*, never its modification time.

    mtime is not portable between machines, and this fingerprint has to be: the
    precomputed payloads are built here and read on the server. A deploy clones
    the repository fresh, and git stamps every checked-out file with the time of
    the clone, so an mtime recorded at build time can never match the one the
    server sees. That silently invalidated every precomputed payload on every
    request, which is the opposite of what these files are for.

    So: the file size plus SQLite's own 100-byte header, which carries the
    change counter (bumped by every write transaction), the freelist page count
    and the schema cookie. Those bytes travel with the file, so they mean the
    same thing on both machines, and they move even when a rewrite happens to
    land on an identical size -- which size alone missed. SQLite reuses freed
    pages, so a delete-and-reinsert cycle really can leave the file exactly as
    large as it was; that was a stale cache served as though it were current.

    One open and a 100-byte read, once per request.
    """
    path = _active_db_path()
    try:
        size = os.stat(path).st_size
    except OSError:
        return ''
    try:
        with open(path, 'rb') as handle:
            header = handle.read(_SQLITE_HEADER_BYTES)
    except OSError:
        # Readable by stat but not by open: fall back to the size alone rather
        # than reporting no database at all.
        return str(size)
    return '%d:%s' % (size, hashlib.sha256(header).hexdigest()[:16])


def _clear_query_caches(*, keep=()):
    """Empty every lru_cache in the queries package.

    Used when the database has changed underneath a running process: the caches
    are keyed on query arguments, not on the state of the data, so nothing else
    would ever evict them.

    Walks every module in the package rather than this module's globals. When
    queries was one file those were the same thing; now they are not, and
    checking only here would silently leave most caches full.
    """
    import importlib
    import pkgutil

    package = importlib.import_module(__package__)
    modules = [package] + [
        importlib.import_module('%s.%s' % (__package__, info.name))
        for info in pkgutil.iter_modules(package.__path__)
    ]
    for module in modules:
        for name, value in list(vars(module).items()):
            if name in keep:
                continue
            clear = getattr(value, 'cache_clear', None)
            if callable(clear):
                clear()


def ensure_fresh_queries():
    """Drop every cached query result if the database has changed.

    The caches in this module are keyed on query arguments, so nothing evicts
    them when the underlying data moves -- a long-running worker would keep
    serving the rankings it computed at start-up until it was restarted. That is
    why updating results meant remembering to reload the web app.

    Called once per request. The check is one open and a 100-byte read, and on
    the ordinary request -- where nothing has changed -- it does nothing else.
    """
    current = _db_fingerprint()
    previous = _LAST_SEEN_DB['fingerprint']
    _LAST_SEEN_DB['fingerprint'] = current
    if previous is not None and previous != current:
        logger.info('database changed (%s -> %s); clearing query caches',
                    previous, current)
        _clear_query_caches()
        return True
    return False
