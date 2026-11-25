import sqlite3

import pytest

from app.jobs import precompute_rankings as job
from app.queries.scorecard import _event_ranked_rows, _relay_ranked_rows
from common import cache_db


@pytest.mark.parametrize(('value', 'expected'), [
    ('2026', [2026]),
    (' 2023 - 2026 ', [2023, 2024, 2025, 2026]),
    ('2024-2024', [2024]),
])
def test_parse_seasons(value, expected):
    assert job.parse_seasons(value) == expected


@pytest.mark.parametrize('value', ['', '2026-2023', '2023,2024', '23', 'all'])
def test_parse_seasons_rejects_invalid_input(value):
    with pytest.raises(ValueError):
        job.parse_seasons(value)


def seed(tmp_path, monkeypatch, rankings=(), stamped=False):
    """An isolated cache holding the given ranking rows (gender, season, event, payload)."""
    monkeypatch.setattr(cache_db, 'CACHE_DB_PATH', str(tmp_path / 'cache.db'))
    conn = cache_db.connect(readonly=False)
    with conn:
        conn.executemany('INSERT INTO rankings VALUES (?, ?, ?, ?)',
                         [(g, s, e, cache_db.encode(p)) for g, s, e, p in rankings])
        if stamped:
            cache_db.stamp(conn)
    conn.close()


def test_selected_rankings_preserve_other_seasons(app, tmp_path, monkeypatch):
    old = {'old': True}
    seed(tmp_path, monkeypatch, [('Boys', '2023', '', old), ('Girls', '2023', '100 Meters', old),
                                 ('Boys', '2024', 'obsolete event', old)], stamped=True)
    previous_meta = cache_db.read_meta()
    calls = []

    def build(gender, season):
        calls.append((gender, season))
        return [('', {'gender': gender, 'kind': 'program'}),
                ('100 Meters', {'gender': gender, 'kind': 'event'})]

    monkeypatch.setattr(job, 'build_rankings', build)
    assert job.update_rankings([2024]) == 4
    assert calls == [('Boys', '2024'), ('Girls', '2024')]
    assert cache_db.load_rankings('Boys', '2023') == old
    assert cache_db.load_rankings('Girls', '2023', '100 Meters') == old
    assert cache_db.load_rankings('Boys', '2024', 'obsolete event') is None
    assert cache_db.load_rankings('Girls', '2024')['kind'] == 'program'
    assert cache_db.load_rankings('Boys', '2024', '100 Meters')['kind'] == 'event'
    # A partial update does not restamp the cache.
    assert cache_db.read_meta() == previous_meta


def test_build_failure_does_not_change_cache(app, tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch, [('Boys', '2024', '', {'old': True})])

    def build(gender, season):
        if gender == 'Girls':
            raise RuntimeError('failed')
        return [('', {'new': True})]

    monkeypatch.setattr(job, 'build_rankings', build)
    with pytest.raises(RuntimeError, match='failed'):
        job.update_rankings([2024])
    assert cache_db.load_rankings('Boys', '2024') == {'old': True}


def test_database_failure_rolls_back_all_changes(app, tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch, [('Boys', '2024', '', {'old': True})])
    monkeypatch.setattr(job, 'build_rankings', lambda gender, season: [
        ('', {'kind': 'program'}), ('', {'duplicate': True}),
    ])
    with pytest.raises(sqlite3.IntegrityError):
        job.update_rankings([2024])
    assert cache_db.load_rankings('Boys', '2024') == {'old': True}


def test_real_rankings_include_individual_relay_and_program(app, tmp_path, monkeypatch):
    monkeypatch.setattr(cache_db, 'CACHE_DB_PATH', str(tmp_path / 'cache.db'))
    _event_ranked_rows.cache_clear()
    _relay_ranked_rows.cache_clear()
    job.update_rankings([2024])
    assert cache_db.load_rankings('Boys', '2024')['rows']
    assert cache_db.load_rankings('Boys', '2024', '100 Meters')['rows']
    assert cache_db.load_rankings('Boys', '2024', '4 x 100 Relay')['rows']
    assert cache_db.load_rankings('Girls', '2024', '100 Hurdles')['rows']
    assert cache_db.cache_status()['built'] is False
    # Athlete lists carry each athlete's grade that season (the popup filters on
    # it); relays carry none.
    sprint = cache_db.load_rankings('Boys', '2024', '100 Meters')['rows']
    assert sprint and all(row['grade'] in ('FR', 'SO', 'JR', 'SR') for row in sprint)
    assert all(row['grade'] is None for row in cache_db.load_rankings('Boys', '2024', '4 x 100 Relay')['rows'])


def test_unknown_season_is_rejected_without_writing(app, tmp_path, monkeypatch):
    cache = tmp_path / 'cache.db'
    monkeypatch.setattr(cache_db, 'CACHE_DB_PATH', str(cache))
    with pytest.raises(ValueError, match='2099'):
        job.update_rankings([2099])
    assert not cache.exists()


def test_full_rebuild_stamps_the_cache_for_build_all_check(app, tmp_path, monkeypatch):
    # A full rebuild records the cache as built from this Track.db -- the
    # fingerprint `build_all --check` and the deploy script compare.
    seed(tmp_path, monkeypatch, [('Boys', '2024', '', {'old': True})])
    assert cache_db.cache_status()['built'] is False
    monkeypatch.setattr(job, 'build_rankings', lambda gender, season: [('', {'kind': 'program'})])
    job.update_rankings([2024], stamp=True)
    meta = cache_db.read_meta()
    assert meta['source_hash'] == cache_db.source_hash()
    assert meta['source_size'] == str(cache_db.source_size())
    assert cache_db.cache_status() == {'built': True, 'stale': False, 'generated_at': meta['generated_at']}


def test_build_all_builds_rankings_then_school_pages():
    from app.jobs import build_all
    names = [entry[0] for entry in build_all.JOBS]
    assert names.index('rankings') < names.index('school_pages')


def test_build_all_passes_the_chosen_seasons_to_every_job(monkeypatch):
    import sys
    import types
    from app.jobs import build_all
    calls = []
    fake = types.ModuleType('fake_job')
    fake.main = lambda years=None: calls.append(('main', years))
    fake.other = lambda years=None: calls.append(('other', years))
    monkeypatch.setitem(sys.modules, 'fake_job', fake)
    monkeypatch.setattr(build_all, 'JOBS', [('school_pages', 'fake_job'), ('rankings', 'fake_job', 'other'),
                                            ('state_qualifiers', 'fake_job')])
    monkeypatch.setattr(build_all, 'current_season', lambda: 2027)
    pruned = []
    monkeypatch.setattr(build_all, 'prune_old_seasons', pruned.append)
    assert build_all.build_all([2025, 2026]) == 0
    # School pages and rankings get the chosen seasons; the rest the current one.
    assert calls == [('main', [2025, 2026]), ('other', [2025, 2026]), ('main', [2027])]
    assert pruned == [2027]
    # Default is the newest season with results; --all is every one.
    monkeypatch.setattr(build_all, 'covered_seasons', lambda: [2024, 2025, 2026])
    assert build_all.resolve_seasons(['build_all']) == [2026]
    assert build_all.resolve_seasons(['build_all', '--all']) == [2024, 2025, 2026]
    assert build_all.resolve_seasons(['build_all', '--season', '2025']) == [2025]
    with pytest.raises(SystemExit):
        build_all.resolve_seasons(['build_all', '--season', '2019'])
