# Track Insights

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
pip install -e ".[web,standalone,dev]"
```

## Running the web app

```bash
cd web
python app.py
# Visit http://localhost:5000
```

`web/data/Track.db` is tracked in git (the deployed site pulls it directly from GitHub), so it's already present and populated -- no separate DB setup step is needed.

## Working with `standalone/`

- `standalone/notebooks/` -- open with Jupyter/VS Code once the venv above is set up and selected as the kernel.
- `standalone/scripts/` -- run directly, e.g. `python standalone/scripts/calculate_team_scores.py`.

Both import shared code the same way the web app does: `from common.db import Database`, `from common.const import CONST`, etc.

## More detail

See `CLAUDE.md` for the full project structure, database schema, coding conventions, and route reference.
