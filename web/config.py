import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'Track.db')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Off unless asked for. Flask's debugger executes arbitrary code typed into
    # the browser, so this must never default to on for a deployed site. Local
    # development is unaffected: wsgi.py passes debug=True to app.run() directly.
    DEBUG = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')

    # Per-request timing and a slow-query log, wired up in the app factory.
    # Diagnostic instrumentation, so it is off unless asked for: it attaches a
    # listener to every SQLAlchemy query and runs on every request.
    SERVER_TIMING = os.environ.get('SERVER_TIMING', '').lower() in ('1', 'true', 'yes')

    # Create the schema at start-up when it is missing. True only for tests,
    # which build their own fixture database. In a deployed environment a
    # missing Track.db means the deploy failed to copy it, and creating an
    # empty one turns that into a site that serves pages with no data on them
    # -- the failure has to be loud instead.
    AUTO_CREATE_SCHEMA = False
