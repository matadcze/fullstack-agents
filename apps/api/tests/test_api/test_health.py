"""Tests for health and root endpoints."""

import os

# Provide minimal defaults so the app can start in test environments
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "changeme-in-tests")

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import create_app  # noqa: E402
from src.core.config import settings  # noqa: E402

client = TestClient(create_app())


def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == settings.app_name
    assert data["version"] == settings.app_version
    assert data["status"] == "running"
