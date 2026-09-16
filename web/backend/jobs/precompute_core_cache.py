"""
Precompute the core dashboard payload for every school.

get_school_dashboard_v2_core sits under every v3 endpoint -- _v3_scope calls it
to resolve the season -- and on the school dashboard it is what the "Loading
postseason program profile..." message waits for. This writes the payload each
school gets when it asks with no season, which is exactly the first page load.

Unlike precompute_program_rank_history, this one does NOT rebuild itself: it
takes minutes, and doing that inside a request would hang the page it exists to
speed up. So RUN THIS AFTER RESULTS CHANGE. Forgetting is safe -- the file
records the database fingerprint it was built from and is ignored once that
stops matching, which costs speed, never correctness.

From web/:
    python -m backend.jobs.precompute_core_cache
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from backend import create_app  # noqa: E402
from backend.models import School  # noqa: E402
from backend.queries import write_core_cache  # noqa: E402
from common.const import CONST  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        school_ids = [row.school_id for row in School.query.with_entities(School.school_id)]
        print('%d schools' % len(school_ids))
        for gender in CONST.GENDER.ALL:
            started = time.perf_counter()
            path, payload = write_core_cache(gender, school_ids)
            # entries is keyed by season, each holding one payload per school
            # that competed in it -- so the count to report is the payloads, not
            # the length of the outer dict, which is just the season count.
            buckets = payload['entries']
            rows = sum(len(bucket) for bucket in buckets.values())
            print('  %-5s %d seasons, %d payloads (%d schools), %.1f KB, %.0fs'
                  % (gender, len(buckets), rows, len(school_ids),
                     os.path.getsize(path) / 1e3, time.perf_counter() - started))
        print('fingerprint %s' % payload['fingerprint'])


if __name__ == '__main__':
    main()
