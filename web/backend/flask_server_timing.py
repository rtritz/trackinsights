"""
Server-side timing for the PythonAnywhere slowdown.

Two pieces:

  1. Server-Timing headers on every response, which the client snippet
     picks up automatically and shows in the diagnostics panel.
  2. A SQLAlchemy query counter + slow-query log, which is where the
     answer almost certainly is.

Drop into your Flask app (or import init_timing and call it on the app).
Remove when done.
"""

import time
from flask import Flask, g, request, current_app


# ---------------------------------------------------------------- 1. per-request
def init_timing(app: Flask, db=None, slow_query_ms: float = 25.0):

    @app.before_request
    def _start_timer():
        g._t_start = time.perf_counter()
        g._queries = []

    @app.after_request
    def _emit_server_timing(response):
        if not hasattr(g, "_t_start"):
            return response

        total_ms = (time.perf_counter() - g._t_start) * 1000.0
        queries = getattr(g, "_queries", [])
        db_ms = sum(q["ms"] for q in queries)

        parts = [
            f'total;dur={total_ms:.1f};desc="Total view time"',
            f'db;dur={db_ms:.1f};desc="Database ({len(queries)} queries)"',
            f'app;dur={max(total_ms - db_ms, 0):.1f};desc="Python (non-DB)"',
        ]

        # the single worst query, so you can see it without reading the log
        if queries:
            worst = max(queries, key=lambda q: q["ms"])
            parts.append(f'slowest;dur={worst["ms"]:.1f};desc="Slowest single query"')

        response.headers["Server-Timing"] = ", ".join(parts)

        # Server-Timing is not readable cross-origin unless exposed.
        # Harmless to set; needed if the API lives on another host.
        response.headers.setdefault("Timing-Allow-Origin", "*")

        # Log anything genuinely slow so it lands in the PythonAnywhere error log.
        if total_ms > 500:
            current_app.logger.warning(
                "SLOW %s %s  total=%.0fms db=%.0fms queries=%d",
                request.method, request.path, total_ms, db_ms, len(queries),
            )
            for q in sorted(queries, key=lambda q: -q["ms"])[:5]:
                current_app.logger.warning("  %6.1fms  %s", q["ms"], q["sql"][:300])

        return response

    if db is not None:
        _instrument_sqlalchemy(app, db, slow_query_ms)

    return app


# ---------------------------------------------------------------- 2. query timing
def _instrument_sqlalchemy(app, db, slow_query_ms):
    """
    Counts and times every SQL statement in the request. The N+1 pattern
    shows up here instantly: hundreds of near-identical fast queries whose
    sum dominates the response.

    Locally against SQLite each round trip is ~0.05ms, so 400 queries costs
    20ms and you never notice. Against a remote MySQL host each round trip
    is 2-5ms, so the same 400 queries costs 1-2 seconds. That difference
    alone accounts for the local/production gap in most cases like this.
    """
    from sqlalchemy import event

    # Flask-SQLAlchemy 3.x keys db.engine by app, and even the attribute
    # *lookup* (not just the read) raises RuntimeError outside an app
    # context - so the whole check has to happen inside one. hasattr()
    # doesn't help here: it only swallows AttributeError, not RuntimeError.
    with app.app_context():
        try:
            engine = db.engine
        except AttributeError:
            # db is already a raw SQLAlchemy Engine, not a Flask-SQLAlchemy
            # extension object.
            engine = db

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_q_start", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        started = conn.info["_q_start"].pop(-1)
        ms = (time.perf_counter() - started) * 1000.0
        try:
            g._queries.append({"ms": ms, "sql": " ".join(statement.split())})
        except (AttributeError, RuntimeError):
            pass  # outside a request context


# ---------------------------------------------------------------- usage
#
#   from flask_server_timing import init_timing
#   init_timing(app, db=db)
#
# Then load the page and look at the "Server-Timing" table in the browser
# panel. Read it like this:
#
#   db high, query count high     -> N+1. Fix with joinedload/selectinload
#                                    or a single aggregate query.
#   db high, query count low      -> one bad query. Get EXPLAIN on it;
#                                    usually a missing index.
#   app high, db low              -> Python-side work. On a throttled
#                                    PythonAnywhere tier this can be 5-10x
#                                    slower than your laptop for the same code.
#   total low, page still slow    -> not the server. Look at the API-request
#                                    table in the browser panel instead.