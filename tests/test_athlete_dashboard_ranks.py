"""Statewide and same-grade ranks exposed only on athlete dashboard history."""
from app import db
from app.models import AthleteResult, Meet
from app.queries.athletes import get_athlete_dashboard_data, _add_dashboard_history_ranks
from app.models import Athlete


def history_stage(payload, event, year, stage="sectional"):
    return next(row[stage] for row in payload["playoff_history"]
                if row["event"] == event and row["year"] == year)


def test_state_ranks_span_sectionals_but_class_ranks_use_race_grade(app):
    # A different sectional contributes to the statewide denominator. Aaron's
    # stored graduation year implies JR, but his race says SR: use the race.
    db.session.add(Meet(meet_id=17, host="Other Sectional", meet_type="Sectional",
                        gender="Boys", year=2024))
    db.session.add_all([
        AthleteResult(athlete_id=103, meet_id=17, event="100 Meters",
                      result_type="Final", result="10.80", result2=10.8, grade="JR"),
        AthleteResult(athlete_id=102, meet_id=4, event="100 Meters",
                      result_type="Prelim", result="10.00", result2=10.0, grade="SR"),
        AthleteResult(athlete_id=105, meet_id=17, event="100 Meters",
                      result_type="Final", result="DNF", result2=9999, grade="SR"),
    ])
    db.session.commit()

    stage = history_stage(get_athlete_dashboard_data(101), "100 Meters", 2024)
    assert stage["state_rank"] == {"rank": 5, "total": 5}
    assert stage["class_rank"] == {"rank": 4, "total": 4, "grade": "SR"}

    tied = history_stage(get_athlete_dashboard_data(102), "100 Meters", 2024)
    assert tied["state_rank"] == {"rank": 2, "total": 5}
    assert tied["class_rank"] == {"rank": 2, "total": 4, "grade": "SR"}


def test_field_ranks_put_larger_marks_first(app):
    stage = history_stage(get_athlete_dashboard_data(104), "High Jump", 2024)
    assert stage["state_rank"] == {"rank": 1, "total": 2}
    assert stage["class_rank"] == {"rank": 1, "total": 2, "grade": "SR"}


def test_prelim_only_results_and_gender_are_respected(app):
    stage = history_stage(get_athlete_dashboard_data(111), "100 Hurdles", 2024, "state")
    assert stage["state_rank"] == {"rank": 1, "total": 1}
    assert stage["class_rank"] == {"rank": 1, "total": 1, "grade": "SR"}


def test_unknown_grade_has_no_class_rank(app):
    result = db.session.get(AthleteResult, (101, 4, "100 Meters", "Final"))
    result.grade = None
    db.session.commit()
    stage = history_stage(get_athlete_dashboard_data(101), "100 Meters", 2024)
    assert stage["state_rank"] == {"rank": 4, "total": 4}
    assert stage["class_rank"] is None


def test_relay_rank_counts_teams_and_has_no_class_rank(app):
    history = [{"year": 2024, "event": "4 x 100 Relay", "sectional": {
        "meet_type": "Sectional", "meet_id": 4, "is_relay": True,
    }}]
    _add_dashboard_history_ranks(history, db.session.get(Athlete, 101))
    assert history[0]["sectional"]["state_rank"] == {"rank": 2, "total": 3}
    assert history[0]["sectional"]["class_rank"] is None


def test_dashboard_api_contains_rank_columns(client):
    response = client.get("/api/athletes/101/dashboard")
    assert response.status_code == 200
    stage = history_stage(response.get_json(), "100 Meters", 2024)
    assert stage["state_rank"] == {"rank": 4, "total": 4}
    assert stage["class_rank"] == {"rank": 4, "total": 4, "grade": "SR"}
