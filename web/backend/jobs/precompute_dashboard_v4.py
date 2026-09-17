"""
Build the V4 school dashboard cache.

Walks every school x gender x season and writes one prepared payload per
combination into web/data/dashboard_cache.db, which is all a V4 page request
reads. Everything expensive -- statewide rankings, qualifier lists, near-miss
selection, head-to-head, returning athletes -- happens here.

RUN THIS AFTER RESULTS CHANGE. The page renders whatever the cache holds and
does not check whether it is still current; a school with no cached payload is
told the dashboard has not been built yet rather than being served stale or
computed on the spot.

The outer loop is gender/season rather than school on purpose: the statewide
tables are computed once per gender/season and then sliced for all 414 schools,
so the expensive part is paid twelve times rather than five thousand.

From web/:
    python -m backend.jobs.precompute_dashboard_v4
    python -m backend.jobs.precompute_dashboard_v4 --limit 25    # a quick subset
    python -m backend.jobs.precompute_dashboard_v4 --check       # is it stale?
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from backend import create_app  # noqa: E402
from backend import queries  # noqa: E402
from backend.models import School  # noqa: E402
from backend.services import dashboard_v4 as svc  # noqa: E402
from common.const import CONST  # noqa: E402


def seasons_for(gender):
    """Every season a reader can select, newest first, plus all-time."""
    years = sorted(queries._covered_rank_seasons(), reverse=True)
    return [str(y) for y in years] + ['all-time']


def main(limit=None):
    app = create_app()
    started = time.perf_counter()
    rows = []
    ranking_rows = []
    with app.app_context():
        school_ids = [r.school_id for r in School.query.with_entities(School.school_id)]
        if limit:
            school_ids = school_ids[:limit]
        print('%d schools' % len(school_ids))

        for gender in CONST.GENDER.ALL:
            for season in seasons_for(gender):
                t0 = time.perf_counter()
                built = 0
                for school_id in school_ids:
                    try:
                        payload = svc.build_payload(school_id, gender, season, queries)
                    except ValueError:
                        # Not a season this school competed in.
                        continue
                    except Exception as exc:  # noqa: BLE001
                        print('   ! %s %s %s: %s' % (school_id, gender, season, exc))
                        continue
                    if not payload:
                        continue
                    rows.append((school_id, gender, season, svc._encode(payload)))
                    built += 1
                # The lists behind the rank figures: one set per gender/season,
                # not per school. Built here because the statewide tables are
                # already warm from the payloads above.
                for event, payload in svc.build_rankings(gender, season, queries):
                    ranking_rows.append((gender, season, event, svc._encode(payload)))
                print('  %-5s %-8s %4d payloads  %5.0fs'
                      % (gender, season, built, time.perf_counter() - t0))

    path = svc.write_cache(rows, svc.source_size(), ranking_rows)
    size = os.path.getsize(path)
    print()
    print('wrote %s' % os.path.normpath(path))
    print('  %d payloads, %d ranked lists, %.1f MB, %.0fs total'
          % (len(rows), len(ranking_rows), size / 1e6, time.perf_counter() - started))
    meta = svc.cache_meta()
    print('  generated_at %s | data v%s | methodology v%s | source_size %s'
          % (meta.get('generated_at'), meta.get('data_version'),
             meta.get('methodology_version'), meta.get('source_size')))


def check():
    """Exit non-zero if the cache no longer matches the results database.

    For wiring into a deploy or a results-loading script, so forgetting to
    rebuild fails loudly there instead of quietly on the site.
    """
    app = create_app()
    with app.app_context():
        status = svc.cache_status()
    if not status['built']:
        print('dashboard cache: NOT BUILT')
        return 2
    if status['stale']:
        print('dashboard cache: STALE -- built %s, results have changed since'
              % status['generated_at'])
        print('  rebuild: python -m backend.jobs.precompute_dashboard_v4')
        return 1
    print('dashboard cache: current (built %s)' % status['generated_at'])
    return 0


if __name__ == '__main__':
    if '--check' in sys.argv:
        sys.exit(check())
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    main(limit)
