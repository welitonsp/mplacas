from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from mplacas.core.config import get_settings
from mplacas.main import app


def test_scoped_read_key_hides_out_of_scope_plant_resources(monkeypatch) -> None:
    allowed_plant_id = uuid.UUID("00000000-0000-0000-0000-000000000040")
    denied_plant_id = uuid.UUID("00000000-0000-0000-0000-000000000041")
    bill_id = uuid.UUID("00000000-0000-0000-0000-000000000042")
    monkeypatch.setenv("MPLACAS_OPERATIONS_API_KEY", "synthetic-admin-key")
    monkeypatch.setenv("MPLACAS_OPERATIONS_READ_API_KEY", "synthetic-read-key")
    monkeypatch.setenv("MPLACAS_OPERATIONS_READ_PLANT_IDS", str(allowed_plant_id))
    get_settings.cache_clear()
    client = TestClient(app)
    headers = {"X-API-Key": "synthetic-read-key"}

    requests = (
        (f"/energy/cycles/{bill_id}", {"plant_id": str(denied_plant_id)}),
        ("/energy/trends/latest", {"plant_id": str(denied_plant_id)}),
        ("/energy/executive/latest", {"plant_id": str(denied_plant_id)}),
        (
            "/energy/anomalies/latest",
            {
                "plant_id": str(denied_plant_id),
                "expected_daily_production_kwh": "10",
            },
        ),
        ("/energy/explanations/latest", {"plant_id": str(denied_plant_id)}),
        ("/reports/monthly/latest", {"plant_id": str(denied_plant_id)}),
    )

    for path, params in requests:
        response = client.get(path, headers=headers, params=params)
        assert response.status_code == 404
        assert response.json() == {"detail": "plant not found"}

    get_settings.cache_clear()
