"""Precompute the school pages (templates/school-page.html) into dashboard_cache.db.

Why: PythonAnywhere runs this analysis 15-25x slower than a development
machine, so pages built per request would take seconds there. Stored pages
make every view a single read.

What: for every school and both teams, the chosen seasons plus All-Time --
All-Time always, because any season's new results change it. Each page is
stored without the statewide distribution curves, which are the same for every
school and are restored from the rankings at request time; that keeps a page
to ~10KB compressed.

Run through build_all (it passes the seasons), or directly from web/:

    python -m app.jobs.precompute_school_pages            # every covered season
    python -m app.jobs.precompute_school_pages 2026       # one season (+ All-Time)

Depends on the rankings lists in the same file, so build_all runs it after
the rankings step. The write is one transaction: a failed build changes nothing.
"""
import sys
import time

from app import create_app, queries
from app.models import School
from common import cache_db
from app.services import school_page as pages
from common.const import CONST


def build_rows(years):
    """(school_id, gender, view, encoded payload) for every school, team and view."""
    views = [str(year) for year in sorted(years)] + ['all-time']
    school_ids = [sid for (sid,) in School.query.with_entities(School.school_id).order_by(School.school_id)]
    rows, skipped = [], 0
    # Season by season, then team, then school: each season's statewide work
    # (cached per season, with a small cap) is built once and reused by every
    # school. School-major order would cycle all seasons per school and keep
    # evicting it.
    for view in views:
        for gender in CONST.GENDER.ALL:
            started = time.perf_counter()
            for school_id in school_ids:
                try:
                    payload = pages.build_payload(school_id, gender, view, with_results=view != 'all-time')
                except ValueError:
                    skipped += 1
                    continue
                if payload is not None:
                    rows.append((school_id, gender, view, cache_db.encode(pages.slim_payload(payload))))
            print('  %s %s: %d schools in %.0fs' % (view, gender, len(school_ids), time.perf_counter() - started))
            sys.stdout.flush()
    return rows, views, skipped


def main(years=None):
    started = time.perf_counter()
    app = create_app()
    with app.app_context():
        years = sorted(years) if years else sorted(queries._covered_rank_seasons())
        print('Building school pages for %s + All-Time' % ', '.join(map(str, years)))
        rows, views, skipped = build_rows(years)
        pages.write_school_pages(rows, views)
    size = sum(len(row[3]) for row in rows)
    print('Stored %d pages (%.1f MB) in %.0fs%s.' % (
        len(rows), size / 1e6, time.perf_counter() - started,
        ', %d skipped' % skipped if skipped else ''))
    return 0


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(main([int(arg)] if arg else None))
