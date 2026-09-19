"""The Flask application.

Everything the running site needs is in this package: the routes, the queries
behind them, the templates they render and the static files those templates
ask for.

    templates/   the HTML
    static/      the CSS, JavaScript, images and precomputed JSON
    routes/      which URL runs which code
    queries/     the database questions, grouped by feature
    analytics/   the prediction and percentile engines
    jobs/        the precompute scripts -- run between seasons, not per request
    services/    the precomputed-dashboard cache

templates/ and static/ sit here rather than in a separate folder because that
is where Flask looks for them by default -- `Flask(__name__)` finds them with
no configuration, which is one less thing to get wrong.

The site is started by web/wsgi.py, one directory up.
"""
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()


def create_app(config_class=Config):
    """Create a Flask app with SQLAlchemy database support."""
    # templates/ and static/ are beside this file, which is exactly where Flask
    # looks; nothing to configure.
    app = Flask(__name__)
    app.config.from_object(config_class)

    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    auto_create = app.config.get('AUTO_CREATE_SCHEMA', False)

    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '', 1)
        if auto_create:
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            if db_path and not os.path.exists(db_path):
                open(db_path, 'a').close()
        elif db_path and not os.path.exists(db_path):
            # Loudly, rather than serving a site with nothing on it. Creating
            # the file here would turn "the deploy did not copy Track.db" into
            # a working site whose every page is empty -- which looks like a
            # data problem and is really a deployment one.
            raise RuntimeError(
                'Track database not found at %s. On a deployed site this means '
                'the deploy did not copy web/data/Track.db.' % db_path)

    db.init_app(app)

    # Only where something is expected to build its own schema -- the test
    # fixtures. A deployed site reads a database that already exists.
    if auto_create and db_uri.startswith('sqlite:///'):
        with app.app_context():
            db.create_all()

    # "166" -> "166th". Used by the V4 dashboard, which prints a lot of places
    # and ranks; a filter keeps that formatting out of both the template and the
    # precomputed payload, so the cache stores numbers and the page decides how
    # to say them.
    @app.template_filter('ordinal')
    def _ordinal(value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            return value
        if 11 <= (number % 100) <= 13:
            return '%dth' % number
        return '%d%s' % (number, {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th'))

    # Points can be halves -- ties split the combined value of the slots they
    # occupy -- so they are floats. "27.0 points" is noise; "27.5" is the reason
    # they are floats at all.
    @app.template_filter('num')
    def _num(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return value
        return '%d' % number if number == int(number) else ('%g' % number)

    # Cache-busting for our own CSS and JS, available to every template as
    # asset_version('js/thing.js'). Derived from the file's modification time,
    # so a saved edit is visible on the next load instead of after a hard
    # refresh -- which has already cost one "the page isn't updating" round trip.
    #
    # A context processor rather than a per-route argument: a page that gains a
    # script should not also require its route to be edited.
    @app.context_processor
    def _asset_helpers():
        def asset_version(filename):
            try:
                return str(int(os.path.getmtime(
                    os.path.join(app.static_folder, filename))))
            except (OSError, TypeError):
                return '0'
        return {'asset_version': asset_version}

    # register blueprints
    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Query results are cached in-process and keyed on their arguments, so
    # nothing evicts them when Track.db is replaced -- a worker would serve the
    # rankings it computed at start-up until someone reloaded the web app. This
    # notices the swap and clears them, so processing new results is all that
    # updating results takes. The check is one os.stat per request.
    from .queries import ensure_fresh_queries

    @app.before_request
    def _refresh_caches_if_db_changed():
        try:
            ensure_fresh_queries()
        except Exception:
            app.logger.exception('database freshness check failed')

    # Per-request timing and a slow-query log. Diagnostic instrumentation --
    # it listens to every query -- so it is registered only when asked for,
    # with SERVER_TIMING=1. It is what identified the 153-query page.
    if app.config.get('SERVER_TIMING'):
        from .flask_server_timing import init_timing
        init_timing(app, db=db)

    return app
