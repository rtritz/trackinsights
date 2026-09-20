"""Batch/precompute jobs -- run periodically (not per-request) to refresh the
dashboard cache and the static JSON files web/app/routes serves.

Run them as modules, from web/:

    python -m app.jobs.build_all                    # everything
    python -m app.jobs.precompute_combined_rankings # just one

WHY THE sys.path LINE BELOW
---------------------------
The jobs import `app` and `config` by their plain top-level names, because that
is how the deployed site is laid out: the deploy copies web/'s *contents* up, so
`app/`, `config.py` and `data/` sit at the server's root. Nothing is pip
installed there -- pyproject.toml is not even copied -- so `web/` has to be on
sys.path for those names to resolve.

Running `python -m app.jobs.x` from web/ already puts it there, so this is
belt-and-braces for the case where the working directory is elsewhere. It lives
here, in the package every job goes through, rather than being repeated at the
top of all eight of them -- which is what it was, eight identical four-line
blocks, none of them explaining themselves.

The catch is that Python runs this file only when the jobs are imported as a
package. `python web/app/jobs/build_all.py` -- passing the path rather than the
module -- gets no package context, so this never runs and the import of `app`
fails. That invocation is not used anywhere: every doc, every job's own
docstring, the deploy script and the site's own "rebuild with" messages all say
`python -m`. Use `-m`.
"""
import os
import sys

_WEB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

if _WEB_DIR not in sys.path:
    sys.path.insert(0, _WEB_DIR)
