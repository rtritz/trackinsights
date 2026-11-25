"""The report data in dashboard_cache.db: how it is stored, served and checked.

Replaces the JSON files that used to live under web/app/static/data/. Each
report is one named artifact (common/cache_db.py), written by the precompute
jobs through app/jobs/artifacts.py and stamped with the season it was built
from, so `build_all --check` can tell which reports are stale.
"""
import json

import pytest

from app.jobs import artifacts as artifacts_module
from app.jobs.artifacts import check_artifacts, write_artifact
from common import cache_db, tournament_hosts


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    """A scratch cache, never the real web/data/dashboard_cache.db."""
    monkeypatch.setattr(cache_db, 'CACHE_DB_PATH', str(tmp_path / 'cache.db'))
    monkeypatch.setattr(cache_db, 'source_hash', lambda: 'HASH-1')
    return tmp_path


# ------------------------------------------------------------------ storing

def test_stored_compact_and_round_trips(cache):
    payload = {'a': [1, 2.5, None, True], 'b': {'c': 'ünicode'}, 'd': []}
    write_artifact('a', payload)
    assert cache_db.load_artifact('a') == payload
    # Sent to the browser as is, so it is stored without padding.
    assert cache_db.artifact_json('a') == json.dumps(payload, separators=(',', ':')).encode('utf-8')


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf')])
def test_nan_and_infinity_fail_the_build_and_keep_the_previous_version(cache, bad):
    """json.dumps writes NaN happily and no JSON parser reads it back. Means over
    an empty selection produce NaN, so this is a real way to break a report."""
    write_artifact('a', {'good': 1})
    with pytest.raises(ValueError):
        write_artifact('a', {'avg': bad})
    assert cache_db.load_artifact('a') == {'good': 1}


def test_a_missing_artifact_or_cache_gives_the_default(cache):
    assert cache_db.load_artifact('nothing', default=[]) == []
    cache_db.connect(readonly=False).close()
    assert cache_db.load_artifact('nothing', default={'ready': False}) == {'ready': False}


def test_tournament_hosts_round_trip_through_the_cache(cache):
    tournament_hosts.save_all({'2026|Boys|regional': {1: 'Valparaiso', 2: 'Warsaw'}})
    tournament_hosts._load_stamped.cache_clear()
    assert tournament_hosts.get_regional_hosts(2026, 'Boys') == {1: 'Valparaiso', 2: 'Warsaw'}


# ------------------------------------------------------------------ serving

@pytest.fixture()
def season_2031(monkeypatch):
    """Make 2031 the current season (the newest year with results)."""
    from app.routes import api_routes
    monkeypatch.setattr(api_routes, 'current_season', lambda: 2031)


SERVED = [
    ('/api/regional-qualifiers/top-list?gender=Boys&source=rankings', 'combined_rankings_2031_boys'),
    ('/api/regional-qualifiers/top-list?gender=Girls&source=results', 'combined_results_2031_girls'),
    ('/api/state-qualifiers?gender=Boys', 'state_qualifiers_2031_boys'),
    # Only the current season is served: an older year in the request is ignored.
    ('/api/state-qualifiers?gender=Boys&year=2025', 'state_qualifiers_2031_boys'),
]


@pytest.mark.parametrize('route,name', SERVED)
def test_the_route_sends_the_stored_json_as_is(cache, client, season_2031, route, name):
    write_artifact(name, {'context': {'stored': name}, 'events': []})
    response = client.get(route)
    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('application/json')
    assert response.data == cache_db.artifact_json(name)


def test_regional_qualifiers_are_served_from_the_stored_lists(cache, client, season_2031):
    write_artifact('regional_qualifiers_2031_girls', {
        'status': {'year': 2031, 'stored': 'status'},
        'regionals': {str(n): {'context': {'regional_num': n}, 'events': []} for n in range(1, 9)},
    })
    status = client.get('/api/regional-qualifiers/status?gender=Girls&year=2026')
    assert status.status_code == 200 and status.get_json() == {'year': 2031, 'stored': 'status'}
    detail = client.get('/api/regional-qualifiers?gender=Girls&regional_num=3')
    assert detail.status_code == 200 and detail.get_json()['context'] == {'regional_num': 3}
    assert client.get('/api/regional-qualifiers?gender=Girls').status_code == 400


def test_a_report_not_built_falls_through_instead_of_erroring(cache, client):
    response = client.get('/api/state-qualifiers?gender=Boys')
    assert response.status_code in (200, 400)


def test_only_the_current_seasons_qualifier_data_is_kept(cache):
    from app.jobs import build_all
    for name, year in (('state_qualifiers_2026_boys', 2026), ('state_qualifiers_2027_boys', 2027),
                       ('regional_qualifiers_2026_girls', 2026), ('combined_results_2026_girls', 2026),
                       ('combined_rankings_2027_girls', 2027),
                       # Year-named report pages keep theirs.
                       ('state_predictions_2026_boys', 2026)):
        write_artifact(name, {'x': 1}, year=year, gender='Boys', stamp=False)
    write_artifact('tournament_hosts', {'x': 1})
    removed = build_all.prune_old_seasons(2027)
    assert sorted(removed) == ['combined_results_2026_girls', 'regional_qualifiers_2026_girls',
                               'state_qualifiers_2026_boys']
    assert sorted(cache_db.artifact_stamps()) == ['combined_rankings_2027_girls', 'state_predictions_2026_boys',
                                                  'state_qualifiers_2027_boys', 'tournament_hosts']


def test_report_pages_read_their_data_from_the_cache(cache, client):
    write_artifact('state_predictions_2026_boys',
                   {'ready': True, 'rows': [], 'missing_regionals': [], 'regionals_loaded': 8})
    assert client.get('/insights/reports/2026-state-predictions').status_code == 200
    assert client.get('/insights/reports/2026-regional-predictions').status_code == 200


# ------------------------------------------------------------------ staleness

def test_consistent_artifacts_are_not_stale(cache):
    write_artifact('a', {'x': 1})
    assert check_artifacts() == (False, [])


def test_no_artifacts_at_all_is_stale(cache):
    stale, problems = check_artifacts()
    assert stale and 'run build_all' in problems[0]


def test_an_artifact_built_from_another_database_is_stale(cache, monkeypatch):
    """The scenario the check exists for: Track.db moved, this artifact did not."""
    write_artifact('a', {'x': 1})
    monkeypatch.setattr(cache_db, 'source_hash', lambda: 'HASH-2')
    stale, problems = check_artifacts()
    assert stale and any('a --' in p and 'results changed' in p for p in problems), problems


def test_rebuilding_only_one_artifact_flags_the_other(cache, monkeypatch):
    """Exactly what running a single precompute job looks like."""
    write_artifact('fresh', {'x': 1})
    write_artifact('stale', {'x': 2})
    monkeypatch.setattr(cache_db, 'source_hash', lambda: 'HASH-2')
    write_artifact('fresh', {'x': 1})
    stale, problems = check_artifacts()
    assert stale
    assert any(p.startswith('stale ') for p in problems) and not any(p.startswith('fresh ') for p in problems)


def test_externally_sourced_artifacts_are_exempt(cache):
    """The tournament hosts come from ihsaa.org; a Track.db hash says nothing."""
    write_artifact('a', {'x': 1})
    tournament_hosts.save_all({})
    assert check_artifacts() == (False, [])


def test_next_seasons_results_do_not_make_this_season_stale(cache, monkeypatch):
    """A 2027 load must leave the 2026 reports alone, or everyone learns to
    ignore the check. The fingerprints stand in for the database."""
    hashes = {(2026, 'Boys'): 'H-2026', (2027, 'Boys'): 'H-2027-before'}
    monkeypatch.setattr(artifacts_module, 'season_fingerprint', lambda y, g, db_path=None: hashes[(y, g)])
    write_artifact('a_2026', {'x': 1}, year=2026, gender='Boys')
    write_artifact('a_2027', {'x': 2}, year=2027, gender='Boys')
    assert check_artifacts() == (False, [])

    hashes[(2027, 'Boys')] = 'H-2027-after'
    stale, problems = check_artifacts()
    assert stale
    assert any(p.startswith('a_2027') for p in problems)
    assert not any(p.startswith('a_2026') for p in problems)


def test_correcting_an_old_season_flags_only_that_season_and_gender(cache, monkeypatch):
    hashes = {(2026, 'Boys'): 'B', (2026, 'Girls'): 'G', (2027, 'Boys'): 'B27'}
    monkeypatch.setattr(artifacts_module, 'season_fingerprint', lambda y, g, db_path=None: hashes[(y, g)])
    for (year, gender) in hashes:
        write_artifact('r_%s_%s' % (year, gender), {'x': 1}, year=year, gender=gender)
    hashes[(2026, 'Girls')] = 'G-corrected'
    stale, problems = check_artifacts()
    assert stale and len(problems) == 1
    assert problems[0].startswith('r_2026_Girls') and '2026 Girls results changed' in problems[0]


# ------------------------------------------- the real fingerprint, real data

def test_the_season_fingerprint_is_stable_across_calls():
    """Unstable row order would make every check report a false change."""
    from app.jobs.artifacts import season_fingerprint, _SCOPE_CACHE
    _SCOPE_CACHE.clear()
    first = season_fingerprint(2026, 'Boys')
    _SCOPE_CACHE.clear()
    second = season_fingerprint(2026, 'Boys')
    assert first and first == second


def test_different_seasons_and_genders_hash_differently():
    from app.jobs.artifacts import season_fingerprint
    seen = {(year, gender): season_fingerprint(year, gender)
            for year in (2025, 2026) for gender in ('Boys', 'Girls')}
    assert len(set(seen.values())) == len(seen), seen
