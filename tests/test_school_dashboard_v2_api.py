def test_school_dashboard_v2_core_endpoint_returns_school_payload(client):
    response = client.get("/api/v2/schools/1/dashboard/core")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["school"]["name"] == "Alpha High"
    assert payload["filters"]["selected_gender"] == "Boys"
    assert str(payload["filters"]["selected_season"]) == "2024"
    assert "program_rank" not in payload
    assert "qualifier_summary" not in payload


def test_school_dashboard_v2_core_endpoint_rejects_unknown_school(client):
    response = client.get("/api/v2/schools/9999/dashboard/core")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not found"


def test_school_dashboard_v2_core_endpoint_validates_gender_and_season(client):
    bad_gender = client.get("/api/v2/schools/1/dashboard/core?gender=Mixed")
    assert bad_gender.status_code == 400

    bad_season = client.get("/api/v2/schools/1/dashboard/core?season=2022")
    assert bad_season.status_code == 400


def test_school_dashboard_v2_event_detail_rejects_all_time_mode(client):
    response = client.get("/api/v2/schools/1/dashboard/events/100%20Meters?season=all-time")
    assert response.status_code == 400
    assert "specific postseason season" in response.get_json()["error"]


def test_school_dashboard_v2_scorecard_and_leaderboard_endpoints(client):
    scorecard_response = client.get("/api/v2/schools/1/dashboard/scorecard?season=2024")
    leaderboard_response = client.get("/api/v2/schools/1/dashboard/leaderboard?season=2024&top_n=2&enrollment_max=1000")

    assert scorecard_response.status_code == 200
    scorecard_payload = scorecard_response.get_json()
    assert any(row["event"] == "4 x 100 Relay" for row in scorecard_payload["rows"])

    assert leaderboard_response.status_code == 200
    leaderboard_payload = leaderboard_response.get_json()
    assert leaderboard_payload["filtered_schools"] >= 1
    assert leaderboard_payload["rows"][0]["rank_display"]


def test_school_dashboard_v2_ranking_endpoint_returns_cached_scope_data(client):
    response = client.get("/api/v2/schools/1/dashboard/ranking?season=2024")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["year"] == 2024
    assert payload["gender"] == "Boys"
    assert payload["rank_display"]
    assert "group_scores" in payload
