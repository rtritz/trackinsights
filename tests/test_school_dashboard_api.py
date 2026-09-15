"""API tests for the school dashboard (v3 -- the only one, since v2 was removed)."""


def test_core_endpoint_returns_school_payload(client):
    response = client.get("/api/v3/schools/1/dashboard/core")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["school"]["name"] == "Alpha High"
    assert payload["filters"]["selected_gender"] == "Boys"
    assert str(payload["filters"]["selected_season"]) == "2024"
    # The heavy blocks stay on their own endpoints so the first paint is cheap.
    assert "program_rank" not in payload
    assert "qualifier_summary" not in payload
    # v3 tells the season control which seasons are still being run.
    assert "incomplete_seasons" in payload["filters"]


def test_core_endpoint_rejects_unknown_school(client):
    response = client.get("/api/v3/schools/9999/dashboard/core")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not found"


def test_core_endpoint_validates_gender_and_season(client):
    bad_gender = client.get("/api/v3/schools/1/dashboard/core?gender=Mixed")
    assert bad_gender.status_code == 400

    bad_season = client.get("/api/v3/schools/1/dashboard/core?season=2022")
    assert bad_season.status_code == 400


def test_event_detail_rejects_all_time_mode(client):
    response = client.get("/api/v3/schools/1/dashboard/events/100%20Meters?season=all-time")
    assert response.status_code == 400
    assert "specific postseason season" in response.get_json()["error"]


def test_leaderboard_endpoint(client):
    response = client.get(
        "/api/v3/schools/1/dashboard/leaderboard?season=2024&top_n=2&enrollment_max=1000"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["filtered_schools"] >= 1
    assert payload["rows"][0]["rank_display"]


def test_ranking_endpoint_returns_scope_data(client):
    response = client.get("/api/v3/schools/1/dashboard/ranking?season=2024")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["year"] == 2024
    assert payload["gender"] == "Boys"
    assert payload["rank_display"]
    # v3 ranks the event groups rather than scoring them: group scores are not
    # comparable across groups, group ranks are.
    assert "group_standings" in payload
    assert "group_scores" not in payload


def test_athlete_scorecard_carries_stage_cells(client):
    response = client.get("/api/v3/schools/1/dashboard/athletes?season=2024")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "season"
    assert payload["stages_present"]

    scored = [row for row in payload["rows"] if row["entry_type"] != "none"]
    assert scored, "expected at least one contested event"
    for row in scored:
        # Every mark belongs to a named stage, and the rank is computed on the
        # highlighted one -- so best_stage must always point at a real cell.
        assert row["stages"]
        if any(cell["has_mark"] for cell in row["stages"].values()):
            assert row["best_stage"] in row["stages"]
        else:
            assert row["best_stage"] is None
            assert not row["rank"]


def test_all_time_switches_to_records_mode(client):
    response = client.get("/api/v3/schools/1/dashboard/athletes?season=all-time")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "records"

    for row in payload["rows"]:
        if row["entry_type"] == "none":
            continue
        # A records board has no statewide rank to show, and every record is dated.
        assert row["rank"] is None
        assert row["year"]


def test_returning_endpoint_reports_retention(client):
    response = client.get("/api/v3/schools/1/dashboard/returning?season=2024")
    assert response.status_code == 200
    payload = response.get_json()
    if not payload.get("available"):
        return
    retention = payload["retention"]
    assert 0 <= retention["athletes_returning"] <= retention["athletes_total"]

    # The headline is the share of scoring that returns, so it must stay a real
    # proportion -- or be absent entirely when the team scored nothing.
    points = payload["points"]
    assert 0 <= points["points_returning"] <= points["points_total"]
    if points["points_total"]:
        assert points["percent"] == round(
            100.0 * points["points_returning"] / points["points_total"], 1
        )
    else:
        assert points["percent"] is None


def test_removed_v2_endpoints_are_gone(client):
    for path in (
        "/api/v2/schools/1/dashboard/core",
        "/api/v2/schools/1/dashboard/scorecard",
        "/api/v2/schools/1/dashboard/ranking",
        "/api/v2/schools/1/dashboard/leaderboard",
        "/api/v2/schools/1/dashboard/qualifiers",
    ):
        assert client.get(path).status_code == 404, path
