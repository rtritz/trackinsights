"""Every route answers.

A smoke test, not a feature test: it asserts that each URL resolves, renders and
does not raise. That is deliberately shallow, and it is the cheapest useful
safety net this project can have -- it catches the whole class of mistakes that
reorganisation causes. A moved template, a renamed query function, a route
referencing a helper that no longer exists: all of them fail here, immediately,
instead of in front of a visitor.

It is driven by Flask's own url_map, so a new route is covered the moment it is
added -- if it needs URL parameters, add them to PARAMS below and the test picks
it up. A route with no entry is reported rather than silently skipped.

What it does NOT do is check that a page is *correct*. Tests for that live
alongside the feature they cover.
"""
import pytest

# Values to fill in each route's parameters. The fixture database (see
# conftest.py) has schools 1-3, athletes 101-105 at school 1, and meets in
# 2023-2024.
PARAMS = {
    'aid': 101,
    'athlete_id': 101,
    'school_id': 1,
    'meet_id': 4,
    'event_name': '100 Meters',
    'gender': 'Boys',
    'season': '2024',
}

# Query strings for routes that need them. Supplying real arguments exercises
# the route properly; accepting its "you did not ask me anything" 400 would test
# almost nothing.
QUERY = {
    '/api/athletes/<int:aid>/result-rankings': '?meet_id=4&event=100%20Meters',
    '/api/percentiles': '?events=100%20Meters&genders=Boys',
    '/api/search': '?q=alpha',
}

# Routes that legitimately answer with something other than 200 for these
# arguments, with the reason. Anything not listed must return 200.
EXPECTED = {
    # The v4 cache is built from the real database, so the fixture has no
    # payload; the page says so rather than inventing one.
    '/school-dashboard-v4/<int:school_id>': (200,),
    '/school-dashboard-v4/<int:school_id>/<gender>/<season>': (200,),
    # Ranked lists come from that same cache.
    '/api/v4/rankings/<gender>/<season>': (200, 404),
    # These need query arguments to do anything; without them they answer, but
    # a 400 is a legitimate "you did not ask me anything".
    '/api/hypothetical-rank': (200, 400),
    '/api/percentiles': (200, 400),
    '/api/sectional-trends': (200, 400),
    '/api/regional-qualifiers': (200, 400),
    '/api/regional-qualifiers/top-list': (200, 400),
    '/api/state-qualifiers': (200, 400),
    '/insights/hypothetical/result': (200, 400),
}


def _routes(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        if 'GET' not in (rule.methods or set()):
            continue
        yield rule


def test_every_route_has_test_parameters(app):
    """A new route with an unknown parameter must be noticed, not skipped."""
    unknown = set()
    for rule in _routes(app):
        unknown |= set(rule.arguments) - set(PARAMS)
    assert not unknown, (
        'No test value for URL parameter(s) %s. Add them to PARAMS in this file '
        'so the new route is covered.' % sorted(unknown)
    )


def test_every_route_answers(app, client):
    """Each route resolves and renders without raising."""
    failures = []
    for rule in _routes(app):
        url = rule.build({k: PARAMS[k] for k in rule.arguments})[1]
        url += QUERY.get(rule.rule, '')
        allowed = EXPECTED.get(rule.rule, (200,))
        try:
            status = client.get(url).status_code
        except Exception as exc:  # noqa: BLE001 -- report, do not stop
            failures.append('%s raised %s: %s' % (url, type(exc).__name__, exc))
            continue
        if status not in allowed:
            failures.append('%s returned %s, expected one of %s'
                            % (url, status, list(allowed)))
    assert not failures, 'Routes that did not answer:\n  ' + '\n  '.join(failures)


def test_every_referenced_static_file_exists(app, client):
    """Every script and stylesheet a template asks for actually resolves.

    Driven by what the templates reference, not by a list kept here -- a list
    verifies that files exist, which is not the same thing and misses the
    mistake that actually happens: a template pointing at a name that does not.

    A missing <script src> is silent. The browser reports nothing the reader can
    see; the page simply sits there inert. This is the test that catches it.
    """
    import re

    referenced = set()
    for rule in _routes(app):
        url = rule.build({k: PARAMS[k] for k in rule.arguments})[1]
        url += QUERY.get(rule.rule, '')
        response = client.get(url)
        if response.status_code != 200 or 'html' not in response.content_type:
            continue
        html = response.get_data(as_text=True)
        # Our own assets only -- a CDN being down is not this test's business.
        for match in re.finditer(r'(?:src|href)="(/static/[^"?]+)', html):
            referenced.add(match.group(1))

    assert referenced, 'no static references found; the crawl may have broken'
    missing = sorted(p for p in referenced if client.get(p).status_code != 200)
    assert not missing, (
        'Templates reference these files, but they do not exist:\n  %s'
        % '\n  '.join(missing)
    )
