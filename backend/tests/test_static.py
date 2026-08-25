"""
Tests for fcc_dashboard.static -- single-process static file serving.

Covers `get_static_dir`'s env-var override/default resolution and
`mount_static_files`'s mount-or-no-op behavior, each exercised against a
fresh, isolated `FastAPI()` instance (not the real module-level `app` in
`api.py`, which mounts once at import time and can't be cleanly remounted
mid-test-suite).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fcc_dashboard.static import get_static_dir, mount_static_files


def test_get_static_dir_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FCC_DASHBOARD_STATIC_DIR", str(tmp_path))
    assert get_static_dir() == tmp_path


def test_get_static_dir_defaults_to_frontend_dist_relative_to_repo(monkeypatch):
    monkeypatch.delenv("FCC_DASHBOARD_STATIC_DIR", raising=False)
    result = get_static_dir()
    assert result.parts[-2:] == ("frontend", "dist")


def _make_fake_build(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>fake dashboard</body></html>", encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('fake')", encoding="utf-8")
    return dist


def test_mount_static_files_serves_index_at_root(tmp_path):
    dist = _make_fake_build(tmp_path)
    app = FastAPI()
    mount_static_files(app, static_dir=dist)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert "fake dashboard" in response.text


def test_mount_static_files_serves_assets(tmp_path):
    dist = _make_fake_build(tmp_path)
    app = FastAPI()
    mount_static_files(app, static_dir=dist)
    client = TestClient(app)

    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_mount_static_files_is_a_noop_when_directory_does_not_exist(tmp_path):
    missing = tmp_path / "does-not-exist"
    app = FastAPI()
    mount_static_files(app, static_dir=missing)
    client = TestClient(app)

    # No crash at mount time, and no route was added for "/" -- FastAPI's
    # own 404, not a 500, proves this degraded gracefully.
    response = client.get("/")
    assert response.status_code == 404
