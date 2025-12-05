import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()


def create_app(config_class=Config):
    """Create a Flask app with SQLAlchemy database support."""
    here = os.path.abspath(os.path.dirname(__file__))
    template_folder = os.path.join(here, '..', 'frontend', 'templates')
    static_folder = os.path.join(here, '..', 'frontend', 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config.from_object(config_class)

    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '', 1)
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        if db_path and not os.path.exists(db_path):
            open(db_path, 'a').close()

    # Initialize database
    db.init_app(app)

    # Auto-create tables for fresh or empty SQLite databases so new environments
    # don't crash when queries run before migrations are applied.
    if db_uri.startswith('sqlite:///'):
        with app.app_context():
            db.create_all()

    # register blueprints
    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    return app
