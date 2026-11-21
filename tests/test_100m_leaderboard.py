def test_100m_leaderboard_shows_best_marks_and_meet_level(client):
    response = client.get('/100m')

    assert response.status_code == 200
    assert b'Boys 100m - Track Insights' in response.data
    assert b'>Boys 100m</h1>' in response.data
    assert b'id="filters-heading"' not in response.data
    assert b'10.60' in response.data
    assert b'Sectional' in response.data
    assert b'Regional' in response.data
    assert b'State' in response.data
    assert b'aria-label="100 Meters leaderboard"' in response.data
    assert b"px-3 sm:px-6 font-sans" in response.data
    assert b"divide-gray-300/70" in response.data
    assert b'class="leaderboard-desktop overflow-x-auto"' in response.data
    assert b'@media (min-width: 64rem)' in response.data


def test_gender_event_pages_are_separate_and_only_show_their_gender(client):
    boys = client.get('/events/boys/100m')
    girls = client.get('/events/girls/100m?gender=Boys')

    assert boys.status_code == 200
    assert girls.status_code == 200
    assert b'>Boys 100m</h1>' in boys.data
    assert b'>Girls 100m</h1>' in girls.data
    assert b'data-gender="Boys"' in boys.data
    assert b'data-gender="Girls"' in girls.data
    assert b'id="filters-heading"' not in boys.data
    assert b'id="filters-heading"' not in girls.data
    assert client.get('/events/boys/100h').status_code == 404
    assert client.get('/events/girls/110h').status_code == 404
    assert client.get('/events/girls/100h').status_code == 200
    assert client.get('/events/boys/110h').status_code == 200


def test_100m_leaderboard_filters_by_gender_level_and_season(client):
    response = client.get('/100m?gender=Boys&meet_type=State&year=2024')

    assert response.status_code == 200
    assert b'10.85' in response.data
    table_rows = response.data.split(b'<tbody>', 1)[1].split(b'</tbody>', 1)[0]
    assert b'State' in table_rows
    assert b'Regional' not in table_rows
    assert b'Sectional' not in table_rows


def test_100m_leaderboard_ignores_invalid_filter_values(client):
    response = client.get('/100m?gender=Unknown&meet_type=Invalid&year=not-a-year')

    assert response.status_code == 200
    assert b'Boys' in response.data
    assert b'All seasons' in response.data


def test_100m_dashboard_includes_analytics_without_the_top_list_panels(client):
    response = client.get('/100m?gender=Boys')

    assert response.status_code == 200
    assert b'Performance Distribution' in response.data
    assert b'25th' in response.data
    assert b'50th' in response.data
    assert b'75th' in response.data
    assert b'Cutoffs' in response.data
    assert b'Event Trends' in response.data
    assert b'data-trend="Sectional"' in response.data
    assert b'data-trend="Regional"' in response.data
    assert b'data-trend="State"' in response.data
    assert b'Previous season' not in response.data
    assert b'All-time' not in response.data
    assert b'event-distribution-chart' in response.data
    assert b'event-trend-chart' in response.data


def test_100m_dashboard_analytics_uses_five_year_window_and_actual_advancement_marks(client, app):
    from app.queries.event_ranking import get_100m_dashboard_analytics

    with app.app_context():
        analytics = get_100m_dashboard_analytics('Boys')

    assert analytics['window'] == [2023, 2024]
    assert analytics['percentiles'][1]['label'] == '50th'
    assert analytics['percentiles'][1]['value'] == 10.75
    assert analytics['percentiles'][1]['display'] == '10.75'
    assert analytics['advancement_ranges']['Regional'] is None
    state_benchmark = analytics['advancement_ranges']['State']
    assert state_benchmark['low'] == 10.8
    assert state_benchmark['high'] == 10.8
    assert state_benchmark['count'] == 1
    assert state_benchmark['low_display'] == '10.80'
    assert analytics['trend']['years'] == [2023, 2024]
    assert analytics['trend']['datasets'][0]['data'] == [10.95, 10.7]
    assert analytics['trend']['datasets'][2]['data'] == [None, 10.85]


def test_event_distribution_respects_selected_meet_level_and_season(app):
    from app.queries.event_ranking import get_event_dashboard_analytics

    with app.app_context():
        all_results = get_event_dashboard_analytics('100 Meters', 'Boys')
        regional_results = get_event_dashboard_analytics(
            '100 Meters', 'Boys', meet_type='Regional'
        )
        state_results = get_event_dashboard_analytics(
            '100 Meters', 'Boys', meet_type='State'
        )
        season_results = get_event_dashboard_analytics(
            '100 Meters', 'Boys', year=2023
        )
        state_season_results = get_event_dashboard_analytics(
            '100 Meters', 'Boys', meet_type='State', year=2024
        )

    assert sum(all_results['distribution']['counts']) == 6
    assert sum(regional_results['distribution']['counts']) == 2
    assert sum(state_results['distribution']['counts']) == 1
    assert sum(season_results['distribution']['counts']) == 2
    assert season_results['window'] == [2023]
    assert sum(state_season_results['distribution']['counts']) == 1
    assert state_season_results['window'] == [2024]
    assert state_season_results['percentiles'][1]['value'] == 10.85
    assert all_results['trend'] == state_season_results['trend']


def test_event_dashboard_passes_selected_filters_to_distribution(client):
    import json

    all_results = client.get('/100m')
    selected_results = client.get('/100m?meet_type=State&year=2024')

    def distribution(response):
        chart_data = response.data.split(b'id="event-chart-data">', 1)[1]
        chart_data = chart_data.split(b'</script>', 1)[0]
        return json.loads(chart_data)['distribution']

    assert sum(distribution(all_results)['counts']) == 6
    assert sum(distribution(selected_results)['counts']) == 1
    assert b'State' in selected_results.data
    assert b'2024' in selected_results.data


def test_distribution_dropdowns_fetch_filtered_chart_and_percentiles(client):
    page = client.get('/100m?gender=Boys&meet_type=State&year=2024')
    assert b'id="distribution-meet-type"' in page.data
    assert b'id="distribution-season"' in page.data
    assert b'data-url="/api/events/100m/distribution"' in page.data

    response = client.get('/api/events/100m/distribution?gender=Boys&meet_type=State&year=2024')
    assert response.status_code == 200
    data = response.get_json()
    assert sum(data['distribution']['counts']) == 1
    assert data['percentiles'][1]['value'] == 10.85
    assert data['lowerIsBetter'] is True

    all_meets = client.get('/api/events/100m/distribution?gender=Boys&meet_type=All&year=All')
    assert sum(all_meets.get_json()['distribution']['counts']) == 6
    empty = client.get('/api/events/100m/distribution?gender=Boys&meet_type=State&year=2023')
    assert empty.status_code == 200
    assert empty.get_json()['distribution']['labels'] == []
    assert empty.get_json()['percentiles'] == []
    assert b'id="event-distribution-chart"' in client.get('/100m?meet_type=State&year=2023').data
    assert client.get('/api/events/not-an-event/distribution').status_code == 404
    assert client.get('/api/events/100m/distribution?year=invalid').status_code == 400


def test_leaderboard_dropdowns_fetch_filtered_rows_and_count(client):
    page = client.get('/100m')
    assert b'id="leaderboard-meet-type"' in page.data
    assert b'id="leaderboard-season"' in page.data
    assert b'data-url="/api/events/100m/leaderboard"' in page.data

    state = client.get('/api/events/100m/leaderboard?gender=Boys&meet_type=State&year=2024')
    assert state.status_code == 200
    data = state.get_json()
    assert data['countLabel'] == '1 mark'
    assert '10.85' in data['html']
    assert 'Regional' not in data['html']

    empty = client.get('/api/events/100m/leaderboard?gender=Boys&meet_type=State&year=2023')
    assert empty.status_code == 200
    assert empty.get_json()['countLabel'] == '0 marks'
    assert 'No marks match those filters yet.' in empty.get_json()['html']

    relay = client.get('/api/events/4x100/leaderboard?gender=Boys&meet_type=Sectional&year=2024')
    assert relay.status_code == 200
    assert 'Relay members' in relay.get_json()['html']
    assert 'relay' in relay.get_json()['countLabel']
    assert client.get('/api/events/not-an-event/leaderboard').status_code == 404
    assert client.get('/api/events/100m/leaderboard?year=invalid').status_code == 400


def test_relay_leaderboards_show_school_lineup_and_respect_filters(client, app):
    import json

    response = client.get('/4x100?gender=Boys&meet_type=Sectional&year=2024')
    assert response.status_code == 200
    assert b'Alpha High' in response.data
    assert b'A. Sprinter, B. Sprinter, C. Curve, D. Jumper' in response.data
    assert b'A Sprinter, B Sprinter, C Curve, D Jumper' not in response.data
    assert b'43.00' in response.data
    assert b'42.80' not in response.data
    assert b'Relay members' in response.data

    chart_data = response.data.split(b'id="event-chart-data">', 1)[1]
    chart_data = chart_data.split(b'</script>', 1)[0]
    analytics = json.loads(chart_data)
    assert sum(analytics['distribution']['counts']) == 3

    girls_relay = client.get('/4x400?gender=Girls&meet_type=Sectional&year=2024')
    assert girls_relay.status_code == 200
    assert b'4:05.00' in girls_relay.data

    with app.app_context():
        from app.queries.event_ranking import get_event_leaderboard

        results = get_event_leaderboard(
            '4 x 100 Relay', 'Boys', meet_type='Regional', year=2024
        )
    assert len(results) == 1
    assert results[0]['result'].school.school_name == 'Alpha High'


def test_all_requested_event_dashboard_routes_render(client):
    event_pages = (
        ('/200m', '200 Meters'),
        ('/400m', '400 Meters'),
        ('/800m', '800 Meters'),
        ('/1600m', '1600 Meters'),
        ('/3200m', '3200 Meters'),
        ('/100h', '100 Hurdles'),
        ('/110h', '110 Hurdles'),
        ('/300h', '300 Hurdles'),
        ('/4x100', '4x100 Relay'),
        ('/4x400', '4x400 Relay'),
        ('/4x800', '4x800 Relay'),
        ('/shot-put', 'Shot Put'),
        ('/discus', 'Discus'),
        ('/pole-vault', 'Pole Vault'),
        ('/high-jump', 'High Jump'),
        ('/long-jump', 'Long Jump'),
    )

    for path, event_name in event_pages:
        response = client.get(path)

        assert response.status_code == 200
        assert event_name.encode() in response.data
        assert b' Leaderboard</h1>' not in response.data
        assert b'aria-label="Event dashboards"' not in response.data
        assert b'Performance Distribution' in response.data
        assert b'Event Trends' in response.data


def test_search_returns_matching_event_dashboards(client):
    shot_put = client.get('/api/search?q=shot%20put').get_json()
    compact_hurdles = client.get('/api/search?q=110h').get_json()
    relay = client.get('/api/search?q=4x100%20relay').get_json()
    existing_athlete = client.get('/api/search?q=Maya').get_json()

    assert shot_put[0] == {
        'type': 'event',
        'id': 'boys-shot-put',
        'name': 'Boys Shot Put',
        'url': '/events/boys/shot-put',
    }
    assert shot_put[1]['name'] == 'Girls Shot Put'
    hundred = client.get('/api/search?q=100m').get_json()
    girls_hundred = client.get('/api/search?q=Girls%20100m').get_json()
    assert [item['url'] for item in hundred if item['type'] == 'event'] == [
        '/events/boys/100m', '/events/girls/100m',
    ]
    assert [item['url'] for item in girls_hundred if item['type'] == 'event'] == [
        '/events/girls/100m',
    ]
    assert compact_hurdles[0]['type'] == 'event'
    assert compact_hurdles[0]['url'] == '/events/boys/110h'
    assert relay[0]['type'] == 'event'
    assert relay[0]['url'] == '/events/boys/4x100'
    assert any(item['type'] == 'athlete' and item['name'] == 'Maya Hurdle'
               for item in existing_athlete)


def test_homepage_links_to_every_event_dashboard(client):
    from app.event_dashboards import EVENT_DASHBOARDS

    response = client.get('/')

    assert response.status_code == 200
    for page in EVENT_DASHBOARDS:
        for gender in page['genders']:
            path = f"/events/{gender.lower()}/{page['slug']}"
            assert f'href="{path}"'.encode() in response.data
    assert b'Boys 100m Dash' in response.data
    assert b'Girls 100m Dash' in response.data


def test_event_dashboard_gender_defaults_and_track_filters(client):
    hurdles = client.get('/100h')
    filtered = client.get('/200m?gender=Boys&meet_type=Sectional&year=2024')

    assert hurdles.status_code == 200
    assert b'Girls 100 Hurdles' in hurdles.data
    assert b'15.20' in hurdles.data
    assert filtered.status_code == 200
    table_rows = filtered.data.split(b'<tbody>', 1)[1].split(b'</tbody>', 1)[0]
    assert b'22.00' in table_rows
    assert b'22.40' not in table_rows


def test_long_distance_distribution_uses_minutes_and_seconds(app):
    from app.queries.event_ranking import get_event_dashboard_analytics

    with app.app_context():
        long_distance = get_event_dashboard_analytics('3200 Meters', 'Boys')
        sprint = get_event_dashboard_analytics('100 Meters', 'Boys')

    assert long_distance['distribution_uses_minutes'] is True
    assert all(':' in label for label in long_distance['distribution']['labels'])
    assert len(long_distance['distribution']['labels']) <= 17
    assert sprint['distribution_uses_minutes'] is False
    assert all(':' not in label for label in sprint['distribution']['labels'])


def test_field_event_leaderboard_ranks_larger_marks_first(client, app):
    from app import db
    from app.models import Athlete, AthleteResult
    from app.queries.event_ranking import get_event_dashboard_analytics, get_event_leaderboard

    with app.app_context():
        db.session.add(Athlete(
            athlete_id=901,
            first='Riley',
            last='Thrower',
            school_id=1,
            gender='Girls',
            graduation_year=2027,
        ))
        db.session.add(AthleteResult(
            athlete_id=901,
            meet_id=14,
            event='Shot Put',
            result_type='Final',
            result='35\'0"',
            result2=420.0,
            place=2,
            grade='SO',
        ))
        db.session.commit()

        results = get_event_leaderboard('Shot Put', 'Girls')
        analytics = get_event_dashboard_analytics('Shot Put', 'Girls')

    assert [entry['result'].athlete_id for entry in results[:2]] == [901, 113]
    assert analytics['event_type'] == 'Field'
    assert analytics['lower_is_better'] is False
    assert analytics['percentiles'][1]['display'] == '34\'7"'
    assert analytics['advancement_ranges']['Regional']['low_display'] == '34\'2"'
