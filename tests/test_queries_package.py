"""The queries package's cross-module behaviour.

queries used to be one file. Splitting it into a package broke an assumption
that had been invisible while it held: `_clear_query_caches()` walked its own
module's globals, which used to mean "everything" and now means "one module of
eight". Left unnoticed, a database change would have cleared 5 of 25 caches and
the site would have gone on serving stale numbers with no error anywhere.

These tests exist so that cannot come back. They deliberately assert the
*property* -- every cache in the package is cleared -- rather than naming
functions, so they keep working as modules and caches are added.
"""
import importlib
import pkgutil

from app import queries
from app.queries import shared


def _cached_functions():
    """Every lru_cache-wrapped function in the package, with its module name."""
    package = importlib.import_module('app.queries')
    found = []
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module('app.queries.%s' % info.name)
        for name, value in vars(module).items():
            # Defined here rather than imported from a sibling, so each cache is
            # counted once.
            if hasattr(value, 'cache_clear') and getattr(value, '__module__', '') == module.__name__:
                found.append((info.name, name, value))
    return found


def test_caches_live_in_more_than_one_module():
    """The premise of the test below.

    If the package were ever consolidated back into one module, the clearing
    test would still pass while proving nothing -- this fails first and says so.
    """
    modules = {mod for mod, _, _ in _cached_functions()}
    assert len(modules) > 1, (
        'Expected cached functions across several modules; found only %s. '
        'If the package was deliberately merged, this test can go -- but check '
        'that _clear_query_caches still covers everything first.' % modules
    )


def test_clearing_reaches_every_module(app):
    """A database change must empty every cache, not just this module's.

    Warmed through a real code path rather than by poking functions directly, so
    the test exercises what a request would actually populate.
    """
    with app.app_context():
        shared._clear_query_caches()

        # Warm whatever a dashboard build touches -- that spans several modules.
        queries.get_school_dashboard_v4_core(1, gender='Boys', season='2024')
        queries.get_school_dashboard_v4_athlete_scorecard(1, 'Boys', '2024')

        warm = [(mod, name) for mod, name, fn in _cached_functions()
                if fn.cache_info().currsize > 0]
        assert warm, 'nothing was cached; the warm-up path may have changed'
        assert len({mod for mod, _ in warm}) > 1, (
            'Only %s was warmed, so this cannot detect the cross-module bug. '
            'Warm a broader path.' % {mod for mod, _ in warm}
        )

        shared._clear_query_caches()

        still_full = [(mod, name) for mod, name, fn in _cached_functions()
                      if fn.cache_info().currsize > 0]
        assert not still_full, (
            'These caches survived _clear_query_caches(): %s. After a results '
            'change the site would serve stale numbers from them.' % still_full
        )


def test_keep_argument_spares_named_caches(app):
    """`keep` is how a caller protects a cache it is mid-way through using."""
    with app.app_context():
        queries.get_school_dashboard_v4_core(1, gender='Boys', season='2024')
        assert queries.get_school_dashboard_v4_core.cache_info().currsize > 0

        shared._clear_query_caches(keep=('get_school_dashboard_v4_core',))
        assert queries.get_school_dashboard_v4_core.cache_info().currsize > 0

        shared._clear_query_caches()
        assert queries.get_school_dashboard_v4_core.cache_info().currsize == 0


def test_every_public_name_is_reachable_from_the_package():
    """`from app.queries import X` must keep working for what routes use.

    The package re-exports each module's names; forgetting one is the easiest
    mistake to make when adding a function, and it fails at import time in
    production rather than here.
    """
    used_by_the_app = [
        'get_school_dashboard_v4_core',
        'get_school_dashboard_v4_athlete_scorecard',
        'get_school_dashboard_v4_program_rank',
        'get_school_dashboard_v4_returning',
        'get_school_dashboard_v4_season_h2h',
        'get_school_dashboard_data',
        'get_athlete_dashboard_data',
        'search_bar',
        'ensure_fresh_queries',
        '_build_statewide_program_rankings',
        '_covered_rank_seasons',
    ]
    missing = [n for n in used_by_the_app if not hasattr(queries, n)]
    assert not missing, 'not re-exported from app.queries: %s' % missing
