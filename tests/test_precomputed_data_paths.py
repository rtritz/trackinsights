"""The precomputed JSON is actually found.

These routes prefer a precomputed file and fall back to live computation when it
is missing. That fallback is silent by design -- no error, no log, just a page
that takes seconds instead of milliseconds -- so a wrong path here is invisible
until somebody notices the site is slow. It happened once already: the paths
were built from ``current_app.root_path`` plus ``'..'``, which resolves to
``web/static/data`` rather than ``web/app/static/data``.

So this asserts the route serves the file rather than computing the answer. The
year is read from whatever is on disk, so a new season's files need no edit here.
"""
import json
import os
import re

import pytest

# Each precomputed set: the directory under app/static/data, a filename pattern
# with the year and gender as groups, and the route that should serve it.
SETS = [
    ('regional_predictions', r'combined_rankings_(\d{4})_(boys|girls)\.json',
     '/api/regional-qualifiers/top-list?gender={gender}&year={year}&source=rankings'),
    ('regional_predictions', r'combined_results_(\d{4})_(boys|girls)\.json',
     '/api/regional-qualifiers/top-list?gender={gender}&year={year}&source=results'),
    ('state_predictions', r'state_qualifiers_(\d{4})_(boys|girls)\.json',
     '/api/state-qualifiers?gender={gender}&year={year}'),
]


@pytest.mark.parametrize('subdir,pattern,route', SETS)
def test_route_serves_the_precomputed_file(app, client, subdir, pattern, route):
    directory = os.path.join(app.static_folder, 'data', subdir)
    assert os.path.isdir(directory), (
        '%s is missing -- the precompute jobs write here, and the routes read here' % directory)

    matches = [(m, name) for name, m in
               ((n, re.fullmatch(pattern, n)) for n in os.listdir(directory)) if m]
    if not matches:
        pytest.skip('no %s files built yet' % pattern)

    match, filename = matches[0]
    year, gender = match.group(1), match.group(2)

    with open(os.path.join(directory, filename), encoding='utf-8') as handle:
        on_disk = json.load(handle)

    response = client.get(route.format(gender=gender.title(), year=year))
    assert response.status_code == 200
    # Served from the file, not recomputed: the fixture database holds none of
    # this season's results, so a fallback would answer with an empty payload.
    assert json.loads(response.data) == on_disk
