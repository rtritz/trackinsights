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

from app.jobs import artifacts as artifacts_module
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


# ---------------------------------------------------- the manifest / staleness

@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    """Point the writer at a scratch directory, not the real static/data."""
    monkeypatch.setattr(artifacts_module, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(artifacts_module, 'MANIFEST_PATH',
                        str(tmp_path / 'manifest.json'))
    monkeypatch.setattr(artifacts_module, 'source_fingerprint', lambda: 'HASH-1')
    return tmp_path


def test_writing_an_artifact_stamps_it(isolated_data_dir):
    write_json_artifact(str(isolated_data_dir / 'a.json'), {'x': 1})

    manifest = artifacts_module.read_manifest()
    assert 'a.json' in manifest
    assert manifest['a.json']['source_hash'] == 'HASH-1'
    assert manifest['a.json']['bytes'] == len('{"x":1}')


def test_stamping_one_artifact_leaves_the_others_alone(isolated_data_dir):
    """Jobs run individually; rebuilding one must not vouch for the rest."""
    write_json_artifact(str(isolated_data_dir / 'a.json'), {'x': 1})
    write_json_artifact(str(isolated_data_dir / 'b.json'), {'x': 2})

    manifest = artifacts_module.read_manifest()
    assert set(manifest) == {'a.json', 'b.json'}


def test_consistent_artifacts_are_not_stale(isolated_data_dir):
    write_json_artifact(str(isolated_data_dir / 'a.json'), {'x': 1})
    stale, problems = artifacts_module.check_artifacts()
    assert not stale, problems


def test_an_artifact_built_from_another_database_is_stale(isolated_data_dir, monkeypatch):
    """The scenario the check exists for: Track.db moved, this file did not."""
    write_json_artifact(str(isolated_data_dir / 'a.json'), {'x': 1})

    monkeypatch.setattr(artifacts_module, 'source_fingerprint', lambda: 'HASH-2')
    stale, problems = artifacts_module.check_artifacts()

    assert stale
    assert any('a.json' in p and 'different Track.db' in p for p in problems), problems


def test_rebuilding_only_one_artifact_flags_the_other(isolated_data_dir, monkeypatch):
    """Exactly what running a single precompute job looks like."""
    write_json_artifact(str(isolated_data_dir / 'fresh.json'), {'x': 1})
    write_json_artifact(str(isolated_data_dir / 'stale.json'), {'x': 2})

    # Track.db changes; only one job is re-run.
    monkeypatch.setattr(artifacts_module, 'source_fingerprint', lambda: 'HASH-2')
    write_json_artifact(str(isolated_data_dir / 'fresh.json'), {'x': 1})

    stale, problems = artifacts_module.check_artifacts()
    assert stale
    assert any('stale.json' in p for p in problems), problems
    assert not any('fresh.json' in p for p in problems), problems


def test_a_deleted_artifact_is_reported(isolated_data_dir):
    path = isolated_data_dir / 'a.json'
    write_json_artifact(str(path), {'x': 1})
    path.unlink()

    stale, problems = artifacts_module.check_artifacts()
    assert stale
    assert any('missing from disk' in p for p in problems), problems


def test_an_unstamped_artifact_is_reported(isolated_data_dir):
    write_json_artifact(str(isolated_data_dir / 'a.json'), {'x': 1})
    (isolated_data_dir / 'stranger.json').write_text('{}', encoding='utf-8')

    stale, problems = artifacts_module.check_artifacts()
    assert stale
    assert any('stranger.json' in p for p in problems), problems


def test_externally_sourced_artifacts_are_exempt(isolated_data_dir):
    """tournament_hosts.json comes from ihsaa.org; a Track.db hash says nothing."""
    write_json_artifact(str(isolated_data_dir / 'a.json'), {'x': 1})
    hosts = isolated_data_dir / 'tournament_hosts'
    hosts.mkdir()
    (hosts / 'tournament_hosts.json').write_text('{}', encoding='utf-8')

    stale, problems = artifacts_module.check_artifacts()
    assert not stale, problems


def test_no_manifest_at_all_is_stale(isolated_data_dir):
    (isolated_data_dir / 'a.json').write_text('{}', encoding='utf-8')
    stale, problems = artifacts_module.check_artifacts()
    assert stale
    assert 'never been stamped' in problems[0]


# ------------------------------------------------------- the committed manifest

def test_the_committed_artifacts_are_all_stamped_and_current(app):
    """The real static/data, against the real Track.db."""
    with app.app_context():
        stale, problems = artifacts_module.check_artifacts()
    assert not stale, (
        'the committed artifacts do not match web/data/Track.db:\n  '
        + '\n  '.join(problems)
        + '\nRun: cd web && python -m app.jobs.build_all')
