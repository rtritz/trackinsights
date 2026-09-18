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
