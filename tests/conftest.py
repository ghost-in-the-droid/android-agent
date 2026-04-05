"""
Shared test fixtures.

Device tests require a connected Android phone (set DEVICE env var).
API tests use FastAPI TestClient (no phone needed).
"""
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def dev():
    """ADB Device fixture — only for device tests."""
    from gitd.bots.common.adb import Device

    serial = os.environ.get("DEVICE", "")
    if not serial:
        pytest.skip("DEVICE env var not set — skipping device tests")
    return Device(serial)
