"""Shared fixtures for API smoke tests."""
import pytest
from fastapi.testclient import TestClient

from gitd.app import app


@pytest.fixture(scope="session")
def client():
    """FastAPI test client — no real server needed."""
    with TestClient(app) as c:
        yield c
