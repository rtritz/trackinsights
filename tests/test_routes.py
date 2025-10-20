import pytest
from app import create_app
from backend import db
from config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TESTING = True
    SQLALCHEMY_ENGINE_OPTIONS = {'connect_args': {'check_same_thread': False}}


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        seed_reference_data()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_home_status(client):
    rv = client.get('/')
    assert rv.status_code == 200


def test_api_athletes(client):
    with client.application.app_context():
        athlete_id = seed_dashboard_data()
    rv = client.get('/api/athletes')
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data, list)
    assert any(item['id'] == athlete_id for item in data)


def test_search_bar_includes_gender_and_class_year(app):
    from backend.queries import search_bar
    with app.app_context():
        seed_dashboard_data()
        results = search_bar('UnitTest')
    athlete_result = next(item for item in results if item['type'] == 'athlete')
    assert athlete_result['gender'] == 'Boys'
    assert athlete_result['classYear'] == 2024


def test_dashboard_endpoint(client):
    with client.application.app_context():
        athlete_id = seed_dashboard_data()

    rv = client.get(f'/api/athletes/{athlete_id}/dashboard')
    assert rv.status_code == 200
    data = rv.get_json()

    assert data['athlete']['first'] == 'Test'
    assert data['athlete']['school'] == 'UnitTest High'
    assert data['athlete']['graduation_year'] == 2024

    sectional_badge = data['badges']['sectional']
    assert sectional_badge['stage'] == 'Sectional'
    assert pytest.approx(sectional_badge['best_percentile'], rel=1e-3) == 50.0

    regional_badge = data['badges']['regional']
    assert regional_badge['achievement'] == 'Placer'

    state_badge = data['badges']['state']
    assert state_badge['achievement'] == 'Qualifier'

    playoff_history = data['playoff_history']
    assert len(playoff_history) == 1
    row = playoff_history[0]
    assert row['year'] == 2024
    assert row['event'] == '400m'
    assert '1st' in row['sectional'] or '2nd' in row['sectional']
    assert '6th' in row['regional']
    assert row['state'] != '–'
    assert '10th' in row['state']


def seed_reference_data():
    from backend.models import Gender, MeetType, ResultType, EventType, Event, Grade

    for gender_value in ('Boys', 'Girls'):
        if not db.session.get(Gender, gender_value):
            db.session.add(Gender(gender=gender_value))

    for meet_type in ('Sectional', 'Regional', 'State'):
        if not db.session.get(MeetType, meet_type):
            db.session.add(MeetType(meet_type=meet_type))

    for result_type in ('Final', 'Prelim'):
        if not db.session.get(ResultType, result_type):
            db.session.add(ResultType(result_type=result_type))

    if not db.session.get(EventType, 'Track'):
        db.session.add(EventType(event_type='Track'))

    if not db.session.get(Event, '400m'):
        db.session.add(Event(event='400m', event_type='Track'))

    if not db.session.get(Grade, '12'):
        db.session.add(Grade(grade='12'))

    db.session.commit()


def seed_dashboard_data():
    from backend.models import (
        Athlete,
        School,
        Meet,
        AthleteResult,
    )

    # Ensure base data exists
    if not School.query.filter_by(school_name='UnitTest High').first():
        school = School(school_name='UnitTest High')
        db.session.add(school)
        db.session.flush()
    else:
        school = School.query.filter_by(school_name='UnitTest High').first()

    athlete = Athlete(
        first='Test',
        last='Athlete',
        gender='Boys',
        graduation_year=2024,
        school=school,
    )
    db.session.add(athlete)
    db.session.flush()

    # Additional athletes to fill out event placements
    others = []
    for idx in range(1, 4):
        other = Athlete(
            first=f'Other{idx}',
            last='Runner',
            gender='Boys',
            graduation_year=2024,
            school=school,
        )
        db.session.add(other)
        others.append(other)
    db.session.flush()

    sectional_meet = Meet(host='Sectional Host', meet_type='Sectional', meet_num=1, gender='Boys', year=2024)
    regional_meet = Meet(host='Regional Host', meet_type='Regional', meet_num=1, gender='Boys', year=2024)
    state_meet = Meet(host='State Host', meet_type='State', meet_num=1, gender='Boys', year=2024)
    db.session.add_all([sectional_meet, regional_meet, state_meet])
    db.session.flush()

    db.session.add_all([
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Final', grade='12', result='50.90', place=2),
        AthleteResult(athlete_id=others[0].athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Final', grade='12', result='50.10', place=1),
        AthleteResult(athlete_id=others[1].athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Final', grade='12', result='51.50', place=3),
        AthleteResult(athlete_id=others[2].athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Final', grade='12', result='52.00', place=4),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=regional_meet.meet_id, event='400m', result_type='Final', grade='12', result='51.02', place=6),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=state_meet.meet_id, event='400m', result_type='Final', grade='12', result='51.40', place=10),
    ])

    db.session.commit()
    return athlete.athlete_id
