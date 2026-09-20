"""The v4 dashboard: the payload it prepares, and the cache it is served from.

These cover the parts that decide what a reader sees -- which entries count as
near misses, how names are printed, and whether a stale cache is noticed -- since
the page itself is now just a lookup and a render.
"""
import json
import sqlite3

import pytest

from app.services import dashboard_v4 as svc


# ------------------------------------------------------------------ payload

def test_build_payload_has_every_section(app):
    with app.app_context():
        payload = svc.build_payload(1, "Boys", "2024")

    assert payload is not None
    for key in ("school", "filters", "overview", "regional", "state", "rank",
                "outlook", "results"):
        assert key in payload, key
    assert payload["school"]["name"] == "Alpha High"
    assert payload["filters"]["selected_season"] == "2024"


def test_payload_marks_whether_state_and_regional_have_anything(app):
    """The tab strip is built from these, so an empty tab never appears."""
    with app.app_context():
        payload = svc.build_payload(1, "Boys", "2024")
    assert isinstance(payload["has_state"], bool)
    assert isinstance(payload["has_regional"], bool)
    assert payload["has_state"] == bool(payload["state"]["qualifiers"])


def test_all_time_has_no_season_only_sections(app):
    """All-time is a records board: qualifying and next season mean nothing."""
    with app.app_context():
        payload = svc.build_payload(1, "Boys", "all-time")
    assert payload["rank"] is None
    assert payload["regional"]["qualifiers"] == []
    assert payload["state"]["qualifiers"] == []


# -------------------------------------------------------------- near misses

def _row(share, cutoff=100.0, name="X"):
    return {"final_stage": "Sectional", "gap_value": share * cutoff,
            "cutoff_value": cutoff, "name": name, "athlete_id": 1,
            "event": "100 Meters", "entry_type": "individual",
            "gap_display": "0.1", "cutoff_display": "10.0", "cutoff_path": "auto"}


def test_just_missed_orders_by_share_not_raw_gap():
    """A raw gap is not comparable across events; the share is what orders."""
    rows = [_row(0.02, cutoff=600.0, name="distance"),   # big raw gap, close
            _row(0.01, cutoff=11.0, name="sprint")]      # small raw gap, closer
    out = svc._just_missed(rows)
    assert [r["name"] for r in out][:2] == ["Sprint", "Distance"]


def test_just_missed_keeps_everyone_inside_the_threshold_up_to_the_cap():
    rows = [_row(0.001 * i) for i in range(1, 21)]  # 20 entries, all within 3%
    out = svc._just_missed(rows)
    assert len(out) == svc.CLOSEST_MAX
    assert all(not r["far"] for r in out)


def test_just_missed_fills_to_the_floor_and_flags_the_padding():
    """Nobody close is exactly when "who came nearest" is asked -- so the list
    still fills, but the rows past the line say so."""
    rows = [_row(0.01), _row(0.40), _row(0.50), _row(0.60)]
    out = svc._just_missed(rows)
    assert len(out) == svc.CLOSEST_MIN
    assert [r["far"] for r in out] == [False, True, True]


def test_just_missed_ignores_entries_that_advanced():
    assert svc._just_missed([dict(_row(0.01), final_stage="Regional")]) == []


# --------------------------------------------------------------------- names

@pytest.mark.parametrize("stored,shown", [
    ("AARON SPRINTER", "Aaron Sprinter"),
    ("MCDONALD", "McDonald"),          # Mc takes a capital after it
    ("MACIAS", "Macias"),              # Mac does not -- it is an ordinary name
    ("O'BRIEN", "O'Brien"),            # one letter before the apostrophe
    ("SMITH-JONES", "Smith-Jones"),
    ("DARIN BROOKS JR", "Darin Brooks Jr"),
    ("WILLIAM PIERCE III", "William Pierce III"),
])
def test_person_names_are_printed_not_shouted(stored, shown):
    assert svc._person_name(stored) == shown


def test_relays_are_named_relay_not_by_their_school():
    row = {"entry_type": "relay", "athlete_id": None, "name": "Alpha High"}
    assert svc._display_name(row) == "Relay"


# --------------------------------------------------------------------- cache

def test_cache_round_trips_through_compression(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "CACHE_DB_PATH", str(tmp_path / "cache.db"))
    payload = {"school": {"name": "Alpha High"}, "results": {"rows": [1, 2, 3]}}
    svc.write_cache([(1, "Boys", "2024", svc._encode(payload))], source_size=123)

    assert svc.load_payload(1, "Boys", "2024") == payload
    assert svc.load_payload(1, "Girls", "2024") is None
    assert svc.load_payload(99, "Boys", "2024") is None


def test_cache_reads_an_uncompressed_payload(tmp_path, monkeypatch):
    """Caches written before compression must keep working."""
    monkeypatch.setattr(svc, "CACHE_DB_PATH", str(tmp_path / "cache.db"))
    payload = {"school": {"name": "Alpha High"}}
    svc.write_cache([(1, "Boys", "2024", json.dumps(payload))], source_size=1)
    assert svc.load_payload(1, "Boys", "2024") == payload


def test_missing_cache_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "CACHE_DB_PATH", str(tmp_path / "absent.db"))
    svc._hash_for.cache_clear()
    assert svc.load_payload(1, "Boys", "2024") is None
    assert svc.cache_status()["built"] is False


def test_cache_notices_the_results_changing(tmp_path, monkeypatch):
    """The case a size check misses: a correction that leaves the file the same
    size. The stored hash is what catches it."""
    monkeypatch.setattr(svc, "CACHE_DB_PATH", str(tmp_path / "cache.db"))
    svc._hash_for.cache_clear()
    svc.write_cache([(1, "Boys", "2024", svc._encode({}))], source_size=svc.source_size())
    assert svc.cache_status()["stale"] is False

    conn = sqlite3.connect(str(tmp_path / "cache.db"))
    conn.execute("UPDATE meta SET value='not-the-current-hash' WHERE key='source_hash'")
    conn.commit()
    conn.close()
    assert svc.cache_status()["stale"] is True


# ------------------------------------------------- the development-only fallback

def test_production_never_builds_a_dashboard_live(app, client):
    """A missing cache must stay a missing cache on the deployed site.

    The cache exists because this analysis took seconds per page, and the deploy
    host measured 15-25x slower than a development machine. A fallback that
    switched itself on in production would restore that, silently, under load.
    """
    assert not app.debug, 'the fixture app must look like production here'
    assert not svc.allow_live_build(app)

    response = client.get('/school-dashboard-v4/1')
    assert response.status_code == 200
    assert b'Computed live for this request' not in response.data


def test_debug_mode_allows_a_live_build(app):
    app.debug = True
    try:
        assert svc.allow_live_build(app)
    finally:
        app.debug = False


def test_an_explicit_opt_in_allows_a_live_build(app, monkeypatch):
    """For running a production-shaped config locally without debug on."""
    assert not svc.allow_live_build(app)
    monkeypatch.setenv('TI_LIVE_DASHBOARD', '1')
    assert svc.allow_live_build(app)


def test_a_live_build_produces_the_same_shape_as_the_cache(app):
    """Whatever the page renders, it is the same payload either way.

    live_payload calls build_payload -- the function the precompute job uses --
    so a locally built dashboard cannot drift from a deployed one in content,
    only in how long it took to produce.
    """
    with app.app_context():
        live = svc.live_payload(1, 'Boys', '2024')
        direct = svc.build_payload(1, 'Boys', '2024')
    assert live is not None
    assert set(live) == set(direct)
    assert live['school'] == direct['school']


def test_live_payload_finds_a_season_without_consulting_the_cache(app):
    """The season list has to come from the database.

    season_choices() answers from dashboard_cache.db, so it returns nothing on a
    fresh clone -- precisely when the fallback is needed. live_seasons() reads
    the same source the precompute job does instead.
    """
    with app.app_context():
        seasons = svc.live_seasons(1, 'Boys')
        assert seasons, 'no seasons found in the database'
        assert seasons[-1] == 'all-time'
        assert seasons[:-1] == sorted(seasons[:-1], reverse=True), 'newest first'
        assert svc.live_payload(1, 'Boys') is not None


def test_live_payload_does_not_read_the_cache_at_all(app, monkeypatch):
    """Independent of the cache, not merely tolerant of it."""
    def boom(*args, **kwargs):
        raise AssertionError('live_payload must not read the cache')

    monkeypatch.setattr(svc, 'load_payload', boom)
    monkeypatch.setattr(svc, 'season_choices', boom)
    with app.app_context():
        assert svc.live_payload(1, 'Boys', '2024') is not None


def test_live_payload_returns_none_for_a_school_with_nothing(app):
    with app.app_context():
        assert svc.live_payload(99999, 'Boys', '2024') is None
