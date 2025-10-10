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

    # Initialize database
    db.init_app(app)

    # register blueprints
    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    return app
