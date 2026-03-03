# Track Insights - AI Assistant Context

## Project Overview
Track Insights is an Indiana high school track and field data analysis web application. It provides athlete dashboards, school dashboards, result comparisons, percentile rankings, and various analytical queries for track and field meet data.

## Tech Stack
- **Backend**: Python 3, Flask, Flask-SQLAlchemy
- **Database**: SQLite (`web/data/Track.db`)
- **Frontend**: Jinja2 templates, Tailwind CSS, DaisyUI components
- **Testing**: pytest
- **Data Processing**: pandas (Jupyter notebooks in `jupyter/`)

## Project Structure
```
trackinsights/
├── web/                          # Main web application
│   ├── app.py                    # Entry point - creates Flask app
│   ├── config.py                 # Configuration (DB path, secrets)
│   ├── backend/
│   │   ├── __init__.py           # Flask app factory (create_app)
│   │   ├── models.py             # SQLAlchemy models
│   │   ├── queries.py            # Database query functions (3000+ lines)
│   │   ├── routes/
│   │   │   ├── main_routes.py    # Page rendering routes
│   │   │   └── api_routes.py     # JSON API endpoints (/api/*)
│   │   ├── scripts/              # Standalone scripts (percentiles, etc.)
│   │   └── util/                 # Utilities (conversion_util, db_util)
│   ├── frontend/
│   │   ├── templates/            # Jinja2 HTML templates
│   │   │   ├── base.html         # Base template (nav, footer, scripts)
│   │   │   ├── home.html         # Homepage
│   │   │   ├── athlete-*.html    # Athlete-related pages
│   │   │   ├── school-*.html     # School-related pages
│   │   │   └── queries/          # Query tool pages
│   │   ├── static/
│   │   │   ├── css/output.css    # Tailwind compiled CSS
│   │   │   ├── js/main.js        # Client-side JavaScript
│   │   │   └── images/           # Logos, backgrounds, icons
│   │   └── tailwind.config.js
│   └── data/Track.db             # SQLite database
├── jupyter/                      # Jupyter notebooks for data analysis
└── docs/                         # Project documentation
```

## Database Models (web/backend/models.py)
Key entities:
- **Athlete**: `athlete_id`, `first`, `last`, `school_id`, `gender`, `graduation_year` (mapped as `grad_year`)
- **School**: `school_id`, `school_name`, `team_name`, `city`, `zip`, etc.
- **AthleteResult**: Composite PK (`athlete_id`, `meet_id`, `event`, `result_type`), `result`, `result2` (float), `place`, `grade`
- **Meet**: `meet_id`, `meet_type` (Sectional/Regional/State), `gender`, `year`, `host`, `meet_num`
- **Event**: `event` (PK), `event_type`
- **RelayResult**: School relay results
- **SchoolEnrollment**: School enrollment data by year

## Important Constants (web/backend/scripts/util/const_util.py)
```python
CONST.GENDER.ALL = ["Boys", "Girls"]
CONST.MEET_TYPE.ALL = ["Sectional", "Regional", "State"]
CONST.RESULT_TYPE.ALL = ["Prelim", "Final"]
CONST.EVENT.ALL_TRACK = ["100 Meters", "200 Meters", "400 Meters", "800 Meters", "1600 Meters", "3200 Meters"]
CONST.EVENT.ALL_FIELD = ["High Jump", "Long Jump", "Shot Put", "Discus", "Pole Vault"]
CONST.EVENT.ALL_RELAY = ["4 x 100 Relay", "4 x 400 Relay", "4 x 800 Relay"]
CONST.EVENT.ALL_GIRLS_HURDLES = ["100 Hurdles", "300 Hurdles"]
CONST.EVENT.ALL_BOYS_HURDLES = ["110 Hurdles", "300 Hurdles"]
```

## Route Patterns

### Main Routes (render HTML pages)
- `/` - Homepage
- `/search` - Athlete search page
- `/athlete-dashboard/<int:athlete_id>` - Athlete dashboard
- `/athlete-dashboard/<int:athlete_id>/result/<int:meet_id>/<path:event_name>` - Result detail
- `/school-dashboard/<int:school_id>` - School dashboard
- `/queries` - Queries index
- `/queries/percentiles` - Percentiles query tool
- `/queries/hypothetical` - Hypothetical result tool
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

### Time/Distance Conversion (web/backend/util/conversion_util.py)
```python
from backend.util.conversion_util import Conversion
CONVERSION = Conversion()
seconds = CONVERSION.time_to_seconds("1:52.34")  # 112.34
inches = CONVERSION.distance_to_inches("5'11\"")  # 71.0
```

### Database Helper (web/backend/util/db_util.py)
```python
from backend.util.db_util import Database
db = Database("data/Track.db")
event_type = db.get_event_type("100 Meters")  # "Track"
```

## Running the Application
```bash
cd web
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python app.py
# Visit http://localhost:5000
```

## Key Implementation Notes
1. **result vs result2**: `result` is the display string (e.g., "1:52.34"), `result2` is the float value for sorting/comparison
2. **Sprint DNQ events**: 100m, 200m, 100H, 110H have prelims where DNQ athletes don't advance
3. **Grade levels**: FR, SO, JR, SR (Freshman, Sophomore, Junior, Senior)
4. **School enrollment**: Used for "like schools" comparisons (within 25% enrollment size)
5. **Meet types progression**: Sectional → Regional → State

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
- Python modules: snake_case (`api_routes.py`, `conversion_util.py`)
- CSS/JS: kebab-case for files, camelCase for JS functions
