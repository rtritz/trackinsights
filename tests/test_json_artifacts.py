"""The precomputed JSON: how it is written, and how it is served.

These files are unusual in that the bytes on disk are the bytes on the wire --
the routes forward them without parsing. That makes two things load-bearing that
would otherwise be cosmetic:

  * they must be written compact, because indentation is 42% of the response;
  * they must never be half-written, because nothing downstream would notice.

Both are the job of app/jobs/artifacts.py, so most of this tests that.
"""
import json
import os

import pytest

from app.jobs.artifacts import write_json_artifact

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'web', 'app', 'static', 'data')


# ------------------------------------------------------------------ the writer

def test_output_is_compact(tmp_path):
    """No indentation and no spaces after separators -- that is the 42%."""
    path = str(tmp_path / 'a.json')
    write_json_artifact(path, {'events': [{'name': 'x', 'rows': [1, 2]}]})
    text = open(path, encoding='utf-8').read()

    assert text == '{"events":[{"name":"x","rows":[1,2]}]}'
    assert '\n' not in text


def test_round_trips(tmp_path):
    payload = {'a': [1, 2.5, None, True], 'b': {'c': 'ünicode'}, 'd': []}
    path = str(tmp_path / 'b.json')
    write_json_artifact(path, payload)
    assert json.loads(open(path, encoding='utf-8').read()) == payload


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf')])
def test_nan_and_infinity_fail_the_build(tmp_path, bad):
    """json.dumps writes NaN happily and no JSON parser will read it back.

    Means and averages over an empty selection produce NaN, so this is a real
    way for a build to emit a file the browser cannot parse.
    """
    path = str(tmp_path / 'c.json')
    with pytest.raises(ValueError):
        write_json_artifact(path, {'avg': bad})


def test_a_rejected_payload_leaves_the_previous_file_alone(tmp_path):
    path = str(tmp_path / 'd.json')
    write_json_artifact(path, {'good': 1})

    with pytest.raises(ValueError):
        write_json_artifact(path, {'bad': float('nan')})

    assert json.loads(open(path, encoding='utf-8').read()) == {'good': 1}
    assert not os.path.exists(path + '.tmp'), 'temporary file left behind'


def test_no_temporary_file_survives_a_good_write(tmp_path):
    path = str(tmp_path / 'e.json')
    write_json_artifact(path, {'x': 1})
    assert os.listdir(tmp_path) == ['e.json']


def test_creates_the_directory(tmp_path):
    path = str(tmp_path / 'nested' / 'deep' / 'f.json')
    write_json_artifact(path, {'x': 1})
    assert os.path.exists(path)


# ------------------------------------------------------- what is on disk today

def _artifacts():
    for root, _dirs, files in os.walk(DATA_DIR):
        for name in sorted(files):
            if name.endswith('.json'):
                yield os.path.join(root, name)


def test_every_committed_artifact_is_parseable_and_finite():
    """Guards the files themselves, not just the writer."""
    problems = []
    for path in _artifacts():
        raw = open(path, 'rb').read()
        try:
            json.loads(raw)
        except ValueError as exc:
            problems.append('%s: %s' % (os.path.basename(path), exc))
            continue
        for token in (b'NaN', b'Infinity'):
            if token in raw:
                problems.append('%s contains %s' % (os.path.basename(path), token.decode()))
    assert not problems, 'bad precomputed artifacts:\n  ' + '\n  '.join(problems)


def test_the_big_artifacts_are_stored_compact():
    """A file rebuilt by hand with indent=2 would silently inflate its route."""
    fat = []
    for path in _artifacts():
        size = os.path.getsize(path)
        if size < 50_000:
            continue  # small ones are rendered into templates, not forwarded
        raw = open(path, encoding='utf-8').read()
        compact = json.dumps(json.loads(raw), separators=(',', ':'))
        if len(raw) > len(compact) * 1.05:
            fat.append('%s is %.0f%% larger than compact'
                       % (os.path.basename(path), 100 * (len(raw) / len(compact) - 1)))
    assert not fat, (
        'these are served to the browser verbatim, so the padding is wire cost:\n  '
        + '\n  '.join(fat))


# ---------------------------------------------------------------- the routes

SERVED = [
    ('/api/regional-qualifiers/top-list?gender=Boys&year=2026&source=rankings',
     'regional_predictions/combined_rankings_2026_boys.json'),
    ('/api/regional-qualifiers/top-list?gender=Girls&year=2026&source=results',
     'regional_predictions/combined_results_2026_girls.json'),
    ('/api/state-qualifiers?gender=Boys&year=2026',
     'state_predictions/state_qualifiers_2026_boys.json'),
]


@pytest.mark.parametrize('route,relative', SERVED)
def test_the_route_sends_the_file_byte_for_byte(client, route, relative):
    path = os.path.join(DATA_DIR, *relative.split('/'))
    if not os.path.exists(path):
        pytest.skip('%s not built' % relative)

    response = client.get(route)
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('application/json')
    assert response.data == open(path, 'rb').read(), (
        'the response should be the file itself; parsing and re-serializing it '
        'cost 12ms on the largest of these')


def test_a_missing_file_falls_through_instead_of_erroring(client):
    """The year is not built, so the route must compute rather than 500."""
    response = client.get('/api/state-qualifiers?gender=Boys&year=2019')
    assert response.status_code in (200, 400)
