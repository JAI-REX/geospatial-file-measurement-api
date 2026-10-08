from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend():
    response = client.get("/")
    assert response.status_code == 200
    assert "GeoMeasure" in response.text


def test_rejects_unsupported_file():
    response = client.post(
        "/api/files/",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
    assert "Only .kml or .zip" in response.json()["detail"]


def test_missing_file():
    response = client.get("/api/files/does-not-exist/")
    assert response.status_code == 404
