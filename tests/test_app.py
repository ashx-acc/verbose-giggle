"""API tests for the FastAPI + sqlite3 application."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.seed import SCHEMA_SQL


@pytest.fixture()
def client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "test_chicago_crime.db"

    setup_connection = sqlite3.connect(database_path)
    setup_connection.executescript(SCHEMA_SQL)
    setup_connection.commit()
    setup_connection.close()

    def override_get_db():
        connection = sqlite3.connect(database_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def real_client() -> Generator[TestClient, None, None]:
    """Read-only client against the real notebook database."""
    with TestClient(app) as test_client:
        yield test_client


def sample_payload(code: int = 901) -> dict:
    return {
        "community_code": code,
        "community_name": "Test Community",
        "population": 12345,
        "area_sqmile": 2.5,
        "area_sqkm": 6.47,
        "density_per_sqmi": 4938.0,
        "density_per_sqkm": 1908.0,
    }


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_read_update_patch_delete(client: TestClient):
    created = client.post("/api/community", json=sample_payload())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["community_code"] == 901
    assert body["community_name"] == "Test Community"

    read = client.get("/api/community/901")
    assert read.status_code == 200
    assert read.json()["population"] == 12345

    replaced = client.put(
        "/api/community/901",
        json={
            "community_name": "Renamed Community",
            "population": 20000,
            "area_sqmile": 3.0,
            "area_sqkm": 7.77,
            "density_per_sqmi": 6666.0,
            "density_per_sqkm": 2574.0,
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["community_name"] == "Renamed Community"
    assert replaced.json()["population"] == 20000

    patched = client.patch(
        "/api/community/901",
        json={"community_name": "Patched Community"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["community_name"] == "Patched Community"
    assert patched.json()["population"] == 20000

    deleted = client.delete("/api/community/901")
    assert deleted.status_code == 204
    assert client.get("/api/community/901").status_code == 404


def test_duplicate_code_and_name_conflict(client: TestClient):
    first = client.post("/api/community", json=sample_payload(902))
    assert first.status_code == 201

    duplicate_code = client.post(
        "/api/community",
        json={**sample_payload(902), "community_name": "Different Name"},
    )
    assert duplicate_code.status_code == 409

    duplicate_name = client.post(
        "/api/community",
        json={**sample_payload(903), "community_name": "Test Community"},
    )
    assert duplicate_name.status_code == 409


def test_patch_requires_at_least_one_field(client: TestClient):
    client.post("/api/community", json=sample_payload(904))
    response = client.patch("/api/community/904", json={})
    assert response.status_code == 400


def test_missing_community_returns_404(client: TestClient):
    assert client.get("/api/community/99999").status_code == 404
    assert client.put("/api/community/99999", json=sample_payload(99999)).status_code == 404
    assert client.patch("/api/community/99999", json={"population": 1}).status_code == 404
    assert client.delete("/api/community/99999").status_code == 404


def test_dashboard_and_insights_endpoints(real_client: TestClient):
    dashboard = real_client.get("/")
    assert dashboard.status_code == 200
    assert "Crime intelligence" in dashboard.text
    assert "Austin" in dashboard.text

    community_page = real_client.get("/community")
    assert community_page.status_code == 200
    assert "Community-area dimension" in community_page.text

    insights = real_client.get("/api/dashboard/insights")
    assert insights.status_code == 200
    payload = insights.json()
    assert payload["kpis"]["total_crimes"] == 496
    assert payload["kpis"]["top_crime_type"] == "THEFT"
    assert len(payload["insights"]) >= 5
    assert len(payload["top_categories"]) == 10


def test_crime_summary_for_known_community(real_client: TestClient):
    response = real_client.get("/api/community/25/crime-summary")
    assert response.status_code == 200
    body = response.json()
    assert body["community_name"] == "Austin"
    assert body["crime_count"] == 34
    assert body["arrest_count"] > 0


def test_dashboard_png_export(real_client: TestClient):
    response = real_client.get("/dashboard/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 100_000
