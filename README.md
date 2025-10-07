# Track Insights (template)

This repository contains a template project structure for a Flask app with a simple frontend and a SQLite database.

Run locally

1. Create and activate a virtual environment

   python -m venv venv; .\venv\Scripts\Activate.ps1

2. Install dependencies

   pip install -r requirements.txt

3. Initialize the database (if desired)

   from app import app
   from backend import db
   with app.app_context():
       db.create_all()

4. Run

   python app.py

Notes

- The `data/Track.db` file is included as an empty DB file.
- Frontend templates live under `frontend/templates` and static assets under `frontend/static`.
