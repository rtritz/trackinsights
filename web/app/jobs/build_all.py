"""
Rebuild everything the site precomputes into web/data/dashboard_cache.db.

One command, so "I updated the results" has exactly one follow-up step and there
is no list to remember. Each job is run in turn, timed, and reported; a job that
fails is reported and the rest still run, because a broken regional-predictions
build should not stop the dashboards from being rebuilt.

WHERE TO RUN THIS
-----------------
Locally, before committing -- NOT on PythonAnywhere.

The cache is derived from Track.db, which is committed: building it from the
same working copy that produced Track.db is what keeps the two in step.

Building on the server instead would multiply the work on every deploy --
PythonAnywhere measured 15-25x slower on the same code -- for an artifact
identical to the one you could have published.

    python -m app.jobs.build_all            # rebuild the current season
    python -m app.jobs.build_all --season 2026   # rebuild one season
    python -m app.jobs.build_all --all      # rebuild every season with results
    (--season and --all choose the school pages and rankings to rebuild; the
     qualifier pages' data is always for the current season only.)
    python -m app.jobs.build_all --check    # is anything stale? (exit 1 if so)
    python -m app.jobs.build_all --check --warn-only   # report, always exit 0
    python -m app.jobs.build_all --list     # what would run

Then publish: Track.db goes in git; the cache goes to a GitHub Release, because
it is large and rewritten on every build. Both steps are in
docs/PROJECT_GUIDE.md section 10, and this script prints them when it finishes.
"""
import importlib
import sys
import time
import traceback


# The current season is the newest year with results (queries.current_season).
# The school pages and rankings are built for the chosen seasons; everything
# else (the qualifier pages, hosts, predictions) for the current season only.
# Each entry is (name, module) or (name, module, entry function; default main).
JOBS = [
    # Hosts first, and cheap: the qualifier pages label meets with them, so stale
    # hosts show up on everything built afterwards.
    ('tournament_hosts', 'app.jobs.precompute_tournament_hosts'),
    # The statewide program and event rankings in dashboard_cache.db, which the
    # school page's rank popups read, plus the cache's freshness stamp.
    ('rankings', 'app.jobs.precompute_rankings', 'rebuild_all'),
    # Every school's page for the chosen seasons plus All-Time, read by the site
    # instead of computed per request. After rankings: the pages read them.
    ('school_pages', 'app.jobs.precompute_school_pages'),
    # The qualifier pages: one regional's list, all eight combined, the state list.
    ('regional_qualifiers', 'app.jobs.precompute_regional_qualifiers'),
    ('combined_rankings', 'app.jobs.precompute_combined_rankings'),
    ('combined_results', 'app.jobs.precompute_combined_results'),
    ('regional_predictions', 'app.jobs.precompute_regional_predictions'),
    ('state_predictions', 'app.jobs.precompute_state_predictions'),
    ('state_qualifiers', 'app.jobs.precompute_state_qualifiers'),
]


# Jobs worth warning about before they start, so a quiet one does not look hung.
SLOW = {'school_pages'}

# Built for whichever seasons were asked for; every other job gets the current one.
PER_SEASON = {'rankings', 'school_pages'}

# The qualifier pages show only the current season, so their data for older
# seasons is removed after a successful build. (The predictions reports are
# named by year -- /insights/reports/2026-... -- so theirs is kept.)
CURRENT_SEASON_ONLY = ('regional_qualifiers_', 'combined_rankings_', 'combined_results_', 'state_qualifiers_')


def run_one(name, module_path, entry_name='main', years=None):
    module = importlib.import_module(module_path)
    entry = getattr(module, entry_name, None)
    if entry is None:
        raise RuntimeError('%s has no %s()' % (module_path, entry_name))
    entry(years=years)


def covered_seasons():
    """Every season with results in Track.db, oldest first."""
    from app import create_app, queries
    with create_app().app_context():
        return sorted(queries._covered_rank_seasons())


def resolve_seasons(argv):
    """The seasons to build: --all, --season YYYY, or (default) the current one.

    Past seasons rarely change, so the default rebuilds only the newest season
    with results. After correcting an older season's results, use --season or --all.
    """
    available = covered_seasons()
    if not available:
        raise SystemExit('No seasons with results found in Track.db.')
    if '--all' in argv:
        return available
    if '--season' in argv:
        index = argv.index('--season')
        try:
            year = int(argv[index + 1])
        except (IndexError, ValueError):
            raise SystemExit('--season needs a year, e.g. --season 2026')
        if year not in available:
            raise SystemExit('No results for %d in Track.db (have: %s).' % (year, ', '.join(map(str, available))))
        return [year]
    return [available[-1]]


def _duration(seconds):
    """A readable length. "4m 52s" beats "292s" when you are watching it."""
    seconds = int(round(seconds))
    if seconds < 60:
        return '%ds' % seconds
    minutes, rest = divmod(seconds, 60)
    return '%dm %02ds' % (minutes, rest)


def current_season():
    from app import create_app, queries
    with create_app().app_context():
        return queries.current_season()


def prune_old_seasons(current):
    """Drop the qualifier pages' data for seasons other than the current one."""
    from common import cache_db
    old = [name for name, (year, *_rest) in cache_db.artifact_stamps().items()
           if name.startswith(CURRENT_SEASON_ONLY) and year is not None and year != current]
    if old:
        cache_db.delete_artifacts(old)
        print('Removed older seasons\' qualifier data: %s' % ', '.join(sorted(old)))
    return old


def build_all(years):
    total = len(JOBS)
    current = current_season()
    print('Rebuilding %d precomputed artifacts. School pages and rankings: %s. '
          'Everything else: %s (the current season).' % (total, ', '.join(map(str, years)), current))
    print('')

    started = time.perf_counter()
    failed = []
    timings = []

    for index, (name, module_path, *entry) in enumerate(JOBS, start=1):
        print('-' * 70)
        heading = '[%d/%d] %s' % (index, total, name)
        if name in SLOW:
            heading += '   (a few minutes; it prints progress every 50 schools)'
        print(heading)
        # Flushed because the jobs below print as they go and some take minutes;
        # a buffered heading would appear after the work it introduces.
        sys.stdout.flush()

        t0 = time.perf_counter()
        try:
            run_one(name, module_path, *(entry or ['main']),
                    years=years if name in PER_SEASON else [current])
            took = time.perf_counter() - t0
            timings.append((name, took, True))
            print('      ok in %s   (%s elapsed, %d of %d done)'
                  % (_duration(took), _duration(time.perf_counter() - started),
                     index, total))
        except Exception:  # noqa: BLE001
            # Reported and carried past: one broken job should not leave every
            # other artifact stale as well.
            took = time.perf_counter() - t0
            failed.append(name)
            timings.append((name, took, False))
            print('      FAILED after %s' % _duration(took))
            traceback.print_exc()
        sys.stdout.flush()

    print('-' * 70)
    print('')
    print('%-24s %10s' % ('job', 'time'))
    for name, took, ok in timings:
        print(('%-24s %10s %s' % (name, _duration(took),
               '' if ok else 'FAILED')).rstrip())
    print('%-24s %10s' % ('total', _duration(time.perf_counter() - started)))
    print('')
    if failed:
        print('FAILED: %s' % ', '.join(failed))
        print('Do not commit a partial rebuild -- fix these and run again.')
        return 1
    prune_old_seasons(current)
    print('All artifacts rebuilt. Two things to publish:')
    print('  git  -- web/data/Track.db')
    print('  release -- gh release upload cache-latest '
          'web/data/dashboard_cache.db --clobber   (or ./docs/publish.sh)')
    print('')
    print('dashboard_cache.db is NOT in git (it is large and rewritten every build).')
    print('The deploy downloads it from that release -- see docs/PROJECT_GUIDE.md.')
    return 0


def check():
    """Is everything precomputed still in step with the results database?

    Two kinds of data, each checked against what it was built from:
    - the rankings and school pages: the cache's stamp, a SHA-256 of the whole
      Track.db (a school page shows every season, so any change can move it);
    - the report data (artifacts): each one's own season and gender, so loading
      2027 results does not flag the 2026 reports.

    Exit codes: 0 current, 1 stale, 2 never built. --warn-only reports exactly
    the same thing and exits 0 -- for deploying a template or styling fix while
    the results are mid-rebuild, where blocking would be the wrong answer. It is
    a deliberate override, not a default: the deploy script uses the gate.
    """
    from app import create_app
    from app.jobs.artifacts import check_artifacts
    from common import cache_db

    app = create_app()
    with app.app_context():
        status = cache_db.cache_status()
        artifacts_stale, problems = check_artifacts()

    if not status['built']:
        print('precomputed data: NOT BUILT -- run python -m app.jobs.build_all')
        return 2

    if not (status['stale'] or artifacts_stale):
        print('precomputed data: current (built %s)' % status['generated_at'])
        return 0

    print('precomputed data: STALE')
    if status['stale']:
        print('  rankings and school pages: built %s, but the results have changed since.'
              % status['generated_at'])
    for problem in problems:
        print('  %s' % problem)
    print('  run: python -m app.jobs.build_all   (locally, then publish the cache)')
    return 1

if __name__ == '__main__':
    if '--list' in sys.argv:
        for name, module_path, *entry in JOBS:
            print('%-24s %s%s' % (name, module_path, ':' + entry[0] if entry else ''))
        sys.exit(0)
    if '--check' in sys.argv:
        code = check()
        if '--warn-only' in sys.argv and code == 1:
            print('  (--warn-only: continuing anyway)')
            code = 0
        sys.exit(code)
    sys.exit(build_all(resolve_seasons(sys.argv)))
