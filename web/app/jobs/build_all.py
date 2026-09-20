"""
Rebuild every precomputed artifact the site serves.

One command, so "I updated the results" has exactly one follow-up step and there
is no list to remember. Each job is run in turn, timed, and reported; a job that
fails is reported and the rest still run, because a broken regional-predictions
build should not stop the dashboards from being rebuilt.

WHERE TO RUN THIS
-----------------
Locally, before committing -- NOT on PythonAnywhere.

The deploy script wipes ~/mysite and copies from a fresh clone, so anything not
committed to git is gone the moment you deploy. And the artifacts are derived
from Track.db, which is itself committed: building them from the same working
copy that produced Track.db is what keeps the two in step by construction.

Building on the server instead would mean roughly an hour of work on every
deploy -- this takes ~5 minutes here and PythonAnywhere measured 15-25x slower
on the same code -- for an artifact that would be identical to the one you could
have committed.

    python -m app.jobs.build_all            # rebuild everything
    python -m app.jobs.build_all --check    # is anything stale? (exit 1 if so)
    python -m app.jobs.build_all --check --warn-only   # report, always exit 0
    python -m app.jobs.build_all --list     # what would run

Then publish: the JSON under web/app/static/data/ and Track.db go in git; the
dashboard cache goes to a GitHub Release, because it is ~12MB and rebuilt whole
every time. Both steps are spelled out in docs/PROJECT_GUIDE.md section 10, and
this script prints them when it finishes.
"""
import importlib
import sys
import time
import traceback


# Dashboards first: it is by far the longest job, so a failure in one of the
# quick prediction builds surfaces after the expensive work is already safe.
JOBS = [
    # Hosts first, and cheap: the dashboards and qualifier pages label meets with
    # them, so a stale file here shows up on everything built afterwards.
    ('tournament_hosts', 'app.jobs.precompute_tournament_hosts'),
    ('dashboard_v4', 'app.jobs.precompute_dashboard_v4'),
    ('combined_rankings', 'app.jobs.precompute_combined_rankings'),
    ('combined_results', 'app.jobs.precompute_combined_results'),
    ('regional_predictions', 'app.jobs.precompute_regional_predictions'),
    ('state_predictions', 'app.jobs.precompute_state_predictions'),
    ('state_qualifiers', 'app.jobs.precompute_state_qualifiers'),
]


def run_one(name, module_path):
    module = importlib.import_module(module_path)
    entry = getattr(module, 'main', None)
    if entry is None:
        raise RuntimeError('%s has no main()' % module_path)
    entry()


def build_all():
    print('Rebuilding %d precomputed artifacts\n' % len(JOBS))
    started = time.perf_counter()
    failed = []
    for name, module_path in JOBS:
        print('-' * 70)
        print('== %s' % name)
        t0 = time.perf_counter()
        try:
            run_one(name, module_path)
            print('   done in %.0fs' % (time.perf_counter() - t0))
        except Exception:  # noqa: BLE001
            # Reported and carried past: one broken job should not leave every
            # other artifact stale as well.
            failed.append(name)
            print('   FAILED after %.0fs' % (time.perf_counter() - t0))
            traceback.print_exc()
    print('-' * 70)
    print('\nTotal %.0fs' % (time.perf_counter() - started))
    if failed:
        print('FAILED: %s' % ', '.join(failed))
        print('Do not commit a partial rebuild -- fix these and run again.')
        return 1
    print('All artifacts rebuilt. Two things to publish:')
    print('  git  -- web/app/static/data/  and  web/data/Track.db')
    print('  release -- gh release upload cache-latest '
          'web/data/dashboard_cache.db --clobber')
    print('')
    print('dashboard_cache.db is NOT in git (it is ~12MB, rewritten every build).')
    print('The deploy downloads it from that release -- see docs/PROJECT_GUIDE.md.')
    return 0


def check():
    """Is everything precomputed still in step with the results database?

    Two artifacts, checked the same way: each records the SHA-256 of the
    Track.db it was built from, and this re-hashes the Track.db that is here now
    and compares.

    Both are checked, not just the cache. The cache used to stand in for the
    whole set on the reasoning that anything changing the results changed it
    too -- true when everything was rebuilt together, false the moment one job
    is run on its own. Rebuilding the dashboards alone left ten stale JSON files
    and still reported "current", which is worse than not checking.

    Exit codes: 0 current, 1 stale, 2 never built. --warn-only reports exactly
    the same thing and exits 0 -- for deploying a template or styling fix while
    the results are mid-rebuild, where blocking would be the wrong answer. It is
    a deliberate override, not a default: the deploy script uses the gate.
    """
    from app import create_app
    from app.services import dashboard_v4 as svc
    from app.jobs.artifacts import check_artifacts

    app = create_app()
    with app.app_context():
        status = svc.cache_status()
        json_stale, json_problems = check_artifacts()

    if not status['built']:
        print('precomputed data: NOT BUILT -- run python -m app.jobs.build_all')
        return 2

    stale = status['stale'] or json_stale
    if not stale:
        print('precomputed data: current (built %s)' % status['generated_at'])
        return 0

    print('precomputed data: STALE')
    if status['stale']:
        print('  dashboard cache: built %s, but the results have changed since.'
              % status['generated_at'])
    for problem in json_problems:
        print('  %s' % problem)
    print('  run: python -m app.jobs.build_all   (locally, then commit)')
    return 1


if __name__ == '__main__':
    if '--list' in sys.argv:
        for name, module_path in JOBS:
            print('%-24s %s' % (name, module_path))
        sys.exit(0)
    if '--check' in sys.argv:
        code = check()
        if '--warn-only' in sys.argv and code == 1:
            print('  (--warn-only: continuing anyway)')
            code = 0
        sys.exit(code)
    sys.exit(build_all())
