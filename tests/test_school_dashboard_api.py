"""The school dashboard API that the production page actually calls.

The v2 and v3 dashboards and their /api/v3/* endpoints are gone; what remains is
the original page, served by /api/schools/<id>/dashboard, which had no coverage
of its own until now.
"""


def test_dashboard_endpoint_returns_school_payload(client):
    response = client.get("/api/schools/1/dashboard")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["school"]["name"] == "Alpha High"
    # The sections the page renders from.
    for key in ("school", "roster", "relay_results", "cumulative_points"):
        assert key in payload, key


def test_dashboard_endpoint_rejects_unknown_school(client):
    response = client.get("/api/schools/9999/dashboard")
    assert response.status_code == 404


def test_removed_dashboard_versions_are_gone(client):
    """v2 and v3 are retired -- their pages and API must not answer.

    Guards against a half-finished removal leaving a route that renders a
    template or calls a query function that no longer exists.
    """
    for url in (
        "/school-dashboard-v2/1",
        "/school-dashboard-v3/1",
        "/api/v2/schools/1/dashboard/core",
        "/api/v3/schools/1/dashboard/core",
        "/api/v3/schools/1/dashboard/athletes",
        "/api/v3/schools/1/dashboard/ranking",
        "/api/v3/schools/1/dashboard/returning",
        "/api/v3/schools/1/dashboard/season-h2h",
        "/api/v3/schools/1/dashboard/leaderboard",
    ):
        assert client.get(url).status_code == 404, url


def test_surviving_dashboards_still_serve(client):
    """The original page and the v4 prototype both render.

    v4 has no prepared payload against the test fixture -- its cache is built
    from the real database -- so it is expected to render its "not built yet"
    state rather than a dashboard. What matters here is that the route resolves
    and the template renders without error.
    """
    assert client.get("/school-dashboard/1").status_code == 200
    assert client.get("/school-dashboard-v4/1").status_code == 200
