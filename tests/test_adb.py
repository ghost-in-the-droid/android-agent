"""Tests for the Device.adb error contract (bots/common/adb.py).

The core guarantee under test: a failed adb call raises ADBError instead of
silently returning "" (the old phantom-success bug that every tool inherited).
The happy path (exit 0) is unchanged — it still returns stripped stdout — and
adb_soft() is the escape hatch for callers that tolerate a nonzero exit.
"""

import shutil
import subprocess

import pytest

from gitd.bots.common.adb import ADBError, ADBResult, Device


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_adb_success_returns_stripped_stdout(monkeypatch):
    """Exit 0 → stripped stdout, contract unchanged from before the fix."""
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompleted(0, "  hello\n", "")
    )
    assert Device("serial").adb("shell", "echo", "hello") == "hello"


def test_adb_nonzero_raises_adberror(monkeypatch):
    """Nonzero exit → ADBError carrying the exit code and stderr message."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(1, "", "error: device 'x' not found"),
    )
    with pytest.raises(ADBError) as exc:
        Device("x").adb("shell", "echo", "hi")
    assert exc.value.returncode == 1
    assert "not found" in str(exc.value)


def test_adberror_is_runtimeerror(monkeypatch):
    """ADBError must subclass RuntimeError so existing `except Exception` /
    `except RuntimeError` call sites keep degrading gracefully."""
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompleted(1, "", "boom")
    )
    with pytest.raises(RuntimeError):
        Device("x").adb("shell", "whatever")


def test_adb_missing_binary_raises_adberror(monkeypatch):
    """adb not on PATH → ADBError(127), never a silent empty string."""

    def _raise(*a, **k):
        raise FileNotFoundError("adb")

    monkeypatch.setattr(subprocess, "run", _raise)
    with pytest.raises(ADBError) as exc:
        Device("x").adb("devices")
    assert exc.value.returncode == 127


def test_adb_timeout_raises_adberror(monkeypatch):
    """A timeout is a hard failure → ADBError, not a swallowed TimeoutExpired."""

    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="adb", timeout=1)

    monkeypatch.setattr(subprocess, "run", _raise)
    with pytest.raises(ADBError):
        Device("x").adb("shell", "sleep", "5", timeout=1)


def test_adb_soft_does_not_raise_on_nonzero(monkeypatch):
    """adb_soft returns the result on a nonzero exit instead of raising."""
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompleted(1, "out", "err")
    )
    res = Device("x").adb_soft("shell", "cmd", "clipboard", "get-text")
    assert isinstance(res, ADBResult)
    assert res.returncode == 1
    assert res.stdout == "out"
    assert res.stderr == "err"
    assert res.ok is False


def test_adb_soft_ok_property(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompleted(0, "x", "")
    )
    assert Device("x").adb_soft("shell", "true").ok is True


@pytest.mark.skipif(shutil.which("adb") is None, reason="adb not installed")
def test_adb_real_bad_serial_raises():
    """End-to-end: a bogus serial against real adb raises ADBError.

    This is the acceptance test from the task — a failing adb command
    (unknown device) must raise with a meaningful message, not return "".
    """
    with pytest.raises(ADBError):
        Device("no-such-device-serial-xyz").adb("shell", "echo", "hi", timeout=5)
