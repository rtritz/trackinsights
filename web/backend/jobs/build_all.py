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

    python -m backend.jobs.build_all            # rebuild everything
    python -m backend.jobs.build_all --check    # is anything stale? (exit 1 if so)
    python -m backend.jobs.build_all --list     # what would run

Then commit the changed files under web/frontend/static/data/ and web/data/.
"""
import importlib
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

# Ordered because the dashboard cache reads the rank history: building it first
# means the dashboards are built against a current one rather than last week's.
JOBS = [
    ('program_rank_history', 'backend.jobs.precompute_program_rank_history'),
    ('core_cache', 'backend.jobs.precompute_core_cache'),
    ('dashboard_v4', 'backend.jobs.precompute_dashboard_v4'),
    ('combined_rankings', 'backend.jobs.precompute_combined_rankings'),
    ('combined_results', 'backend.jobs.precompute_combined_results'),
    ('regional_predictions', 'backend.jobs.precompute_regional_predictions'),
    ('state_predictions', 'backend.jobs.precompute_state_predictions'),
    ('state_qualifiers', 'backend.jobs.precompute_state_qualifiers'),
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
    print('All artifacts rebuilt. Commit the changes under')
    print('  web/frontend/static/data/   and   web/data/dashboard_cache.db')
    return 0


def check():
    """Is the dashboard cache still in step with the results database?

    Only the V4 cache records what it was built from, so it is the one that can
    answer this. It is also the artifact most likely to be noticed if wrong, and
    anything that changed the results changed it too -- so in practice it stands
    for all of them.
    """
    from backend import create_app
    from backend.services import dashboard_v4 as svc
    app = create_app()
    with app.app_context():
        status = svc.cache_status()
    if not status['built']:
        print('precomputed data: NOT BUILT -- run python -m backend.jobs.build_all')
        return 2
    if status['stale']:
        print('precomputed data: STALE')
        print('  built %s, but the results have changed since.' % status['generated_at'])
        print('  run: python -m backend.jobs.build_all   (locally, then commit)')
        return 1
    print('precomputed data: current (built %s)' % status['generated_at'])
    return 0


if __name__ == '__main__':
    if '--list' in sys.argv:
        for name, module_path in JOBS:
            print('%-24s %s' % (name, module_path))
        sys.exit(0)
    if '--check' in sys.argv:
        sys.exit(check())
    sys.exit(build_all())
