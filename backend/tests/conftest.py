"""Shared pytest fixtures for backend API tests."""

import pytest

from fcc_dashboard.api import app


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()
