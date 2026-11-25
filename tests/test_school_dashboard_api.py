"""Retired school dashboards stay retired; the current page serves.

The v2, v3 and v4 dashboards and their APIs are gone. The school page is
/school-dashboard/<id> (services/school_page.py), and its rank
popups read /api/rankings/<gender>/<season>.
"""


def test_removed_dashboard_versions_are_gone(client):
    """Guards against a half-finished removal leaving a route that renders a
    template or calls a query function that no longer exists."""
    for url in (
        "/school-dashboard-v2/1",
        "/school-dashboard-v3/1",
        "/school-dashboard-v4/1",
        "/school-dashboard-v4/1/Boys/2024",
        "/api/schools/1/dashboard",
        "/api/schools/1/percentiles",
        "/api/v2/schools/1/dashboard/core",
        "/api/v3/schools/1/dashboard/core",
        "/api/v3/schools/1/dashboard/athletes",
        "/api/v3/schools/1/dashboard/ranking",
        "/api/v3/schools/1/dashboard/returning",
        "/api/v3/schools/1/dashboard/season-h2h",
        "/api/v3/schools/1/dashboard/leaderboard",
        "/api/v4/rankings/Boys/2024",
    ):
        assert client.get(url).status_code == 404, url


def test_the_school_page_serves(client):
    assert client.get("/school-dashboard/1").status_code == 200
    assert client.get("/school-dashboard/1/Boys/2024").status_code == 200
    assert client.get("/school-dashboard/1/Boys/all-time").status_code == 200
