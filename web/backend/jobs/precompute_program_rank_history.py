"""
Precompute each program's statewide rank in every covered season.

The v3 school dashboard draws a rank-history trend and a year-over-year arrow.
Both need only two numbers per season -- the school's rank and the size of the
field -- but getting them meant calling _build_statewide_program_rankings() once
per season, and that builds the full statewide table each time.  A cold
dashboard was paying for four of those to read eight numbers.

Running this is OPTIONAL.  The file records the database fingerprint it was
built from, and the dashboard rebuilds it automatically whenever that no longer
matches -- so new results are picked up with nothing to remember.  What running
it here buys is that the one slow rebuild happens now, rather than landing on
whichever visitor arrives first after the data changed.

From web/:
    python -m backend.jobs.precompute_program_rank_history
"""
import os
import sys

# Ensure 'backend' is importable when running this script directly
HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.abspath(os.path.join(HERE, '..', '..'))
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

from backend import create_app  # noqa: E402
from backend.queries import (  # noqa: E402
    PROGRAM_RANK_HISTORY_PATH,
    write_program_rank_history,
)


def main():
    app = create_app()
    with app.app_context():
        # The same builder the dashboard's self-heal path uses, so the file can
        # never be written here in a shape the reader does not expect.
        payload = write_program_rank_history()

    index = payload.get('index') or {}
    tables = sum(len(seasons) for seasons in index.values())
    rows = sum(len(school) for seasons in index.values() for school in seasons.values())
    print('wrote %s' % os.path.normpath(PROGRAM_RANK_HISTORY_PATH))
    print('  %d gender/season tables, %d school rows, %.0f KB'
          % (tables, rows, os.path.getsize(PROGRAM_RANK_HISTORY_PATH) / 1e3))
    print('  fingerprint %s' % payload.get('fingerprint'))


if __name__ == '__main__':
    main()
