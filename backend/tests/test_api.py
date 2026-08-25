"""
Tests for `fcc_dashboard.api` itself -- the real startup path and the
assembled route set.

Every other test file in this suite bypasses `lifespan` entirely via
`app.dependency_overrides[get_db] = lambda: test_db`, so `_resolve_db_path`,
`init_db` against a real on-disk file, and the lifespan startup/shutdown
code in `api.py` are never actually exercised anywhere else. This file
closes that gap: it points the env-var override seams at a `tmp_path` file
and uses `TestClient` as a context manager (`with TestClient(app) as
client:`), which is what actually runs FastAPI's lifespan, unlike
instantiating `TestClient(app)` directly.
"""

from fastapi.testclient import TestClient

from fcc_dashboard.api import app


def test_lifespan_starts_real_db_and_serves_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("FCC_DASHBOARD_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("FCC_DASHBOARD_PRICING_PATH", str(tmp_path / "pricing.json"))

    with TestClient(app) as client:
        response = client.get("/db/tables")

    assert response.status_code == 200
    assert set(response.json()["tables"]) == {
        "requests", "collector_state", "process_state",
    }
    assert (tmp_path / "test.db").exists()


def test_openapi_route_set_is_complete():
    paths = set(app.openapi()["paths"])
    assert paths == {
        "/status",
        "/requests",
        "/stats",
        "/pricing",
        "/pricing/refresh",
        "/db/tables",
        "/db/tables/{name}",
    }
