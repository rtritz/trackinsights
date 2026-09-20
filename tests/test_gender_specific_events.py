"""The gender-conditional paths, which had no data to run against.

The fixture was Boys-only, so every branch that asks "is this the girls' side?"
was dead in the test suite -- including the hurdle lists, which are the one place
the two genders genuinely run different events: 100 Hurdles for girls, 110 for
boys, and 300 Hurdles for both.

These also cover ``_get_all_sectional_events_list`` and ``_get_sectional_events``
directly. Those two used to be written defensively around a ``CONST`` that could
not actually be absent, and were rewritten to read it straight; this is what
says the rewrite kept their output the same.
"""
import pytest

from common.const import CONST


def test_girls_event_list_has_the_girls_hurdle_and_not_the_boys_one(app):
    from app.queries.shared import _get_all_sectional_events_list

    with app.app_context():
        events = _get_all_sectional_events_list(CONST.GENDER.GIRLS)

    assert CONST.EVENT.E100H in events, '100 Hurdles is the girls\' hurdle'
    assert CONST.EVENT.E110H not in events, '110 Hurdles is the boys\' race'
    assert CONST.EVENT.E300H in events, '300 Hurdles is run by both'


def test_boys_event_list_has_the_boys_hurdle_and_not_the_girls_one(app):
    from app.queries.shared import _get_all_sectional_events_list

    with app.app_context():
        events = _get_all_sectional_events_list(CONST.GENDER.BOYS)

    assert CONST.EVENT.E110H in events
    assert CONST.EVENT.E100H not in events
    assert CONST.EVENT.E300H in events


@pytest.mark.parametrize('gender', CONST.GENDER.ALL)
def test_every_track_and_field_event_appears_once(app, gender):
    from app.queries.shared import _get_all_sectional_events_list

    with app.app_context():
        events = _get_all_sectional_events_list(gender)

    assert len(events) == len(set(events)), 'an event is listed twice'
    for event in list(CONST.EVENT.ALL_TRACK) + list(CONST.EVENT.ALL_FIELD):
        assert event in events, '%s missing for %s' % (event, gender)


def test_the_combined_event_list_covers_both_genders_hurdles(app):
    """_get_sectional_events is the union -- the trends tool offers them all."""
    from app.queries.shared import _get_sectional_events

    with app.app_context():
        events = _get_sectional_events()

    assert CONST.EVENT.E100H in events
    assert CONST.EVENT.E110H in events
    assert len(events) == len(set(events))


def test_trend_options_offer_both_genders(app):
    from app.queries import get_sectional_event_trends_options

    with app.app_context():
        options = get_sectional_event_trends_options()

    assert options['genders'] == list(CONST.GENDER.ALL)
    assert CONST.EVENT.E100H in options['events']


def test_a_girls_athlete_dashboard_renders(client):
    """Athlete 111 runs the 100 Hurdles -- a girls-only event."""
    response = client.get('/athlete-dashboard/111')
    assert response.status_code == 200
    assert b'Maya' in response.data


def test_the_api_answers_for_a_girls_athlete(client):
    response = client.get('/api/athletes/111/dashboard')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['athlete']['gender'] == CONST.GENDER.GIRLS


def test_percentiles_can_be_asked_for_the_girls_hurdle(client):
    response = client.get('/api/percentiles?events=100+Hurdles&genders=Girls')
    assert response.status_code == 200
    assert 'rows' in response.get_json()


def test_search_finds_a_girls_athlete(client):
    response = client.get('/api/search?q=Maya')
    assert response.status_code == 200
    names = [row.get('name', '') for row in response.get_json()]
    assert any('Maya' in name for name in names), names
