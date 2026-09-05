# Track Insights - AI Assistant Context

## Project Overview
Track Insights is an Indiana high school track and field data analysis web application. It provides athlete dashboards, school dashboards, result comparisons, percentile rankings, and various analytical queries for track and field meet data.

## Tech Stack
- **Backend**: Python 3, Flask, Flask-SQLAlchemy
- **Database**: SQLite (`web/data/Track.db`)
- **Frontend**: Jinja2 templates, Tailwind CSS, DaisyUI components
- **Testing**: pytest
- **Data Processing**: pandas, notebooks and standalone scripts in `standalone/`

## Project Structure
```
trackinsights/
├── pyproject.toml                # Defines the `common` package + optional dependency groups (web/standalone/dev)
├── common/                       # THE shared library -- used by both web/ and standalone/. One canonical
│   │                              copy of Database, Conversion, CONST, etc. No per-area duplicates of these.
│   ├── db.py                     # Database class (sqlite3 + pandas wrapper)
│   ├── conversion.py             # Conversion class (time/distance <-> string parsing)
│   ├── const.py                  # CONST (event/gender/meet-type constants, DB_PATH)
│   ├── regional_hosts.py         # Manual regional host mappings
│   └── standards.py              # State-qualifying standard marks by year
│
├── web/                          # Flask app. Run with `cd web && python app.py` (repo-root venv)
│   ├── app.py                    # Entry point - creates Flask app
│   ├── config.py                 # Configuration (DB path, secrets)
│   ├── backend/
│   │   ├── __init__.py           # Flask app factory (create_app)
│   │   ├── models.py             # SQLAlchemy models
│   │   ├── queries.py            # Database query functions (imports from `common`)
│   │   ├── routes/
│   │   │   ├── main_routes.py    # Page rendering routes
│   │   │   └── api_routes.py     # JSON API endpoints (/api/*)
│   │   ├── analytics/            # Engines imported live by queries.py/routes at request time
│   │   │   ├── percentiles.py
│   │   │   ├── regional_predictions.py
│   │   │   ├── state_predictions.py
│   │   │   ├── projected_team_scores.py
│   │   │   └── examples/         # Runnable demo scripts (not pytest, not part of the request path)
│   │   ├── jobs/                 # Batch/precompute scripts -- run periodically, not per-request
│   │   │   └── precompute_*.py   # Regenerate the static JSON under frontend/static/data/
│   │   └── videos.py
│   ├── frontend/
│   │   ├── templates/            # Jinja2 HTML templates
│   │   │   ├── base.html         # Base template (nav, footer, scripts)
│   │   │   ├── home.html         # Homepage
│   │   │   ├── athlete-*.html    # Athlete-related pages
│   │   │   ├── school-dashboard.html
│   │   │   └── insights/         # Insights pages (queries & reports)
│   │   ├── static/
│   │   │   ├── css/output.css    # Tailwind compiled CSS
│   │   │   ├── js/main.js        # Client-side JavaScript
│   │   │   └── images/           # Logos, backgrounds, icons
│   │   └── tailwind.config.js
│   └── data/                     # Track.db (tracked in git -- deployment pulls it directly)
│
├── standalone/                   # Programs that are NOT part of the web app -- data pipeline / maintenance tools
│   ├── notebooks/                # Jupyter notebooks (scraping, merging, one-off analysis)
│   │   └── Load Schools in DB.ipynb  # Yearly: load schools/enrollment from an IHSAA CSV, then
│   │                                  # scrape logos (myIHSAA) and geocode addresses (US Census)
│   │                                  # for any school missing one, each in its own cell
│   ├── scripts/                  # Plain .py standalone programs (calculate_team_scores.py, etc.)
│   └── reports/                  # Generated report notebooks + their output PDFs/TSVs
│
└── docs/                         # Project documentation
```

## `common/` -- the one shared library
`common/` is a real installable package (`pip install -e ".[web,standalone,dev]"` once per environment/venv). The Flask app, notebooks, and standalone scripts all import from it the same way, regardless of their own location or working directory -- e.g. `from common.db import Database`, `from common.const import CONST`. **Do not create a new per-area copy of Database/Conversion/CONST/etc.** -- if a standalone script or a web route needs a new shared helper, add it to `common/` so both sides use the same implementation.

## Database Models (web/backend/models.py)
Key entities:
- **Athlete**: `athlete_id`, `first`, `last`, `school_id`, `gender`, `graduation_year` (mapped as `grad_year`)
- **School**: `school_id`, `school_name`, `team_name`, `city`, `zip`, `logo_path` (relative path under `frontend/static/`, `None` if no logo), etc.
- **AthleteResult**: Composite PK (`athlete_id`, `meet_id`, `event`, `result_type`), `result`, `result2` (float), `place`, `grade`
- **Meet**: `meet_id`, `meet_type` (Sectional/Regional/State), `gender`, `year`, `host`, `meet_num`
- **Event**: `event` (PK), `event_type`
- **RelayResult**: School relay results
- **SchoolEnrollment**: School enrollment data by year

## Important Constants (common/const.py)
```python
CONST.GENDER.ALL = ["Boys", "Girls"]
CONST.MEET_TYPE.ALL = ["Sectional", "Regional", "State"]
CONST.RESULT_TYPE.ALL = ["Prelim", "Final"]
CONST.EVENT.ALL_TRACK = ["100 Meters", "200 Meters", "400 Meters", "800 Meters", "1600 Meters", "3200 Meters"]
CONST.EVENT.ALL_FIELD = ["High Jump", "Long Jump", "Shot Put", "Discus", "Pole Vault"]
CONST.EVENT.ALL_RELAY = ["4 x 100 Relay", "4 x 400 Relay", "4 x 800 Relay"]
CONST.EVENT.ALL_GIRLS_HURDLES = ["100 Hurdles", "300 Hurdles"]
CONST.EVENT.ALL_BOYS_HURDLES = ["110 Hurdles", "300 Hurdles"]
CONST.DB_PATH  # absolute, cwd-independent path to web/data/Track.db
```

## Route Patterns

### Main Routes (render HTML pages)
- `/` - Homepage
- `/search` - Athlete search page
- `/athlete-dashboard/<int:athlete_id>` - Athlete dashboard
- `/athlete-dashboard/<int:athlete_id>/result/<int:meet_id>/<path:event_name>` - Result detail
- `/school-dashboard/<int:school_id>` - School dashboard
- `/insights` - Insights index (queries & reports)
- `/insights/percentiles` - Percentiles query tool
- `/insights/hypothetical` - Hypothetical result tool
- `/about` - About page

### API Routes (return JSON, prefix: `/api`)
- `GET /api/search?q=<query>` - Search athletes/schools
- `GET /api/athletes` - List athletes
- `GET /api/athletes/<id>` - Get athlete by ID
- `GET /api/athletes/<id>/dashboard` - Athlete dashboard data
- `GET /api/athletes/<id>/result-rankings` - Result rankings
- `GET /api/percentiles/options` - Percentile filter options
- `GET /api/percentiles` - Percentile data
- `GET /api/sectional-trends/options` - Sectional trends options
- `GET /api/hypothetical/options` - Hypothetical query options

## Coding Conventions

### Python/Flask
- Use Flask application factory pattern (`create_app()`)
- Blueprints: `main_bp` for pages, `api_bp` for API endpoints (prefix `/api`)
- Query functions go in `queries.py`, return dicts or model instances
- Use `@lru_cache` for expensive computations that don't change often
- Import db from backend: `from . import db` or `from backend import db`
- Shared, non-web-specific logic (DB access, unit conversion, constants) belongs in `common/`, imported as `from common.<module> import <name>` -- never re-implemented locally

### API Response Format
```python
# Success
return jsonify(data)
return jsonify(data), 201  # Created

# Error
return jsonify({'error': 'message'}), 404
return jsonify({'error': 'message'}), 400
```

### Templates (Jinja2)
- Extend `base.html`: `{% extends 'base.html' %}`
- Content block: `{% block content %}...{% endblock %}`
- Static files: `{{ url_for('static', filename='css/output.css') }}`
- Dynamic routes: `{{ url_for('main.athlete_dashboard', athlete_id=123) }}`

### Frontend Styling
- Use **DaisyUI** component classes (btn, card, badge, modal, etc.)
- Theme: `data-theme="autumn"` on `<html>`
- Custom fonts: Oswald (impact style), Racing Sans One
- Color conventions:
  - Boys: `border-blue-500 text-blue-600`
  - Girls: `border-pink-500 text-pink-600`
  - Schools: `border-green-500 text-green-600`

### JavaScript
- Vanilla JS (no framework)
- Fetch API for AJAX calls to `/api/*`
- DOM ready: `document.addEventListener('DOMContentLoaded', function() { ... })`
- Use `AbortController` for cancellable requests

## Utility Functions

### Time/Distance Conversion (common/conversion.py)
```python
from common.conversion import Conversion
CONVERSION = Conversion()
seconds = CONVERSION.time_to_seconds("1:52.34")  # 112.34
inches = CONVERSION.distance_to_inches("5'11\"")  # 71.0
```
Handles hand-timed marks with a trailing "h" (`"23.5h"`) and non-numeric sentinel tokens (`"NT"`, `"DNF"`, `"DNS"`, `"DQ"`, ...), mapping them to `9999` seconds / `0` inches rather than raising -- this matches the sentinel convention already written into `result2` by the scraping pipeline.

### Database Helper (common/db.py)
```python
from common.db import Database
from common.const import CONST
db = Database(CONST.DB_PATH)
event_type = db.get_event_type("100 Meters")  # "Track"
```

## Running the Application
One virtual environment at the repo root covers both the web app and standalone/ work:
```bash
python -m venv .venv
.venv\Scripts\activate      # or source .venv/bin/activate on macOS/Linux
pip install -e ".[web,standalone,dev]"

cd web
python app.py
# Visit http://localhost:5000
```

## Key Implementation Notes
1. **result vs result2**: `result` is the display string (e.g., "1:52.34"), `result2` is the float value for sorting/comparison
2. **Sprint DNQ events**: 100m, 200m, 100H, 110H have prelims where DNQ athletes don't advance
3. **Grade levels**: FR, SO, JR, SR (Freshman, Sophomore, Junior, Senior)
4. **School enrollment**: Used for "like schools" comparisons (within 25% enrollment size)
5. **Meet types progression**: Sectional → Regional → State
6. **Team scoring**: Sectional/Regional score the top 8 places (10-8-6-5-4-3-2-1); State scores the top 9 (10-8-7-6-5-4-3-2-1). Ties split the combined value of the scoring slots they occupy evenly across the tied schools/athletes -- see `web/backend/queries.py::_compute_cumulative_points` and `standalone/scripts/calculate_team_scores.py::get_points` for the canonical implementation of this logic.

## Common Query Patterns
```python
# Get athlete with school loaded
athlete = Athlete.query.options(joinedload(Athlete.school)).get(athlete_id)

# Filter results by meet type and year
results = AthleteResult.query.join(Meet).filter(
    Meet.meet_type == "Sectional",
    Meet.year == 2024
).all()

# Search with fuzzy matching
results = search_bar(query)  # Returns list of dicts with type, id, name
```

## File Naming Conventions
- Templates: kebab-case (`athlete-dashboard.html`, `athlete-result-detail.html`)
- Python modules: snake_case (`api_routes.py`, `conversion.py`)
- CSS/JS: kebab-case for files, camelCase for JS functions
