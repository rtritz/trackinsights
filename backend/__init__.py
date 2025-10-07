import os
from flask import Flask
from config import Config


def create_app(config_class=Config):
    """Create a Flask app. DB usage is disabled in this minimal template.

    Enable DB later by swapping in a SQLAlchemy-backed implementation.
    """
    here = os.path.abspath(os.path.dirname(__file__))
    template_folder = os.path.join(here, '..', 'frontend', 'templates')
    static_folder = os.path.join(here, '..', 'frontend', 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config.from_object(config_class)
    app.config['USE_DB'] = False

    # register blueprints
    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    return app
