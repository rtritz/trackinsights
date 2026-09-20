"""queries/shared.py stays a helpers module, not a re-export hub.

It used to re-export thirty names it had only imported -- the models, ``db``,
``func``, ``joinedload``, ``typing.Optional`` -- and every feature module took
them from there rather than from where they live. See shared.py's own docstring
for why that was worth undoing.

This asserts the property directly: a module may only hand on names it defines.
"""
import ast
import os

QUERIES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'web', 'app', 'queries')

# The package's front door is a deliberate re-export surface -- that is its whole
# job, and test_queries_package.py covers what belongs in it.
EXEMPT = {'__init__.py'}


def _definitions(tree):
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _imports(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.asname or a.name.split('.')[0] for a in node.names)
    return names


def _module_trees():
    for name in sorted(os.listdir(QUERIES)):
        if name.endswith('.py') and name not in EXEMPT:
            path = os.path.join(QUERIES, name)
            with open(path, encoding='utf-8') as handle:
                yield name, ast.parse(handle.read(), filename=path)


def test_no_module_takes_a_borrowed_name_from_a_sibling():
    """`from .x import y` must name something x actually defines."""
    defined, imported = {}, {}
    for name, tree in _module_trees():
        module = name[:-3]
        defined[module] = _definitions(tree)
        imported[module] = _imports(tree)

    violations = []
    for name, tree in _module_trees():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ImportFrom) and node.level == 1):
                continue
            source = node.module
            if source not in defined:
                continue
            for alias in node.names:
                if alias.name in defined[source]:
                    continue
                if alias.name in imported[source]:
                    violations.append(
                        '%s takes %r from .%s, which only imported it'
                        % (name, alias.name, source))

    assert not violations, (
        'borrowed names passed along between modules:\n  %s\n'
        'Import it from where it is defined instead.' % '\n  '.join(violations))
