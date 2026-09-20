"""Nothing the site serves may open a socket.

The qualifier pages used to fetch ihsaa.org while a visitor waited -- twice, in
two separate helpers -- each with a twenty-second timeout. A slow third party
made the site slow, and a hung one held a worker for the full twenty seconds.
The hosts change once a year, so the fetch is now a precompute job
(``app.jobs.precompute_tournament_hosts``) and the site reads its output.

These tests exist so that cannot come back quietly. The first is the real
guarantee: every route is exercised with the socket module sabotaged, so any
code that tries to connect fails loudly here rather than in production. The
second is a cheap readability check on top of it.
"""
import importlib
import pkgutil
import socket

import pytest


class NetworkUsed(AssertionError):
    pass


# The packages that run while a request is being served. jobs/ is deliberately
# absent -- that is where fetching is allowed, and where it now lives.
REQUEST_PATH_PACKAGES = ['app.queries', 'app.services', 'app.analytics', 'app.routes']

NETWORK_NAMES = ('urlopen', 'urlretrieve', 'Request')


@pytest.fixture()
def no_network(monkeypatch):
    """Make any attempt to open a socket raise."""
    def forbidden(*args, **kwargs):
        raise NetworkUsed(
            'the request path tried to open a network connection; fetching '
            'belongs in app/jobs/, not in code that serves a page')

    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    return forbidden


def test_no_route_opens_a_socket(app, client, no_network):
    """Every route renders with networking disabled."""
    from test_routes_smoke import EXPECTED, PARAMS, QUERY, _routes

    failures = []
    for rule in _routes(app):
        url = str(rule)
        for name in rule.arguments:
            if name not in PARAMS:
                continue
            url = url.replace('<int:%s>' % name, str(PARAMS[name]))
            url = url.replace('<path:%s>' % name, str(PARAMS[name]))
            url = url.replace('<%s>' % name, str(PARAMS[name]))
        if '<' in url:
            continue
        url += QUERY.get(str(rule), '')

        allowed = EXPECTED.get(str(rule), (200,))
        try:
            response = client.get(url)
        except NetworkUsed as exc:
            failures.append('%s tried to use the network: %s' % (url, exc))
            continue
        if response.status_code not in allowed and response.status_code != 500:
            continue
        # A 500 here is worth inspecting: it may be the sabotaged socket
        # surfacing as a caught exception rather than a raised one.
        if response.status_code == 500 and b'network' in response.data.lower():
            failures.append('%s answered 500 after touching the network' % url)

    assert not failures, 'Routes that reached for the network:\n  ' + '\n  '.join(failures)


def test_request_path_modules_do_not_import_urllib():
    """A readability guard: the serving packages should not name urlopen at all."""
    offenders = []
    for package_name in REQUEST_PATH_PACKAGES:
        package = importlib.import_module(package_name)
        modules = [package] + [
            importlib.import_module('%s.%s' % (package_name, info.name))
            for info in pkgutil.iter_modules(package.__path__)
        ]
        for module in modules:
            for name in NETWORK_NAMES:
                if hasattr(module, name):
                    offenders.append('%s.%s' % (module.__name__, name))

    assert not offenders, (
        'network helpers reachable from the request path: %s\n'
        'Fetching belongs in app/jobs/; the site reads what the job wrote.'
        % ', '.join(offenders))
