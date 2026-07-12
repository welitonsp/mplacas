from fastapi.testclient import TestClient

from mplacas.main import app


def test_dashboard_page_is_served_without_embedded_credentials() -> None:
    response = TestClient(app).get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Painel Executivo de Energia" in response.text
    assert "Chave operacional" in response.text
    assert "MPLACAS_OPERATIONS_API_KEY" not in response.text
    assert "X-API-Key" not in response.text


def test_dashboard_assets_are_served() -> None:
    client = TestClient(app)

    css = client.get("/dashboard-assets/dashboard.css")
    javascript = client.get("/dashboard-assets/dashboard.js")

    assert css.status_code == 200
    assert javascript.status_code == 200
    assert "metric-grid" in css.text
    assert '"X-API-Key":state.apiKey' in javascript.text
    assert "localStorage" not in javascript.text
