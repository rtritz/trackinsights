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
import re

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

    @app.template_filter('relay_names')
    def _relay_names(value):
        if not value:
            return value

        names = re.split(r'\band\b|&|/|;|,|\+', value, flags=re.IGNORECASE)
        abbreviated = []
        for name in names:
            parts = name.split()
            if len(parts) > 1:
                abbreviated.append('%s. %s' % (parts[0][0].upper(), parts[-1]))
            elif parts:
                abbreviated.append(parts[0])
        return ', '.join(abbreviated)

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

    @app.context_processor
    def _event_navigation_data():
        # Keep the event picker aligned with the canonical DB event names while
        # presenting familiar labels in the menu and homepage search.
        from common.const import CONST
        from .event_dashboards import EVENT_DASHBOARDS

        pages_by_event = {page['event']: page for page in EVENT_DASHBOARDS}

        def event_row(boys_event, boys_label, girls_event=None, girls_label=None):
            girls_event = girls_event or boys_event
            girls_label = girls_label or boys_label
            return {'links': [
                {
                    'event_name': event_name,
                    'label': f'{gender} {label}',
                    'url': f"/events/{gender.lower()}/{pages_by_event[event_name]['slug']}",
                    'gender': gender,
                }
                for gender, event_name, label in (
                    ('Boys', boys_event, boys_label),
                    ('Girls', girls_event, girls_label),
                )
            ]}

        return {'event_nav_groups': [
            {'label': 'Sprints', 'events': [
                event_row(CONST.EVENT.E100, '100m Dash'),
                event_row(CONST.EVENT.E200, '200m Dash'),
                event_row(CONST.EVENT.E400, '400m Dash'),
            ]},
            {'label': 'Distance', 'events': [
                event_row(CONST.EVENT.E800, '800m Run'),
                event_row(CONST.EVENT.E1600, '1600m Run'),
                event_row(CONST.EVENT.E3200, '3200m Run'),
            ]},
            {'label': 'Hurdles', 'events': [
                event_row(CONST.EVENT.E110H, '110m Hurdles', CONST.EVENT.E100H, '100m Hurdles'),
                event_row(CONST.EVENT.E300H, '300m Hurdles'),
            ]},
            {'label': 'Relays', 'events': [
                event_row(CONST.EVENT.E400R, '4×100m Relay'),
                event_row(CONST.EVENT.E1600R, '4×400m Relay'),
                event_row(CONST.EVENT.E3200R, '4×800m Relay'),
            ]},
            {'label': 'Field Events', 'events': [
                event_row(CONST.EVENT.ELJ, 'Long Jump'),
                event_row(CONST.EVENT.EHJ, 'High Jump'),
                event_row(CONST.EVENT.ESP, 'Shot Put'),
                event_row(CONST.EVENT.EDT, 'Discus Throw'),
                event_row(CONST.EVENT.EPV, 'Pole Vault'),
            ]},
        ]}

    # register blueprints
    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Athlete card PNGs are painted in-process with Pillow. If that cannot
    # work here (package or font missing) say so at start-up, in the error
    # log a deployer actually reads, instead of a 503 on every card.
    from .services.cards import paint_problem
    with app.app_context():
        theCardProblem = paint_problem()
    app.config['CARDS_RENDER_PROBLEM'] = theCardProblem
    if theCardProblem is not None:
        app.logger.error('athlete cards cannot render on this server: %s', theCardProblem)

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
