import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from app import create_app, db  # noqa: E402
from app import queries  # noqa: E402
from app.models import Athlete, AthleteResult, Event, Meet, RelayResult, School, SchoolEnrollment  # noqa: E402
from common.const import CONST  # noqa: E402


class TestConfig:
    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = ""
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # The fixture seeds one meet per round; the real gate wants 32 sectionals.
    V3_REQUIRE_COMPLETE_SEASON = False


def _clear_query_caches():
    for func in (
        queries._get_event_types_map,
        queries._build_statewide_program_rankings,
        queries.get_school_dashboard_v4_qualifiers,
        queries.get_regional_qualifiers,
        queries._schools_with_logos,
    ):
        if hasattr(func, "cache_clear"):
            func.cache_clear()


def _seed_events():
    boys_hurdles = list(CONST.EVENT.ALL_BOYS_HURDLES)
    girls_hurdles = list(CONST.EVENT.ALL_GIRLS_HURDLES)
    event_type_map = {}
    for event_name in CONST.EVENT.ALL_TRACK:
        event_type_map[event_name] = CONST.EVENT_TYPE.TRACK
    for event_name in CONST.EVENT.ALL_FIELD:
        event_type_map[event_name] = CONST.EVENT_TYPE.FIELD
    for event_name in CONST.EVENT.ALL_RELAY:
        event_type_map[event_name] = CONST.EVENT_TYPE.RELAY
    for event_name in boys_hurdles + girls_hurdles:
        event_type_map[event_name] = CONST.EVENT_TYPE.TRACK

    return [Event(event=name, event_type=event_type) for name, event_type in event_type_map.items()]


def _seed_core_data():
    schools = [
        School(school_id=1, school_name="Alpha High", team_name="Alpha High", city="Alpha City", school_type="Public"),
        School(school_id=2, school_name="Beta High", team_name="Beta High", city="Beta City", school_type="Public"),
        School(school_id=3, school_name="Gamma High", team_name="Gamma High", city="Gamma City", school_type="Public"),
    ]

    enrollments = [
        SchoolEnrollment(school_id=1, year=2023, enrollment=920),
        SchoolEnrollment(school_id=1, year=2024, enrollment=930),
        SchoolEnrollment(school_id=2, year=2024, enrollment=480),
        SchoolEnrollment(school_id=3, year=2024, enrollment=1210),
    ]

    meets = [
        Meet(meet_id=1, host="Alpha Sectional", meet_type="Sectional", meet_num=1, gender="Boys", year=2023),
        Meet(meet_id=2, host="Regional 1", meet_type="Regional", meet_num=1, gender="Boys", year=2023),
        Meet(meet_id=3, host="State Finals", meet_type="State", meet_num=1, gender="Boys", year=2023),
        Meet(meet_id=4, host="Alpha Sectional", meet_type="Sectional", meet_num=1, gender="Boys", year=2024),
        Meet(meet_id=5, host="Regional 1", meet_type="Regional", meet_num=1, gender="Boys", year=2024),
        Meet(meet_id=6, host="State Finals", meet_type="State", meet_num=1, gender="Boys", year=2024),
    ]

    athletes = [
        Athlete(athlete_id=101, first="Aaron", last="Sprinter", school_id=1, gender="Boys", graduation_year=2025),
        Athlete(athlete_id=102, first="Blake", last="Sprinter", school_id=1, gender="Boys", graduation_year=2025),
        Athlete(athlete_id=103, first="Chris", last="Curve", school_id=1, gender="Boys", graduation_year=2025),
        Athlete(athlete_id=104, first="Dylan", last="Jumper", school_id=1, gender="Boys", graduation_year=2025),
        Athlete(athlete_id=105, first="Ethan", last="Distance", school_id=1, gender="Boys", graduation_year=2025),
        Athlete(athlete_id=201, first="Brent", last="Falcon", school_id=2, gender="Boys", graduation_year=2025),
        Athlete(athlete_id=202, first="Cole", last="Vault", school_id=2, gender="Boys", graduation_year=2025),
        Athlete(athlete_id=301, first="Grant", last="Flash", school_id=3, gender="Boys", graduation_year=2025),
    ]

    athlete_results = [
        AthleteResult(athlete_id=105, meet_id=1, event="3200 Meters", result_type="Final", result="10:00.00", result2=600.0, place=10, grade="SR"),
        AthleteResult(athlete_id=101, meet_id=1, event="100 Meters", result_type="Final", result="11.00", result2=11.0, place=10, grade="SR"),
        AthleteResult(athlete_id=201, meet_id=1, event="100 Meters", result_type="Final", result="10.90", result2=10.9, place=1, grade="SR"),
        AthleteResult(athlete_id=301, meet_id=1, event="200 Meters", result_type="Final", result="22.40", result2=22.4, place=2, grade="SR"),
        AthleteResult(athlete_id=101, meet_id=4, event="100 Meters", result_type="Final", result="10.90", result2=10.9, place=4, grade="SR"),
        AthleteResult(athlete_id=101, meet_id=5, event="100 Meters", result_type="Final", result="10.80", result2=10.8, place=3, grade="SR"),
        AthleteResult(athlete_id=101, meet_id=6, event="100 Meters", result_type="Prelim", result="10.85", result2=10.85, place=5, grade="SR"),
        AthleteResult(athlete_id=102, meet_id=4, event="100 Meters", result_type="Final", result="10.70", result2=10.7, place=2, grade="SR"),
        AthleteResult(athlete_id=102, meet_id=5, event="100 Meters", result_type="Final", result="10.72", result2=10.72, place=2, grade="SR"),
        AthleteResult(athlete_id=103, meet_id=1, event="200 Meters", result_type="Final", result="22.00", result2=22.0, place=10, grade="SR"),
        AthleteResult(athlete_id=103, meet_id=4, event="200 Meters", result_type="Final", result="22.00", result2=22.0, place=1, grade="SR"),
        AthleteResult(athlete_id=104, meet_id=4, event="High Jump", result_type="Final", result="6'0\"", result2=72.0, place=1, grade="SR"),
        AthleteResult(athlete_id=201, meet_id=4, event="100 Meters", result_type="Final", result="10.70", result2=10.7, place=2, grade="SR"),
        AthleteResult(athlete_id=202, meet_id=4, event="High Jump", result_type="Final", result="5'10\"", result2=70.0, place=2, grade="SR"),
        AthleteResult(athlete_id=301, meet_id=4, event="100 Meters", result_type="Final", result="10.60", result2=10.6, place=1, grade="SR"),
    ]

    relay_results = [
        RelayResult(school_id=1, meet_id=4, event="4 x 100 Relay", result="43.00", result2=43.0, place=2, athlete_names="A Sprinter, B Sprinter, C Curve, D Jumper"),
        RelayResult(school_id=1, meet_id=5, event="4 x 100 Relay", result="42.80", result2=42.8, place=1, athlete_names="A Sprinter, B Sprinter, C Curve, D Jumper"),
        RelayResult(school_id=2, meet_id=4, event="4 x 100 Relay", result="43.50", result2=43.5, place=3, athlete_names="Brent Falcon, Cole Vault, Relay Three, Relay Four"),
        RelayResult(school_id=3, meet_id=4, event="4 x 100 Relay", result="42.90", result2=42.9, place=1, athlete_names="Grant Flash, Relay Six, Relay Seven, Relay Eight"),
    ]

    return schools, enrollments, meets, athletes, athlete_results, relay_results


@pytest.fixture()
def app():
    db_path = REPO_ROOT / "tests" / f"school_dashboard_test_{uuid4().hex}.sqlite"
    config = type(
        "LocalTestConfig",
        (TestConfig,),
        {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path.as_posix()}"},
    )

    app = create_app(config)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add_all(_seed_events())
        schools, enrollments, meets, athletes, athlete_results, relay_results = _seed_core_data()
        db.session.add_all(schools + enrollments + meets + athletes + athlete_results + relay_results)
        db.session.commit()
        _clear_query_caches()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()

    if db_path.exists():
        db_path.unlink()


@pytest.fixture()
def client(app):
    return app.test_client()
