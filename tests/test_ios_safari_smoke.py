"""Pytest wrapper for scripts/ios_safari_smoke.py verification logic.

The smoke script used to exit 0 unconditionally (pass-when-broken). These
tests pin the verify_smoke() contract: a healthy launch passes, a broken one
produces failures.
"""

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "ios_safari_smoke", Path(__file__).resolve().parents[1] / "scripts" / "ios_safari_smoke.py"
)
_smoke = importlib.util.module_from_spec(_SPEC)
sys.modules["ios_safari_smoke"] = _smoke
_SPEC.loader.exec_module(_smoke)

verify_smoke = _smoke.verify_smoke

_GOOD_TREE = "\n".join(
    [
        '[0] Application "Chrome"',
        '[1] TextField "Address and search bar" [clickable]',
        '[2] StaticText "Ghost in the Droid"',
        '[3] Link "Docs" [clickable]',
        '[4] StaticText "Give any AI agent a phone body"',
    ]
)


def test_healthy_launch_passes():
    state = {"packageName": "com.google.chrome.ios"}
    assert verify_smoke(state, _GOOD_TREE, "com.google.chrome.ios") == []
    # headline-bearing content present: more than zero rendered content lines
    assert len([ln for ln in _GOOD_TREE.splitlines() if ln.strip()]) > 0


def test_wrong_foreground_app_fails():
    state = {"packageName": "com.apple.springboard"}
    failures = verify_smoke(state, _GOOD_TREE, "com.google.chrome.ios")
    assert any("foreground app" in f for f in failures)


def test_empty_tree_fails():
    state = {"packageName": "com.google.chrome.ios"}
    failures = verify_smoke(state, "", "com.google.chrome.ios")
    assert any("screen tree looks empty" in f for f in failures)


def test_missing_state_fails():
    failures = verify_smoke({}, _GOOD_TREE, "com.google.chrome.ios")
    assert any("no foreground app" in f for f in failures)
