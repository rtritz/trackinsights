"""The layers only depend downwards.

    routes  ->  services  ->  queries  ->  analytics  ->  common

Each layer may use the ones below it and must not reach back up. That was not
always true: ``app.analytics.percentiles`` imported ``app.db`` to fetch a
connection, which made analytics simultaneously the bottom of the stack and a
consumer of the top of it. The give-away was that the import had to be written
*inside* the function -- at module level it was a cycle and would not load.

A function-local import is how that kind of mistake hides, so this reads the
source rather than the imported module: an import nested inside a function is
found exactly like one at the top of the file.
"""
import ast
import os

import pytest

WEB_APP = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web', 'app')

# Lowest first. A layer may import from itself and from anything below it.
LAYERS = ['analytics', 'queries', 'services', 'routes']

# `app` itself (the package root) holds the Flask app and `db`. Everything above
# analytics is allowed to use it; analytics is not, which is the rule this file
# was written for.
ROOT_ALLOWED_FROM = {'queries', 'services', 'routes'}


def _package_files(layer):
    directory = os.path.join(WEB_APP, layer)
    for name in sorted(os.listdir(directory)):
        if name.endswith('.py'):
            yield os.path.join(directory, name)


def _imported_layers(path, own_layer):
    """Which sibling layers this file imports, and whether it imports app.db.

    Resolves relative imports by level: inside app/<layer>/x.py, `from . import`
    is the layer itself, `from .. import` is the app package, and
    `from ..other import` is the sibling layer `other`.
    """
    with open(path, encoding='utf-8') as handle:
        tree = ast.parse(handle.read(), filename=path)

    layers, uses_root = set(), False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ''
            if node.level == 2:            # from .. / from ..something
                head = module.split('.')[0] if module else ''
                if head in LAYERS:
                    layers.add(head)
                else:
                    # `from .. import db`, or `from ..models import X`
                    uses_root = True
            elif node.level == 0 and module.startswith('app.'):
                head = module.split('.')[1]
                if head in LAYERS:
                    layers.add(head)
                else:
                    uses_root = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith('app.'):
                    head = alias.name.split('.')[1]
                    if head in LAYERS:
                        layers.add(head)
                    else:
                        uses_root = True

    layers.discard(own_layer)
    return layers, uses_root


@pytest.mark.parametrize('layer', LAYERS)
def test_layer_does_not_import_upwards(layer):
    rank = LAYERS.index(layer)
    allowed = set(LAYERS[:rank])

    violations = []
    for path in _package_files(layer):
        imported, _ = _imported_layers(path, layer)
        for other in sorted(imported - allowed):
            violations.append('%s imports app.%s' % (
                os.path.relpath(path, WEB_APP).replace(os.sep, '/'), other))

    assert not violations, (
        'these reach up the stack instead of down:\n  %s\n'
        'Order is %s -- pass what is needed in as an argument instead.'
        % ('\n  '.join(violations), ' -> '.join(LAYERS)))


def test_analytics_does_not_reach_for_the_flask_app():
    """analytics/ is the bottom: it takes a connection, it does not fetch one."""
    violations = []
    for path in _package_files('analytics'):
        _, uses_root = _imported_layers(path, 'analytics')
        if uses_root:
            violations.append(os.path.relpath(path, WEB_APP).replace(os.sep, '/'))

    assert not violations, (
        'these import from the app package (its db, models or config): %s\n'
        'analytics runs against any connection; the caller supplies it.'
        % ', '.join(violations))
