"""
Shared test fixtures.

Device tests require a connected Android phone (set DEVICE env var).
API tests use FastAPI TestClient (no phone needed).
"""

import os
import tempfile
from pathlib import Path

import pytest

# ── Test DB isolation (must run at conftest import, before any gitd import) ───
# gitd.models.base builds its SQLAlchemy engine bound to settings.db_path AT
# IMPORT TIME, and `settings` is created the first time gitd.config is imported.
# So the ONLY place we can redirect the DB is here, at conftest import — pytest
# loads conftest before collecting/importing any test module that pulls in gitd.
# Without this, trace tests (which insert and DELETE trace rows) run against the
# real data/gitd.db and wipe live rows. This module does NOT import gitd, so the
# env var is set first.
if "DB_PATH" not in os.environ:
    _TEST_DB = Path(tempfile.gettempdir()) / "gitd_pytest.db"
    # Start each test session from a clean slate (drop WAL/SHM sidecars too).
    for _suffix in ("", "-wal", "-shm"):
        Path(str(_TEST_DB) + _suffix).unlink(missing_ok=True)
    os.environ["DB_PATH"] = str(_TEST_DB)


@pytest.fixture(scope="session", autouse=True)
def _verify_db_isolated():
    """Fail loudly if the app DB wasn't redirected to the throwaway test DB.

    If anything imported gitd before this conftest set DB_PATH, the module-level
    engine would still point at the real dev DB and the trace tests would wipe
    it. This guard turns that silent data-loss into an immediate, obvious error.
    """
    from gitd.models.base import engine

    engine_url = str(engine.url)
    db_path = os.environ.get("DB_PATH", "")
    real_db = "data/gitd.db"  # the production default in gitd/config.py
    assert db_path and db_path in engine_url and real_db not in engine_url, (
        f"Test DB isolation failed: engine is bound to {engine_url!r} (DB_PATH="
        f"{db_path!r}), expected a throwaway temp DB and definitely NOT {real_db}. "
        "Something imported gitd before conftest set DB_PATH — do NOT run this "
        "suite, it would touch the real dev DB."
    )
    yield


@pytest.fixture(scope="session")
def dev():
    """ADB Device fixture — only for device tests."""
    from gitd.bots.common.adb import Device

    serial = os.environ.get("DEVICE", "")
    if not serial:
        pytest.skip("DEVICE env var not set — skipping device tests")
    return Device(serial)
