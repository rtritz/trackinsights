"""Contract tests against the isolated fixture database, never Track.db."""

import json

import pytest
from jinja2 import ChoiceLoader, DictLoader

from app import db
from app.models import Athlete, AthleteResult, Meet, RelayResult, School
from app.services import school_page as service

original_load_rankings = service._load_rankings


@pytest.fixture(autouse=True)
def rankings(monkeypatch):
    tables = {
        ('Boys', '2024', ''): {'rows': [
            {'rank': 1, 'school_id': 3, 'value': 88.0},
            {'rank': 2, 'school_id': 1, 'value': 75.0},
        ]},
        ('Boys', '2023', ''): {'rows': [{'rank': 3, 'school_id': 1, 'value': 50.0}]},
        ('Boys', '2024', '100 Meters'): {'rows': [
            {'rank': 1, 'athlete_id': 301, 'school_id': 3, 'name': 'Grant', 'mark': '10.60'},
            {'rank': 2, 'athlete_id': 102, 'school_id': 1, 'name': 'Blake', 'mark': '10.70'},
            {'rank': 2, 'athlete_id': 201, 'school_id': 2, 'name': 'Brent', 'mark': '10.70'},
            {'rank': 4, 'athlete_id': 101, 'school_id': 1, 'name': 'Aaron', 'mark': '10.80'},
        ]},
        ('Boys', '2023', '100 Meters'): {'rows': [
            {'rank': 1, 'athlete_id': 101, 'school_id': 1, 'name': 'Aaron', 'mark': '11.00'},
        ]},
        ('Boys', '2024', 'High Jump'): {'rows': [
            {'rank': 1, 'athlete_id': 104, 'school_id': 1, 'name': 'Dylan', 'mark': "6'0\""},
            {'rank': 2, 'athlete_id': 202, 'school_id': 2, 'name': 'Cole', 'mark': "5'10\""},
        ]},
    }
    monkeypatch.setattr(service, '_load_rankings',
                        lambda gender, season, event='': tables.get((gender, str(season), event)))
    return tables


@pytest.fixture()
def template(app):
    app.jinja_loader = ChoiceLoader([DictLoader({
        'school-page.html': '{{ {"id": school_id, "payload": payload}|tojson }}'
    }), app.jinja_loader])


def event(payload, name):
    return next(e for e in payload['events'] if e['name'] == name)


def field_sizes(monkeypatch, regional=16, state=30):
    """Shrink the advancement fields so the tiny fixture pools can fill them.

    `regional` is the field filled from the sectionals; `state` from the regionals.
    """
    monkeypatch.setattr(service, '_field_size',
                        lambda stage, year: regional if stage == 'Sectional' else state)


def test_routes_default_explicit_validation_and_missing_school(client, template):
    response = client.get('/school-dashboard/1')
    assert response.status_code == 200
    body = json.loads(response.data)
    assert body['id'] == 1
    assert (body['payload']['gender'], body['payload']['season']) == ('Boys', '2024')
    assert client.get('/school-dashboard/1/Girls/2024').status_code == 200
    assert client.get('/school-dashboard/1/Girls/2023').status_code == 200
    assert client.get('/school-dashboard/1/Boys/all-time').status_code == 200
    for path in ('/school-dashboard/1/Other/2024', '/school-dashboard/1/Boys/2022',
                 '/school-dashboard/1/Boys/banana'):
        assert client.get(path).status_code == 400
    assert client.get('/school-dashboard/9999').status_code == 404
    assert client.get('/school-dashboard/9999/Boys/2024').status_code == 404


def test_result_units_history_and_records(app):
    payload = service.build_payload(1, 'Boys', '2024')
    assert payload['years'] == [2024, 2023]
    assert payload['latest_year'] == 2024
    # 4 individual athlete-events and one relay, independent of rounds/meets.
    assert payload['summary']['result_units'] == 5
    assert payload['summary']['regional_entries'] == 3
    assert payload['summary']['state_entries'] == 1
    assert payload['summary']['athletes'] == 4
    assert payload['summary']['rank']['rank'] == 2
    assert [r['rank'] for r in payload['summary']['top_performers']] == [4, 1, 2]
    all_time = service.build_payload(1, 'Boys', 'all-time')
    assert all_time['summary']['result_units'] == 8
    assert [h['year'] for h in all_time['history']] == [2024, 2023]
    assert [h['result_units'] for h in all_time['history']] == [5, 3]
    record = next(b for b in all_time['bests'] if b['event'] == '100 Meters')
    assert [(e['athlete_id'], e['year'], e['value']) for e in record['entries']] == [(102, 2024, 10.7)]
    assert all_time['summary']['rank'] is None
    assert all_time['outlook']['year'] == 2024
    assert all_time['outlook']['roster']


def test_event_distribution_ranks_and_actual_cutoffs(app, monkeypatch):
    field_sizes(monkeypatch, regional=4, state=2)
    payload = service.build_payload(1, 'Boys', 2024)
    sprint = event(payload, '100 Meters')
    jump = event(payload, 'High Jump')
    assert [r['value'] for r in sprint['distribution']['marks']] == [10.6, 10.7, 10.7, 10.8]
    assert [r['rank'] for r in sprint['entries']] == [2, 4]
    # Sectional: 3 automatic + 1 spot; Aaron's 10.90 meets the 11.23 standard,
    # so the standard fills it and is the cut. Regional: 2 automatic fill a
    # field of 2, so only the standard remains.
    assert sprint['regional_cutoff'][0]['value'] == 11.23
    assert sprint['regional_cutoff'][0]['path'] == 'standard'
    assert sprint['state_cutoff'][0]['value'] == 11.23
    # Two high jumpers, both automatic, cannot fill a field of 4: no cut.
    assert jump['regional_cutoff'] == []
    assert jump['state_cutoff'] == []
    assert jump['unit'] == 'inches'
    assert [r['value'] for r in jump['distribution']['marks']] == [72, 70]
    assert event(payload, '200 Meters')['distribution']['missing_years'] == [2024]
    assert not event(payload, '200 Meters')['distribution']['complete']
    all_time = event(service.build_payload(1, 'Boys', 'all-time'), '100 Meters')
    assert len(all_time['distribution']['marks']) == 4
    assert all(r['rank'] is None for r in all_time['distribution']['marks'])


def test_roster_counts_missing_grades_and_no_mark_entries(app):
    db.session.add(Athlete(athlete_id=114, first='Unknown', last='Grade', school_id=1,
                           gender='Girls', graduation_year=2026))
    db.session.add(AthleteResult(athlete_id=114, meet_id=14, event='200 Meters',
                                 result_type='Final', result='DNF', result2=9999, grade=None))
    db.session.commit()
    payload = service.build_payload(1, 'Girls', '2024')
    assert payload['summary']['result_units'] == 5
    assert payload['summary']['athletes'] == 4
    assert payload['outlook']['returning_count'] == 2
    assert payload['outlook']['graduating_count'] == 1
    assert payload['outlook']['unknown_count'] == 1
    assert all(p['athlete_id'] != 114 for p in payload['performances'])
    assert event(payload, '100 Hurdles')['entries']
    assert all(e['name'] != '110 Hurdles' for e in payload['events'])


def test_empty_school_and_gender_consistency(app):
    db.session.add(School(school_id=99, school_name='Empty'))
    # A bad cross-gender meet must not introduce a Boys year.
    db.session.add(Meet(meet_id=99, year=2025, gender='Girls', meet_type='Sectional'))
    db.session.add(AthleteResult(athlete_id=101, meet_id=99, event='100 Meters',
                                 result_type='Final', result='10.1', result2=10.1))
    db.session.commit()
    assert service.build_payload(1)['years'] == [2025, 2024, 2023]
    payload = service.build_payload(99)
    assert payload['season'] == 'all-time' and payload['latest_year'] is None
    assert payload['summary']['result_units'] == 0
    assert [h['year'] for h in payload['history']] == [2025, 2024, 2023]
    assert all(h['result_units'] == 0 for h in payload['history'])


def test_relays_and_partial_cache_are_not_silently_complete(app, rankings):
    rankings[('Boys', '2024', '4 x 100 Relay')] = {'rows': [
        {'rank': 1, 'school_id': 1, 'athlete_id': None, 'name': 'Relay', 'mark': '42.80'},
        {'rank': 2, 'school_id': 3, 'athlete_id': None, 'name': 'Relay', 'mark': '42.90'},
        {'rank': 3, 'school_id': 2, 'athlete_id': None, 'name': 'Relay', 'mark': 'not a mark'},
    ]}
    relay = event(service.build_payload(1, 'Boys', 2024), '4 x 100 Relay')
    assert len(relay['entries']) == 1 and relay['entries'][0]['rank'] == 1
    assert [r['value'] for r in relay['distribution']['marks']] == [42.8, 42.9]
    assert relay['distribution']['skipped_rows'] == 1
    assert not relay['distribution']['complete']
    # Three relays, all automatic, cannot fill a 16-team regional: every
    # finalist advanced, so there is no cut to show.
    assert relay['regional_cutoff'] == []


def test_latest_incomplete_season_is_not_replaced_by_last_state_meet(app):
    db.session.add(Meet(meet_id=99, year=2025, gender='Boys', meet_type='Sectional', meet_num=1))
    db.session.add(RelayResult(school_id=1, meet_id=99, event='4 x 100 Relay',
                               result='42.00', result2=42, place=1))
    db.session.commit()
    payload = service.build_payload(1)
    assert payload['season'] == '2025'
    assert payload['years'] == [2025, 2024, 2023]
    assert payload['summary']['result_units'] == 1


def test_rounds_with_no_results_statewide_show_as_pending_not_zero(app, client):
    # 2025 has Sectional results only: Regional and State are pending, so the
    # page says so instead of "0 qualifiers". Complete seasons have none pending.
    db.session.add(Meet(meet_id=99, year=2025, gender='Boys', meet_type='Sectional', meet_num=1))
    db.session.add(RelayResult(school_id=1, meet_id=99, event='4 x 100 Relay',
                               result='42.00', result2=42, place=1))
    db.session.commit()
    payload = service.build_payload(1, 'Boys', '2025')
    assert payload['summary']['pending'] == ['Regional', 'State']
    assert service.build_payload(1, 'Boys', '2024')['summary']['pending'] == []
    page = client.get('/school-dashboard/1/Boys/2025').get_data(as_text=True)
    assert page.count('Results not in yet') >= 2 and "Regional results aren't in yet." in page
    assert 'None this season' not in page


def test_a_team_with_no_results_yet_this_season_is_all_pending(app, client):
    # Between the girls' and boys' sectionals: girls have 2025 results, boys
    # none yet, so every boys round is pending and the page says only that.
    db.session.add(Meet(meet_id=99, year=2025, gender='Girls', meet_type='Sectional', meet_num=1))
    db.session.add(RelayResult(school_id=1, meet_id=99, event='4 x 100 Relay',
                               result='48.00', result2=48, place=1))
    db.session.commit()
    # Either gender's first result makes the season current.
    from app.queries import current_season
    current_season.cache_clear()
    assert current_season() == 2025
    assert service._pending_stages('Boys', 2025) == ['Sectional', 'Regional', 'State']
    assert 'Sectional' not in service._pending_stages('Boys', 2024)
    page = client.get('/school-dashboard/1/Boys/2025').get_data(as_text=True)
    assert '2025 playoff results are pending.' in page and page.count('Results not in yet') == 4
    assert 'no boys entries' not in page and 'Top Statewide Marks' not in page


def test_cache_not_used_for_another_database(app, monkeypatch):
    def forbidden(*args):
        raise AssertionError('production cache was read for a fixture database')
    monkeypatch.setattr(service.cache_db, 'load_rankings', forbidden)
    assert original_load_rankings('Boys', 2024, '100 Meters') is None


def test_regional_cut_is_the_last_fill_spot_in_the_feeder_pool(app, monkeypatch):
    # 2027 has no 3 Participant Standard, so the fill alone sets the cut.
    # Sectionals 1 and 2 feed Regional 1; sectional 5 feeds Regional 2.
    # A field of 3 with one automatic qualifier leaves 2 fill spots.
    field_sizes(monkeypatch, regional=3)
    db.session.add_all([
        Meet(meet_id=90, year=2027, gender='Boys', meet_type='Sectional', meet_num=1),
        Meet(meet_id=91, year=2027, gender='Boys', meet_type='Sectional', meet_num=2),
        Meet(meet_id=92, year=2027, gender='Boys', meet_type='Sectional', meet_num=5),
        Meet(meet_id=93, year=2027, gender='Boys', meet_type='Regional', meet_num=1),
        Meet(meet_id=94, year=2027, gender='Boys', meet_type='Regional', meet_num=2),
    ] + [Athlete(athlete_id=i, first='Pool', last=str(i), gender='Boys', school_id=2) for i in range(901, 906)])
    result = lambda athlete, meet, value, place, kind='Final': AthleteResult(  # noqa: E731
        athlete_id=athlete, meet_id=meet, event='100 Meters', result_type=kind,
        result=f'{value:.2f}', result2=value, place=place)
    db.session.add_all([
        result(101, 90, 11.50, 5),          # ours: third-best non-automatic mark
        result(201, 90, 10.90, 1),          # automatic top 3: takes a spot, never the cut
        result(902, 91, 11.10, 5),          # best fill mark, from a sibling sectional
        result(901, 91, 11.20, 4),          # second fill mark: the cut
        result(903, 92, 11.00, 4),          # other regional's pool: ignored
        result(905, 91, 11.05, 4, 'Prelim'),  # prelim mark: ignored
    ])
    db.session.commit()
    payload = service.build_payload(1, 'Boys', 2027)
    cutoff = event(payload, '100 Meters')['regional_cutoff'][0]
    assert (cutoff['meet_id'], cutoff['value'], cutoff['place'], cutoff['path']) == (90, 11.2, 4, 'fill')
    ours = next(r for r in payload['results']['rows'] if r.get('athlete_id') == 101)
    assert ours['gap_value'] == pytest.approx(.3) and ours['gap_stage'] == 'Regional'


def test_summary_places_team_points_and_qualifier_details(app):
    db.session.add(AthleteResult(athlete_id=102, meet_id=6, event='100 Meters',
                                 result_type='Final', result='10.75', result2=10.75, place=9, grade='SR'))
    db.session.commit()
    summary = service.build_payload(1, 'Boys', 2024)['summary']
    assert summary['sectional_team'] == {'meet_id': 4, 'rank': 1, 'total_teams': 3, 'points': 40.0}
    assert summary['sectional_placers'] == 5
    assert summary['regional_entries'] == 3 and summary['regional_placers'] == 3
    assert summary['state_entries'] == 2 and summary['state_placers'] == 1
    details = summary['qualifier_details']['State']
    assert [(r['name'], r['place'], r['prelim'], r['placer']) for r in details] == [
        ('Aaron Sprinter', 5, True, False), ('Blake Sprinter', 9, False, True)]
    assert summary['sentence'] == '1 state medalist'


def test_covered_seasons_no_school_participation_and_gender_filters(app, client, template):
    db.session.add(Meet(meet_id=99, year=2025, gender='Boys', meet_type='Sectional', meet_num=1))
    db.session.commit()
    payload = service.build_payload(1, 'Boys', 2025)
    assert payload['years'] == [2025, 2024, 2023]
    assert payload['season'] == '2025' and payload['summary']['result_units'] == 0
    assert payload['summary']['sectional_team'] is None
    assert payload['outlook']['year'] == 2024
    assert json.loads(client.get('/school-dashboard/1/Boys/2025').data)['payload']['season'] == '2025'
    assert service.build_payload(1, 'Girls', '2024')['gender'] == 'Girls'


def test_scorecard_cells_rank_and_cache_only(app, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('live statewide ranking was computed')
    monkeypatch.setattr(service.scorecard, '_event_mark_ranks', forbidden)
    monkeypatch.setattr(service.scorecard, '_relay_mark_ranks', forbidden)
    payload = service.build_payload(1, 'Boys', 'all-time')
    row = next(r for r in payload['results']['rows'] if r['year'] == 2024 and r.get('athlete_id') == 101 and r['event'] == '100 Meters')
    assert row['rank'] == 4 and row['rank_total'] == 4
    assert row['final_stage'] == 'State'
    assert row['stages']['State']['round'] == 'Prelim'
    assert row['stages']['Regional']['place'] == 3
    assert {'gap', 'gap_value', 'cutoff_value'} <= row.keys()
    assert payload['data']['event_cache_issues'] and not payload['data']['complete']
    assert next(e for e in payload['performances'] if e['athlete_id'] == 101 and e['year'] == 2024)['prelim']
    assert any(r['entry_type'] == 'none' for r in payload['results']['rows'])


def test_missing_result_value_is_not_silently_removed_from_scorecard(app):
    db.session.add(AthleteResult(athlete_id=103, meet_id=5, event='200 Meters',
                                 result_type='Final', result='DNF', result2=None, place=None, grade='SR'))
    db.session.commit()
    result = service.build_payload(1, 'Boys', 2024)
    row = next(r for r in result['results']['rows'] if r.get('athlete_id') == 103 and r['event'] == '200 Meters')
    assert row['final_stage'] == 'Regional'
    assert row['stages']['Regional']['mark_display'] == 'DNF'
    assert row['stages']['Regional']['has_mark'] is False


def test_result_gaps_use_chart_cutoffs_and_furthest_actual_stage(app, monkeypatch):
    # Without standards, the single fill spot (3 automatic in a field of 4)
    # goes to the best non-automatic final mark: Aaron, 4th in 10.90.
    standards = service._STATE_STANDARD_VALUES
    monkeypatch.setattr(service, '_STATE_STANDARD_VALUES', {})
    field_sizes(monkeypatch, regional=4, state=4)
    db.session.add_all([
        Athlete(athlete_id=901, first='Near', last='Miss', gender='Boys', school_id=1),
        Athlete(athlete_id=902, first='Far', last='Miss', gender='Boys', school_id=1),
        Athlete(athlete_id=903, first='No', last='Mark', gender='Boys', school_id=1),
        AthleteResult(athlete_id=901, meet_id=4, event='100 Meters', result_type='Prelim', result='11.00', result2=11.0, place=10),
        AthleteResult(athlete_id=902, meet_id=4, event='100 Meters', result_type='Final', result='12.00', result2=12.0, place=11),
        AthleteResult(athlete_id=903, meet_id=4, event='100 Meters', result_type='Final', result='DQ', result2=9999, place=None),
    ])
    db.session.commit()
    payload = service.build_payload(1, 'Boys', 2024)
    rows = {r['athlete_id']: r for r in payload['results']['rows'] if r.get('athlete_id') in (101, 102, 901, 902, 903)}
    regional_cut = event(payload, '100 Meters')['regional_cutoff'][0]
    assert regional_cut['value'] == 10.9 and regional_cut['path'] == 'fill'
    # Two regional finalists cannot fill a State field of 4: no State cut.
    assert event(payload, '100 Meters')['state_cutoff'] == []
    assert rows[901]['stages']['Sectional']['round'] == 'Prelim'
    assert rows[901]['cutoff_value'] == regional_cut['value']
    assert rows[901]['gap_value'] == pytest.approx(.1)
    assert rows[901]['gap'] == '0.10s'
    assert rows[901]['gap_stage'] == 'Regional'
    assert rows[902]['gap_value'] == pytest.approx(1.1)
    assert rows[902]['gap_display'] == '1.10s'
    assert rows[902]['gap_stage'] == 'Regional'
    assert rows[903]['gap_value'] is None and rows[903]['cutoff_value'] is None
    assert rows[102]['final_stage'] == 'Regional'
    assert rows[102]['cutoff_value'] is None and rows[102]['gap_value'] is None
    assert rows[101]['final_stage'] == 'State'
    assert rows[101]['gap_value'] is None  # no ninth-place final in this event
    assert rows[101]['cutoff_value'] is None
    assert next(r for r in payload['results']['rows'] if r.get('athlete_id') == 103)['gap_value'] is None
    all_time = service.build_payload(1, 'Boys', 'all-time')
    prior = next(r for r in all_time['results']['rows'] if r['year'] == 2023 and r.get('athlete_id') == 101)
    assert prior['gap_value'] is None  # 2023 has no observed regional entrant
    # With the 2024 standard (11.23) back, the 11.00 prelim beat the cut: it is
    # reported, but there is no "short by" for a mark that met it.
    monkeypatch.setattr(service, '_STATE_STANDARD_VALUES', standards)
    rows = {r['athlete_id']: r for r in service.build_payload(1, 'Boys', 2024)['results']['rows']
            if r.get('athlete_id') in (901, 902)}
    assert rows[901]['cutoff_value'] == 11.23 and rows[901]['gap_value'] is None
    assert rows[902]['gap_value'] == pytest.approx(.77)


def test_marks_at_state_get_no_gap(app):
    # The gap measures qualifying only (Regional, State). A mark at State has
    # nothing further to qualify for -- not even a top-9 place -- so no gap.
    db.session.add_all([
        Athlete(athlete_id=901, first='Ninth', last='Other', gender='Boys', school_id=2),
        AthleteResult(athlete_id=901, meet_id=6, event='100 Meters', result_type='Final', result='10.70', result2=10.7, place=9),
        AthleteResult(athlete_id=901, meet_id=6, event='100 Meters', result_type='Prelim', result='9.00', result2=9, place=9),
        AthleteResult(athlete_id=901, meet_id=6, event='High Jump', result_type='Final', result="6'2\"", result2=74, place=9),
        AthleteResult(athlete_id=104, meet_id=6, event='High Jump', result_type='Final', result="6'0\"", result2=72, place=10),
        RelayResult(school_id=2, meet_id=6, event='4 x 100 Relay', result='42.00', result2=42, place=9),
        RelayResult(school_id=1, meet_id=6, event='4 x 100 Relay', result='43.00', result2=43, place=12),
    ])
    db.session.commit()
    payload = service.build_payload(1, 'Boys', 2024)
    rows = payload['results']['rows']
    sprint = next(r for r in rows if r.get('athlete_id') == 101 and r['event'] == '100 Meters')
    jump = next(r for r in rows if r.get('athlete_id') == 104 and r['event'] == 'High Jump')
    relay = next(r for r in rows if r['event'] == '4 x 100 Relay' and r['entry_type'] == 'relay')
    assert sprint['stages']['State']['round'] == 'Prelim'
    for row in (sprint, jump, relay):
        assert row['final_stage'] == 'State'
        assert row['gap_value'] is None and row['gap_display'] is None and row['gap_stage'] is None


def test_cutoffs_are_matched_to_each_source_meet_and_year(app, monkeypatch):
    # Each sectional here is alone in its regional's pool: 1 automatic + 1 fill.
    field_sizes(monkeypatch, regional=2)
    db.session.add_all([
        Meet(meet_id=90, year=2027, gender='Boys', meet_type='Sectional', meet_num=1),
        Meet(meet_id=91, year=2027, gender='Boys', meet_type='Sectional', meet_num=5),
        Meet(meet_id=92, year=2027, gender='Boys', meet_type='Regional', meet_num=1),
        Meet(meet_id=93, year=2027, gender='Boys', meet_type='Regional', meet_num=2),
        Athlete(athlete_id=905, first='Wild', last='One', gender='Boys', school_id=2),
        Athlete(athlete_id=906, first='Wild', last='Two', gender='Boys', school_id=3),
        AthleteResult(athlete_id=101, meet_id=90, event='100 Meters', result_type='Final', result='11.50', result2=11.5, place=5),
        AthleteResult(athlete_id=102, meet_id=91, event='100 Meters', result_type='Final', result='12.50', result2=12.5, place=5),
        AthleteResult(athlete_id=201, meet_id=90, event='100 Meters', result_type='Final', result='11.00', result2=11, place=3),
        AthleteResult(athlete_id=201, meet_id=92, event='100 Meters', result_type='Final', result='11.10', result2=11.1, place=3),
        AthleteResult(athlete_id=301, meet_id=91, event='100 Meters', result_type='Final', result='12.00', result2=12, place=3),
        AthleteResult(athlete_id=301, meet_id=93, event='100 Meters', result_type='Final', result='12.10', result2=12.1, place=3),
        # The best non-automatic mark in each pool takes its one fill spot.
        AthleteResult(athlete_id=905, meet_id=90, event='100 Meters', result_type='Final', result='11.20', result2=11.2, place=4),
        AthleteResult(athlete_id=905, meet_id=92, event='100 Meters', result_type='Final', result='11.30', result2=11.3, place=8),
        AthleteResult(athlete_id=906, meet_id=91, event='100 Meters', result_type='Final', result='12.20', result2=12.2, place=4),
        AthleteResult(athlete_id=906, meet_id=93, event='100 Meters', result_type='Final', result='12.30', result2=12.3, place=8),
    ])
    db.session.commit()
    payload = service.build_payload(1, 'Boys', 2027)
    assert {c['meet_id']: c['value'] for c in event(payload, '100 Meters')['regional_cutoff']} == {90: 11.2, 91: 12.2}
    for selected in (payload, service.build_payload(1, 'Boys', 'all-time')):
        rows = [r for r in selected['results']['rows'] if r['year'] == 2027 and r.get('athlete_id') in (101, 102)]
        assert {r['athlete_id']: r['cutoff_value'] for r in rows} == {101: 11.2, 102: 12.2}
        assert all(r['gap_value'] == pytest.approx(.3) and r['gap_display'] == '0.30s' for r in rows)


def test_field_cutoff_and_missing_state_ninth_are_not_fabricated(app, monkeypatch):
    # One State spot, no automatic jumper: the best non-automatic height (5'10")
    # fills it; that is easier than the 6'6" standard, so it is the cut.
    field_sizes(monkeypatch, state=1)
    db.session.add_all([
        AthleteResult(athlete_id=201, meet_id=5, event='High Jump', result_type='Final', result="5'10\"", result2=70, place=4),
        AthleteResult(athlete_id=201, meet_id=6, event='High Jump', result_type='Final', result="5'10\"", result2=70, place=10),
        AthleteResult(athlete_id=104, meet_id=5, event='High Jump', result_type='Final', result="5'8\"", result2=68, place=8),
        # A prelim at ninth and a final in eighth do not establish ninth place.
        AthleteResult(athlete_id=301, meet_id=6, event='100 Meters', result_type='Prelim', result='10.70', result2=10.7, place=9),
        AthleteResult(athlete_id=301, meet_id=6, event='100 Meters', result_type='Final', result='10.70', result2=10.7, place=8),
    ])
    db.session.commit()
    payload = service.build_payload(1, 'Boys', 2024)
    jump = next(r for r in payload['results']['rows'] if r.get('athlete_id') == 104 and r['event'] == 'High Jump')
    assert jump['cutoff_value'] == event(payload, 'High Jump')['state_cutoff'][0]['value'] == 70
    assert jump['gap_value'] == 2 and jump['gap_display'] == '2"'
    sprint = next(r for r in payload['results']['rows'] if r.get('athlete_id') == 101 and r['event'] == '100 Meters')
    assert sprint['gap_value'] is None and sprint['cutoff_value'] is None


def test_state_invalid_ninth_and_unknown_final_place_leave_gap_absent(app):
    db.session.add_all([
        AthleteResult(athlete_id=201, meet_id=6, event='100 Meters', result_type='Final', result='DQ', result2=9999, place=9),
        AthleteResult(athlete_id=102, meet_id=6, event='100 Meters', result_type='Final', result='10.80', result2=10.8, place=None),
    ])
    db.session.commit()
    payload = service.build_payload(1, 'Boys', 2024)
    rows = {r['athlete_id']: r for r in payload['results']['rows'] if r.get('athlete_id') in (101, 102)}
    assert all(rows[athlete]['gap_value'] is None for athlete in rows)
    # Even with a valid ninth, a final without a place is not known to be a non-placer.
    ninth = AthleteResult.query.filter_by(athlete_id=201, meet_id=6, event='100 Meters', result_type='Final').one()
    ninth.result, ninth.result2 = '10.70', 10.7
    db.session.commit()
    rows = service.build_payload(1, 'Boys', 2024)['results']['rows']
    unknown = next(r for r in rows if r.get('athlete_id') == 102 and r['event'] == '100 Meters')
    assert unknown['gap_value'] is None and unknown['cutoff_value'] is None


def test_outlook_is_latest_and_lists_qualifying_returners_and_graduates(app):
    result = AthleteResult.query.filter_by(athlete_id=102, meet_id=5, event='100 Meters').one()
    result.grade = 'JR'
    AthleteResult.query.filter_by(athlete_id=102, meet_id=4, event='100 Meters').one().grade = 'JR'
    db.session.commit()
    outlook = service.build_payload(1, 'Boys', 2023)['outlook']
    assert outlook['year'] == 2024
    assert [r['name'] for r in outlook['regional_returners']] == ['Blake Sprinter']
    assert outlook['regional_returners'][0]['regional_events'] == ['100 Meters']
    assert [r['name'] for r in outlook['state_graduating']] == ['Aaron Sprinter']


def test_top_performers_annual_percentile_dedup_and_all_time_half(app, rankings):
    rankings[('Boys', '2023', '100 Meters')]['rows'] = [
        {'rank': 1, 'athlete_id': 101, 'school_id': 1, 'mark': '11.00'}]
    rankings[('Boys', '2024', '4 x 100 Relay')] = {'rows': [
        {'rank': 1, 'athlete_id': None, 'school_id': 1, 'mark': '42.80'}]}
    annual = service.build_payload(1, 'Boys', 2024)['summary']['top_performers']
    assert annual[0]['athlete_id'] == 101 and annual[0]['prelim']
    assert annual[0]['percentile'] == .25
    all_time = service.build_payload(1, 'Boys', 'all-time')['summary']['top_performers']
    # All-time ranks compare each athlete's best mark with every athlete's best
    # across seasons. Aaron's best is 10.80 (2024), 4th of 4 all-time -- even
    # though his 2023 11.00 was 1st that season.
    aaron = [r for r in all_time if r['athlete_id'] == 101]
    assert len(aaron) == 1 and aaron[0]['year'] == 2024
    assert (aaron[0]['all_time_rank'], aaron[0]['all_time_total']) == (4, 4)
    blake = next(r for r in all_time if r['athlete_id'] == 102)
    assert blake['all_time_rank'] == 2  # 10.70, behind only Grant's 10.60
    order = [r['all_time_percentile'] for r in all_time]
    assert order == sorted(order, reverse=True)
    assert any(r['is_relay'] for r in all_time)
    assert len(all_time) <= 10


def test_mapped_regional_without_school_qualifier_and_unknown_standard_year(app, monkeypatch):
    # The 2 automatic regional qualifiers fill a State field of 2, leaving the standard.
    field_sizes(monkeypatch, state=2)
    db.session.add_all([
        Meet(meet_id=91, year=2027, gender='Boys', meet_type='Sectional', meet_num=1),
        Meet(meet_id=92, year=2027, gender='Boys', meet_type='Regional', meet_num=1),
        RelayResult(school_id=2, meet_id=91, event='4 x 100 Relay', result='44.00', result2=44, place=1),
    ])
    db.session.commit()
    mapped = event(service.build_payload(2, 'Boys', 2024), '100 Meters')
    assert mapped['state_cutoff'][0]['meet_id'] == 5
    assert mapped['state_cutoff'][0]['path'] == 'standard'
    unknown = event(service.build_payload(2, 'Boys', 2027), '100 Meters')
    assert unknown['state_cutoff'] == []


def test_all_events_have_bests_and_history_has_absent_years(app):
    payload = service.build_payload(1, 'Girls', 'all-time')
    assert len(payload['bests']) == len(payload['events'])
    assert next(b for b in payload['bests'] if b['event'] == 'Pole Vault')['entries'] == []
    assert all('sectional_team' in h and 'rank_cache_missing' in h for h in payload['history'])
    assert payload['data']['program_missing_years'] == [2024, 2023]


def test_tied_team_scoring_and_cache_mismatch_are_explicit(app, rankings):
    rankings[('Girls', '2024', '100 Meters')] = {'rows': [
        {'rank': 1, 'athlete_id': 112, 'school_id': 1, 'mark': '12.30'}]}
    payload = service.build_payload(1, 'Girls', 2024)
    assert payload['summary']['sectional_team']['points'] == 33.0
    nina = next(e for e in payload['performances'] if e['athlete_id'] == 112)
    assert nina['rank'] is None
    assert any(e['athlete_id'] == 112 for e in payload['data']['unmatched_entries'])


def test_state_placer_before_qualifier_before_other_performances(app, rankings):
    db.session.add(AthleteResult(athlete_id=102, meet_id=6, event='100 Meters',
                                 result_type='Final', result='10.75', result2=10.75, place=9, grade='SR'))
    db.session.commit()
    rankings[('Boys', '2024', '4 x 100 Relay')] = {'rows': [
        {'rank': 1, 'athlete_id': None, 'school_id': 1, 'mark': '42.80'}]}
    top = service.build_payload(1, 'Boys', 2024)['summary']['top_performers']
    assert [r['athlete_id'] for r in top[:2]] == [102, 101]
    assert top[0]['place'] == 9 and not top[0]['prelim']
    assert top[1]['place'] == 5 and top[1]['prelim']
    assert top[2]['percentile'] == 1


def test_state_cut_uses_fill_mark_when_easier_than_standard(app, monkeypatch):
    field_sizes(monkeypatch, state=1)
    db.session.add_all([
        AthleteResult(athlete_id=201, meet_id=5, event='High Jump', result_type='Final',
                      result="5'10\"", result2=70, place=4),
        AthleteResult(athlete_id=201, meet_id=6, event='High Jump', result_type='Final',
                      result="5'10\"", result2=70, place=10),
    ])
    db.session.commit()
    # Nobody met the 6'6" standard, so the 5'10" fill mark is the cut.
    cutoff = event(service.build_payload(1, 'Boys', 2024), 'High Jump')['state_cutoff'][0]
    assert cutoff['value'] == 70 and cutoff['place'] == 4 and cutoff['path'] == 'fill'


def test_top_three_finishers_never_set_the_cut(app, monkeypatch):
    # 3rd place advances automatically, however slow; only at-large marks count.
    monkeypatch.setattr(service, '_STATE_STANDARD_VALUES', {})
    db.session.add_all([
        AthleteResult(athlete_id=201, meet_id=5, event='High Jump', result_type='Final',
                      result="5'0\"", result2=60, place=3),
        AthleteResult(athlete_id=201, meet_id=6, event='High Jump', result_type='Final',
                      result="5'0\"", result2=60, place=12),
    ])
    db.session.commit()
    assert event(service.build_payload(1, 'Boys', 2024), 'High Jump')['state_cutoff'] == []

def test_prelim_marks_count_for_records_but_finals_decide_places(app):
    # Blake ran 10.55 in the 2024 sectional prelims and 10.70 (2nd) in the final.
    db.session.add(AthleteResult(athlete_id=102, meet_id=4, event='100 Meters', result_type='Prelim',
                                 result='10.55', result2=10.55, place=1, grade='SR'))
    # Chris's regional 200m final is a DQ, but his prelim was a valid 22.10.
    db.session.add_all([
        AthleteResult(athlete_id=103, meet_id=5, event='200 Meters', result_type='Prelim',
                      result='22.10', result2=22.1, place=2, grade='SR'),
        AthleteResult(athlete_id=103, meet_id=5, event='200 Meters', result_type='Final',
                      result='DQ', result2=9999, place=None, grade='SR'),
    ])
    db.session.commit()
    all_time = service.build_payload(1, 'Boys', 'all-time')
    record = next(b for b in all_time['bests'] if b['event'] == '100 Meters')['entries'][0]
    assert (record['athlete_id'], record['value'], record['mark_prelim']) == (102, 10.55, True)
    # At the regional, the DQ'd final still decides the result row, but the
    # valid 22.10 prelim survives as his best mark there.
    rows, _ = service._school_rows(1, 'Boys')
    regional = next(r for r in rows if r['athlete_id'] == 103 and r['meet_id'] == 5 and r['event'] == '200 Meters')
    assert regional['result_type'] == 'Final' and (regional['best_value'], regional['best_round']) == (22.1, 'Prelim')
    # The sectional cell still shows the final: 10.70, 2nd.
    season = service.build_payload(1, 'Boys', 2024)
    blake = next(r for r in season['results']['rows'] if r.get('athlete_id') == 102 and r['event'] == '100 Meters')
    assert blake['stages']['Sectional']['round'] == 'Final' and blake['stages']['Sectional']['place'] == 2


def test_shared_resolver_best_of_rounds(app):
    from app.queries.shared import _resolve_postseason_individual_rows
    db.session.add(AthleteResult(athlete_id=102, meet_id=4, event='100 Meters', result_type='Prelim',
                                 result='10.55', result2=10.55, place=1))
    db.session.commit()
    pick = lambda **kw: next(r for r in _resolve_postseason_individual_rows(gender='Boys', year=2024, **kw)  # noqa: E731
                             if r['athlete_id'] == 102 and r['meet_id'] == 4 and r['event'] == '100 Meters')
    assert pick()['result_value'] == 10.7                      # default: the final
    assert pick(best_of_rounds=True)['result_value'] == 10.55  # rankings: the best round


def test_all_time_list_matches_the_all_time_ranks_on_cards(app, client, rankings):
    # Every athlete's best across 2023-2024, competition-ranked: Aaron's best is
    # his 2024 10.80 (not his 2023 11.00), so he is 4th behind a tie for 2nd.
    payload = service.all_time_rankings('Boys', '100 Meters')
    assert [(r['athlete_id'], r['rank'], r['mark'], r['year']) for r in payload['rows']] == [
        (301, 1, '10.60', 2024), (102, 2, '10.70', 2024), (201, 2, '10.70', 2024), (101, 4, '10.80', 2024)]
    cards = service.build_payload(1, 'Boys', 'all-time')['summary']['top_performers']
    aaron = next(r for r in cards if r['athlete_id'] == 101)
    assert (aaron['all_time_rank'], aaron['all_time_total']) == (4, len(payload['rows']))
    # Grade is the athlete's grade in the season of that best mark.
    season_grades = {r['athlete_id']: r.get('grade') for r in service._load_rankings('Boys', 2024, '100 Meters')['rows']}
    assert all(r['grade'] == season_grades[r['athlete_id']] for r in payload['rows'])
    response = client.get('/api/rankings/Boys/all-time?event=100%20Meters')
    assert response.status_code == 200 and response.get_json()['rows'][0]['rank'] == 1
    assert service.all_time_rankings('Boys', 'Not An Event') is None


def test_size_group_rank_splits_at_the_median_and_shares_ties():
    ranking = {'rows': [
        {'rank': 1, 'school_id': 10, 'enrollment': 3000},
        {'rank': 2, 'school_id': 11, 'enrollment': 300},
        {'rank': 3, 'school_id': 12, 'enrollment': 400},
        {'rank': 3, 'school_id': 13, 'enrollment': 350},
        {'rank': 5, 'school_id': 14, 'enrollment': 2000},
        {'rank': 6, 'school_id': 15, 'enrollment': 450},
        {'rank': 7, 'school_id': 16, 'enrollment': None},   # unknown size: in no group
    ]}
    # Enrollments 300, 350, 400, 450, 2000, 3000 -> median 425.
    small = service._size_group_rank(ranking, 13)
    assert small == {'group': 'small', 'split': 425, 'rank': 2, 'of': 3}   # tied 3rd overall, 2nd of 3 small
    assert service._size_group_rank(ranking, 14)['rank'] == 2              # behind the 3000 school
    assert service._size_group_rank(ranking, 16) is None
    assert service._size_group_rank(None, 13) is None


def _normalized(payload):
    return json.loads(json.dumps(payload, sort_keys=True, default=str))


def test_stored_pages_restore_to_the_live_page(app, tmp_path, monkeypatch):
    monkeypatch.setattr(service.cache_db, 'CACHE_DB_PATH', str(tmp_path / 'cache.db'))
    monkeypatch.setattr(service, '_use_stored_pages', lambda: True)
    live = {view: service.build_payload(1, 'Boys', view, with_results=view != 'all-time') for view in ('2024', 'all-time')}
    service.write_school_pages(
        [(1, 'Boys', view, service.cache_db.encode(service.slim_payload(p))) for view, p in live.items()],
        ['2024', 'all-time'])
    # A season page comes back whole: the statewide curves are restored, and the
    # parts covering every season come from All-Time (whose history also carries
    # other seasons' team finishes, which a season page does not show).
    stored, charts = service.page_data(1, 'Boys', '2024')
    assert _normalized(stored) == _normalized(dict(live['2024'], history=live['all-time']['history']))
    assert charts == service.chart_events(live['2024']['events'])
    # A bare URL resolves to the school's latest season, as build_payload does.
    assert service.page_data(1, 'Boys', None)[0]['season'] == '2024'
    # All-Time draws no curves, so they are not restored there.
    all_time, charts = service.page_data(1, 'Boys', 'all-time')
    assert charts == [] and all_time['summary'] == _normalized(live['all-time'])['summary']


def test_a_stored_season_page_learns_about_newer_seasons_from_all_time(app, tmp_path, monkeypatch):
    """A build refreshes only the current season and All-Time. An older season's
    stored page must still offer the new season in its picker and history."""
    monkeypatch.setattr(service.cache_db, 'CACHE_DB_PATH', str(tmp_path / 'cache.db'))
    monkeypatch.setattr(service, '_use_stored_pages', lambda: True)
    old = dict(service.build_payload(1, 'Boys', '2024'), years=[2024], latest_year=2024)
    newer = dict(service.build_payload(1, 'Boys', 'all-time', with_results=False),
                 years=[2025, 2024], latest_year=2025, history=[{'year': 2025}, {'year': 2024}],
                 bests=['newer'], outlook={'year': 2025})
    service.write_school_pages([(1, 'Boys', '2024', service.cache_db.encode(service.slim_payload(old))),
                                (1, 'Boys', 'all-time', service.cache_db.encode(service.slim_payload(newer)))],
                               ['2024', 'all-time'])
    page = service.page_data(1, 'Boys', '2024')[0]
    assert page['years'] == [2025, 2024] and page['latest_year'] == 2025
    assert page['history'] == newer['history'] and page['bests'] == ['newer'] and page['outlook'] == {'year': 2025}
    assert page['season'] == '2024' and page['summary'] == _normalized(old)['summary']   # its own season


def test_stored_pages_of_another_format_or_missing_build_live(app, tmp_path, monkeypatch):
    monkeypatch.setattr(service.cache_db, 'CACHE_DB_PATH', str(tmp_path / 'cache.db'))
    monkeypatch.setattr(service, '_use_stored_pages', lambda: True)
    fake = dict(service.build_payload(1, 'Boys', '2024'), marker='stored')
    service.write_school_pages([(1, 'Boys', '2024', service.cache_db.encode(service.slim_payload(fake)))], ['2024'])
    assert service.page_data(1, 'Boys', '2024')[0].get('marker') == 'stored'
    monkeypatch.setattr(service, 'PAGE_FORMAT', 'next')      # payload shape changed in code
    assert 'marker' not in service.page_data(1, 'Boys', '2024')[0]
    assert service.page_data(1, 'Girls', '2024')[0]['gender'] == 'Girls'   # never stored: built live
