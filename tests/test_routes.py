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
    assert sectional_badge['achievement'] == 'Placer'
    assert sectional_badge['count'] == 3

    regional_badge = data['badges']['regional']
    assert regional_badge['achievement'] == 'Placer'
    assert regional_badge['count'] == 3

    state_badge = data['badges']['state']
    assert state_badge['achievement'] == 'Placer'
    assert state_badge['count'] == 2

    playoff_history = data['playoff_history']
    assert len(playoff_history) == 3
    row_400 = next(item for item in playoff_history if item['event'] == '400m')
    assert row_400['year'] == 2024
    assert '2nd' in row_400['sectional'] or '1st' in row_400['sectional']
    assert '6th' in row_400['regional']
    assert '10th' in row_400['state']

    personal_bests = data['personal_bests']
    assert len(personal_bests) == 3

    pb_400 = next(item for item in personal_bests if item['event'] == '400m')
    assert pb_400['event_type'] == 'Track'
    assert pb_400['result'] == '50.90'
    assert pb_400['meet_type'] == 'Sectional'
    assert pb_400['year'] == 2024
    assert isinstance(pb_400['meet_id'], int)
    assert pb_400['result_type'] == 'Final'
    assert pb_400['school_rank'] == {'rank': 1, 'total': 1, 'since_year': 2022}
    assert pb_400['state_rank'] == {'rank': 2, 'total': 4, 'since_year': 2022}

    pb_800 = next(item for item in personal_bests if item['event'] == '800m')
    assert pb_800['result'] == '1:55.20'
    assert pb_800['state_rank'] == {'rank': 1, 'total': 4, 'since_year': 2022}

    pb_lj = next(item for item in personal_bests if item['event'] == 'Long Jump')
    assert pb_lj['event_type'] == 'Field'
    assert pb_lj['state_rank'] == {'rank': 1, 'total': 4, 'since_year': 2022}


def test_result_rankings_endpoint(client):
    from backend.models import AthleteResult, Meet

    with client.application.app_context():
        athlete_id = seed_dashboard_data()
        sectional_result = (
            AthleteResult.query
            .join(Meet, AthleteResult.meet_id == Meet.meet_id)
            .filter(
                AthleteResult.athlete_id == athlete_id,
                AthleteResult.event == '400m',
                AthleteResult.result_type == 'Final',
                Meet.meet_type == 'Sectional',
            )
            .one()
        )

    rv = client.get(
        f'/api/athletes/{athlete_id}/result-rankings'
        f'?meet_id={sectional_result.meet_id}&event=400m&result_type=Final'
    )
    assert rv.status_code == 200
    payload = rv.get_json()

    assert payload['context'] == {
        'year': 2024,
        'gender': 'Boys',
        'event': '400m',
        'meet_type': 'Sectional',
        'result_type': 'Final',
        'event_type': 'Track',
    }

    overall = payload['rankings']['overall']
    assert overall['rank'] == 2
    assert overall['total'] == 4
    assert any(entry['is_target'] for entry in overall['top_results'])

    like_schools = payload['rankings']['like_schools']
    assert like_schools['rank'] == 2
    assert like_schools['total'] == 3
    assert like_schools['criteria']['min_enrollment'] == 750
    assert like_schools['criteria']['max_enrollment'] == 1250

    same_grade = payload['rankings']['same_grade']
    assert same_grade['rank'] == 2
    assert same_grade['total'] == 3
    assert same_grade['criteria'] == {'grade': '12'}


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

    for event_type in ('Track', 'Relay', 'Field'):
        if not db.session.get(EventType, event_type):
            db.session.add(EventType(event_type=event_type))

    events = (
        ('400m', 'Track'),
        ('800m', 'Track'),
        ('4 x 400 Relay', 'Relay'),
        ('Long Jump', 'Field'),
    )
    for event_name, event_type in events:
        if not db.session.get(Event, event_name):
            db.session.add(Event(event=event_name, event_type=event_type))

    for grade_value in ('11', '12'):
        if not db.session.get(Grade, grade_value):
            db.session.add(Grade(grade=grade_value))

    db.session.commit()


def seed_dashboard_data():
    from backend.models import (
        Athlete,
        School,
        Meet,
        AthleteResult,
        SchoolEnrollment,
    )

    target_year = '2024'

    def ensure_school(name, enrollment):
        school_obj = School.query.filter_by(school_name=name).first()
        if not school_obj:
            school_obj = School(school_name=name)
            db.session.add(school_obj)
            db.session.flush()

        if enrollment is not None:
            enrollment_row = SchoolEnrollment.query.filter_by(
                school_id=school_obj.school_id,
                year=target_year,
            ).first()
            if not enrollment_row:
                db.session.add(
                    SchoolEnrollment(
                        school_id=school_obj.school_id,
                        year=target_year,
                        enrollment=enrollment,
                    )
                )

        return school_obj

    unit_school = ensure_school('UnitTest High', 1000)
    comparable_school = ensure_school('Comparable High', 1120)
    small_school = ensure_school('Smallville High', 760)
    large_school = ensure_school('Mega High', 1500)

    athlete = Athlete(
        first='Test',
        last='Athlete',
        gender='Boys',
        graduation_year=2024,
        school=unit_school,
    )
    db.session.add(athlete)
    db.session.flush()

    others = []
    other_grades = []
    for first_name, school_obj, grade_value in (
        ('Other1', comparable_school, '12'),
        ('Other2', small_school, '12'),
        ('Other3', large_school, '11'),
    ):
        other = Athlete(
            first=first_name,
            last='Runner',
            gender='Boys',
            graduation_year=2024,
            school=school_obj,
        )
        db.session.add(other)
        others.append(other)
        other_grades.append(grade_value)
    db.session.flush()

    female_athletes = []
    for idx in range(1, 3):
        female = Athlete(
            first=f'Female{idx}',
            last='Runner',
            gender='Girls',
            graduation_year=2024,
            school=unit_school,
        )
        db.session.add(female)
        female_athletes.append(female)
    db.session.flush()

    sectional_meet = Meet(host='Sectional Host', meet_type='Sectional', meet_num=1, gender='Boys', year=2024)
    regional_meet = Meet(host='Regional Host', meet_type='Regional', meet_num=1, gender='Boys', year=2024)
    state_meet = Meet(host='State Host', meet_type='State', meet_num=1, gender='Boys', year=2024)
    girls_sectional_meet = Meet(host='Girls Sectional Host', meet_type='Sectional', meet_num=1, gender='Girls', year=2024)
    girls_regional_meet = Meet(host='Girls Regional Host', meet_type='Regional', meet_num=1, gender='Girls', year=2024)
    girls_state_meet = Meet(host='Girls State Host', meet_type='State', meet_num=1, gender='Girls', year=2024)
    db.session.add_all([
        sectional_meet,
        regional_meet,
        state_meet,
        girls_sectional_meet,
        girls_regional_meet,
        girls_state_meet,
    ])
    db.session.flush()

    db.session.add_all([
        # 400m results
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Final', grade='12', result='50.90', result2=50.90, place=2),
        AthleteResult(athlete_id=others[0].athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Final', grade=other_grades[0], result='50.10', result2=50.10, place=1),
        AthleteResult(athlete_id=others[1].athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Final', grade=other_grades[1], result='51.50', result2=51.50, place=3),
        AthleteResult(athlete_id=others[2].athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Final', grade=other_grades[2], result='52.00', result2=52.00, place=4),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=sectional_meet.meet_id, event='400m', result_type='Prelim', grade='12', result='50.95', result2=50.95, place=1),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=regional_meet.meet_id, event='400m', result_type='Final', grade='12', result='51.02', result2=51.02, place=6),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=regional_meet.meet_id, event='400m', result_type='Prelim', grade='12', result='51.20', result2=51.20, place=1),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=regional_meet.meet_id, event='4 x 400 Relay', result_type='Final', grade='12', result='3:18.00', result2=198.00, place=1),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=state_meet.meet_id, event='400m', result_type='Final', grade='12', result='51.40', result2=51.40, place=10),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=state_meet.meet_id, event='400m', result_type='Prelim', grade='12', result='51.30', result2=51.30, place=1),

        # 800m results
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=sectional_meet.meet_id, event='800m', result_type='Final', grade='12', result='1:55.20', result2=115.20, place=1),
        AthleteResult(athlete_id=others[0].athlete_id, meet_id=sectional_meet.meet_id, event='800m', result_type='Final', grade=other_grades[0], result='1:56.00', result2=116.00, place=2),
        AthleteResult(athlete_id=others[1].athlete_id, meet_id=sectional_meet.meet_id, event='800m', result_type='Final', grade=other_grades[1], result='1:58.20', result2=118.20, place=3),
        AthleteResult(athlete_id=others[2].athlete_id, meet_id=sectional_meet.meet_id, event='800m', result_type='Final', grade=other_grades[2], result='2:00.10', result2=120.10, place=4),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=regional_meet.meet_id, event='800m', result_type='Final', grade='12', result='1:55.80', result2=115.80, place=3),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=state_meet.meet_id, event='800m', result_type='Final', grade='12', result='1:56.10', result2=116.10, place=9),

        # Long Jump results (field event)
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=sectional_meet.meet_id, event='Long Jump', result_type='Final', grade='12', result='22-06.00', result2=22.50, place=1),
        AthleteResult(athlete_id=others[0].athlete_id, meet_id=sectional_meet.meet_id, event='Long Jump', result_type='Final', grade=other_grades[0], result='21-08.00', result2=21.67, place=2),
        AthleteResult(athlete_id=others[1].athlete_id, meet_id=sectional_meet.meet_id, event='Long Jump', result_type='Final', grade=other_grades[1], result='21-02.00', result2=21.17, place=3),
        AthleteResult(athlete_id=others[2].athlete_id, meet_id=sectional_meet.meet_id, event='Long Jump', result_type='Final', grade=other_grades[2], result='20-09.00', result2=20.75, place=4),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=regional_meet.meet_id, event='Long Jump', result_type='Final', grade='12', result='22-01.00', result2=22.08, place=2),
        AthleteResult(athlete_id=athlete.athlete_id, meet_id=state_meet.meet_id, event='Long Jump', result_type='Final', grade='12', result='22-03.00', result2=22.25, place=4),

        # Girls results (should not impact boys rankings)
        AthleteResult(athlete_id=female_athletes[0].athlete_id, meet_id=girls_sectional_meet.meet_id, event='400m', result_type='Final', grade='12', result='57.10', result2=57.10, place=1),
        AthleteResult(athlete_id=female_athletes[1].athlete_id, meet_id=girls_sectional_meet.meet_id, event='400m', result_type='Final', grade='12', result='58.00', result2=58.00, place=2),
        AthleteResult(athlete_id=female_athletes[0].athlete_id, meet_id=girls_regional_meet.meet_id, event='400m', result_type='Final', grade='12', result='56.80', result2=56.80, place=1),
        AthleteResult(athlete_id=female_athletes[0].athlete_id, meet_id=girls_state_meet.meet_id, event='400m', result_type='Final', grade='12', result='56.50', result2=56.50, place=3),
        AthleteResult(athlete_id=female_athletes[0].athlete_id, meet_id=girls_sectional_meet.meet_id, event='800m', result_type='Final', grade='12', result='2:13.50', result2=133.50, place=1),
        AthleteResult(athlete_id=female_athletes[1].athlete_id, meet_id=girls_sectional_meet.meet_id, event='800m', result_type='Final', grade='12', result='2:15.20', result2=135.20, place=2),
        AthleteResult(athlete_id=female_athletes[0].athlete_id, meet_id=girls_regional_meet.meet_id, event='800m', result_type='Final', grade='12', result='2:12.80', result2=132.80, place=1),
        AthleteResult(athlete_id=female_athletes[0].athlete_id, meet_id=girls_sectional_meet.meet_id, event='Long Jump', result_type='Final', grade='12', result='18-06.00', result2=18.50, place=1),
        AthleteResult(athlete_id=female_athletes[1].athlete_id, meet_id=girls_sectional_meet.meet_id, event='Long Jump', result_type='Final', grade='12', result='18-02.00', result2=18.17, place=2),
    ])

    db.session.commit()
    return athlete.athlete_id
