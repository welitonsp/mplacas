from fastapi.testclient import TestClient

from mplacas.main import app


def test_legacy_dashboard_redirects_to_the_jwt_spa() -> None:
    response = TestClient(app).get("/dashboard", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "https://mplacas-frontend.pages.dev/dashboard"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_legacy_dashboard_assets_are_not_served() -> None:
    response = TestClient(app).get("/dashboard-assets/dashboard.js")

    assert response.status_code == 404
