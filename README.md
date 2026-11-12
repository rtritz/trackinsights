# Track Insights

This repository is a temporary prototype clone of the [original Track Insights repository](https://github.com/rtritz/trackinsights), used with explicit permission from Mr. Ritz. The official website is [trackinsights.org](https://trackinsights.org).

An Indiana high school track & field data analysis app: athlete/school dashboards, result comparisons, percentile rankings, and meet-projection tools, built on a SQLite database of meet results.

## Repository layout

- **`common/`** -- the shared library (database access, unit conversion, constants) used by both the web app and the standalone programs. See `CLAUDE.md` for details.
- **`web/`** -- the Flask web application.
- **`standalone/`** -- data-pipeline and maintenance programs that are *not* part of the web app: scraping notebooks, one-off scripts, generated reports.
- **`docs/`** -- project documentation. **New to the project? Start with
  [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md)** -- it explains the layout,
  where to make each kind of change, and the data workflow.

## Setup

One virtual environment at the repo root covers everything (the web app, notebooks, and standalone scripts):

```bash
python -m venv .venv
.venv\Scripts\activate      # or source .venv/bin/activate on macOS/Linux
python -m pip install --upgrade pip
pip install -e ".[web,standalone,dev]"
```

The pip upgrade matters: the pip that ships with macOS and some older Python
installs is too old to install this project and quietly installs nothing.
Run the `pip install -e` line again after every `git pull` that adds a
package (the athlete cards added Pillow); the app says so at start-up and on
the athlete dashboard if something is missing.

## Running the web app

```bash
cd web
python wsgi.py
# Visit http://localhost:5000
```

`web/data/Track.db` is tracked in git (the deployed site pulls it directly from GitHub), so it's already present and populated -- no separate DB setup step is needed.

## Working with `standalone/`

- `standalone/notebooks/` -- open with Jupyter/VS Code once the venv above is set up and selected as the kernel.
- `standalone/scripts/` -- run directly, e.g. `python standalone/scripts/calculate_team_scores.py`.

Both import shared code the same way the web app does: `from common.db import Database`, `from common.const import CONST`, etc.

## More detail

See `CLAUDE.md` for the full project structure, database schema, coding conventions, and route reference.
