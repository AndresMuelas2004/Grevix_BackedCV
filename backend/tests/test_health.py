from fastapi.testclient import TestClient

from backedcv.main import create_app


def test_health_reports_ok():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
