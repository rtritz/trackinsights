---

## 📁 Project Layout

```
track_app/
│
├── app.py                  # Main entry point that starts the Flask server. Imports and initializes the app from backend/__init__.py.
├── config.py               # Stores configuration settings such as database path, debug mode, etc.
│
├── backend/                # Contains all Flask logic — routes, models, and database queries. Used by the back-end developer.
│   ├── __init__.py         # Initializes the Flask app, registers blueprints, and connects to the database.
│   ├── models.py           # Defines SQLAlchemy models (tables such as Athlete, School, etc.).
│   ├── queries.py          # Reusable database functions (e.g., get_athletes(), add_school()).
│   ├── routes/             # Organizes all Flask route files for modularity.
│   │   ├── __init__.py
│   │   ├── main_routes.py  # Routes that render web pages (e.g., /home, /search).
│   │   └── api_routes.py   # Routes that serve JSON responses for APIs or AJAX calls.
│
├── frontend/               # Contains all user-facing assets — HTML, Tailwind CSS, JS, and images. Used by the front-end developer.
│   ├── templates/          # Jinja2 HTML templates rendered by Flask.
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── athlete-search.html
│   │   └── ...
│   ├── static/             # Static files served to the browser.
│   │   ├── css/
│   │   │   └── styles.css  # Tailwind build output file.
│   │   ├── js/
│   │   │   └── main.js     # Custom JavaScript for interactivity.
│   │   └── images/         # Project images and icons.
│   └── tailwind.config.js  # Tailwind configuration for custom colors, fonts, and themes.
│
├── data/                   # Storage of DB
│   └── Track.db            # SQLite database file.
│
├── tests/                  # Optional folder for test scripts to verify routes, APIs, and models.
│   └── test_routes.py
│
├── requirements.txt        # Lists Python dependencies for easy installation.
├── README.md               # Project documentation and setup instructions.
└── .gitignore              # Excludes unnecessary files (e.g., __pycache__, .env, Track.db).
```

---

