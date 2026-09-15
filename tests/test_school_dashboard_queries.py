from backend import queries


def _scorecard_row(scorecard, event_name):
    return next(row for row in scorecard["rows"] if row["event"] == event_name)


def _program_event(program_rank, event_name):
    return next(row for row in program_rank["event_scores"] if row["event"] == event_name)


def test_stage_summary_distinguishes_zero_points_from_no_attendance(app):
    with app.app_context():
        summary = queries.get_school_dashboard_v2_stage_summary(1, "Boys", 2023)
        stages = {row["stage"]: row for row in summary["stages"]}

        assert stages["Sectional"]["attended"] is True
        assert stages["Sectional"]["entries"] >= 1
        assert stages["Sectional"]["points"] == 0
        assert stages["Sectional"]["points_display"] == "0"
        assert stages["Regional"]["attended"] is False
        assert stages["Regional"]["points"] is None
        assert stages["Regional"]["points_display"] == "—"
        assert stages["State"]["points_display"] == "—"


def test_program_rank_uses_standard_competition_ranking_with_ties(app):
    with app.app_context():
        queries._build_statewide_program_rankings.cache_clear()
        program_rank = queries.get_school_dashboard_v2_program_rank(1, "Boys", 2024)
        hundred = _program_event(program_rank, "100 Meters")

        slot_ranks = [slot["statewide_rank"] for slot in hundred["slots"]]
        assert slot_ranks == [2, 4]
        assert hundred["slots"][0]["statewide_score"] == 66.7
        assert hundred["slots"][1]["statewide_score"] == 0.0


def test_best_mark_prior_status_and_relay_holder_logic(app):
    with app.app_context():
        scorecard_2024 = queries.get_school_dashboard_v2_scorecard(1, "Boys", 2024)
        assert _scorecard_row(scorecard_2024, "100 Meters")["status"]["label"] == "Improved"
        assert _scorecard_row(scorecard_2024, "200 Meters")["status"]["label"] == "Same"
        assert _scorecard_row(scorecard_2024, "High Jump")["status"]["label"] == "New"
        assert _scorecard_row(scorecard_2024, "4 x 100 Relay")["holder_name"] == "Alpha High"

        scorecard_2023 = queries.get_school_dashboard_v2_scorecard(1, "Boys", 2023)
        distance_row = _scorecard_row(scorecard_2023, "3200 Meters")
        assert distance_row["status"]["label"] == "—"
        assert "No earlier covered postseason season" in distance_row["status"]["tooltip"]


def test_event_detail_returns_individual_and_relay_row_shapes(app):
    with app.app_context():
        individual_detail = queries.get_school_dashboard_v2_event_detail(1, "Boys", 2024, "100 Meters")
        relay_detail = queries.get_school_dashboard_v2_event_detail(1, "Boys", 2024, "4 x 100 Relay")

        assert individual_detail["all_marks"]
        assert individual_detail["all_marks"][0]["row_type"] == "individual"
        assert "athlete_name" in individual_detail["all_marks"][0]
        assert individual_detail["trend_points"]

        assert relay_detail["all_marks"]
        assert relay_detail["all_marks"][0]["row_type"] == "relay"
        assert relay_detail["all_marks"][0]["team_name"] == "Alpha High"
        assert "lineup" in relay_detail["all_marks"][0]


def test_school_filtered_qualifiers_group_individual_and_relay(monkeypatch, app):
    regional_payload = {
        "context": {"status": "ready"},
        "events": [
            {
                "event": "100 Meters",
                "qualifiers": [
                    {"school_id": 1, "athlete_id": 101, "name": "Sprinter, Aaron", "school": "Alpha High", "result": "10.80", "place": 2, "sectional_host": "Alpha Sectional", "qualifier_type": "auto"},
                    {"school_id": 2, "athlete_id": 201, "name": "Falcon, Brent", "school": "Beta High", "result": "10.70", "place": 1, "sectional_host": "Alpha Sectional", "qualifier_type": "auto"},
                ],
            },
            {
                "event": "4 x 100 Relay",
                "qualifiers": [
                    {"school_id": 1, "name": None, "school": "Alpha High", "result": "42.80", "place": 1, "sectional_host": "Alpha Sectional", "qualifier_type": "auto"},
                ],
            },
        ],
    }
    state_payload = {
        "context": {"status": "ready"},
        "events": [
            {
                "event": "100 Meters",
                "qualifiers": [
                    {"school_id": 1, "athlete_id": 101, "name": "Sprinter, Aaron", "school": "Alpha High", "result": "10.80", "place": 3, "sectional_host": "Regional 1", "qualifier_type": "fill"},
                ],
            },
        ],
    }

    monkeypatch.setattr(queries, "get_regional_qualifiers", lambda gender, regional_num, year: regional_payload if regional_num == 1 else {"context": {"status": "ready"}, "events": []})
    monkeypatch.setattr(queries, "get_state_qualifiers", lambda gender, year: state_payload)
    queries.get_school_dashboard_v2_qualifiers.cache_clear()

    with app.app_context():
        qualifiers = queries.get_school_dashboard_v2_qualifiers(1, "Boys", 2024)

        assert len(qualifiers["regional"]["individual"]) == 1
        assert qualifiers["regional"]["individual"][0]["athlete_id"] == 101
        assert len(qualifiers["regional"]["relay"]) == 1
        assert qualifiers["regional"]["relay"][0]["name"] == "Alpha High"
        assert len(qualifiers["state"]["individual"]) == 1
        assert qualifiers["state"]["individual"][0]["source_label"] == "Regional 1"
