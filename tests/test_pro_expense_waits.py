"""Bounded Pro Expense navigation regressions; fake UI time, no device/model calls."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SEQUENCE = json.loads((ROOT / "tests/fixtures/showcase-skills/pro-expense-waits.json").read_text())


def helper():
    spec = importlib.util.spec_from_file_location(
        "expense_wait_helpers", ROOT / "skillhub/androidworld/pro-expense/helpers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeUI:
    def __init__(
        self,
        h,
        monkeypatch,
        *,
        launch_delay=0,
        editor_delay=0,
        require_retap=False,
        never_editor=False,
        foreground=True,
    ):
        self.h = h
        self.now = 0
        self.launch_delay = launch_delay
        self.editor_delay = editor_delay
        self.require_retap = require_retap
        self.never_editor = never_editor
        self.foreground = foreground
        self.fab_taps = []
        self.saves = 0
        self.typed = []
        self.adb_calls = []
        monkeypatch.setattr(h.time, "monotonic", lambda: self.now)
        monkeypatch.setattr(h.time, "sleep", self.sleep)
        monkeypatch.setattr(h, "nodes", self.nodes)
        monkeypatch.setattr(h, "type_into", lambda _, rid, text: self.typed.append((rid, text)))
        monkeypatch.setattr(h, "select_category", lambda _, category: self.typed.append(("category", category)))

    def sleep(self, seconds):
        self.now += seconds
        assert self.now < 250, "polling exceeded the bounded recovery window"

    def node(self, rid, text=""):
        return {
            "id": rid,
            "text": text,
            "desc": "",
            "bounds": (0, 0, 100, 100) if rid == self.h.FAB else (0, 200, 100, 300),
        }

    def nodes(self, _):
        if self.now < self.launch_delay:
            return []
        if self.saves:
            return [self.node(self.h.FAB)]
        opened = self.fab_taps and self.now >= self.fab_taps[-1] + self.editor_delay
        if opened and not self.never_editor and (not self.require_retap or len(self.fab_taps) >= 2):
            return [self.node(self.h.NAME), self.node("save", "SAVE")]
        return [self.node(self.h.FAB)]

    def adb(self, *args):
        self.adb_calls.append(args)
        if "dumpsys" in " ".join(args):
            return SEQUENCE["expense_foreground" if self.foreground else "foreign_foreground"]
        if "monkey" in args:
            self.foreground = True
        return ""

    def tap(self, x, y, delay=0):
        assert self.foreground, "FAB must never be tapped while another app is foreground"
        if y == 50:
            self.fab_taps.append(self.now)
        else:
            self.saves += 1
        self.sleep(delay)


ROW = {"name": "Coffee", "amount": "4.50", "category": "Food", "note": "Morning"}


def test_launch_wait_accepts_home_after_old_twenty_second_limit(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch, launch_delay=SEQUENCE["launch_delay_seconds"])
    raw = yaml.safe_load((ROOT / "skillhub/androidworld/pro-expense/skill.yaml").read_text())
    steps = raw["subroutines"][0]["steps"][1]["retry"]["steps"]
    last = steps[-1]
    if "python_action" in last:
        assert h.wait_for_home(dev, {}, SimpleNamespace())["success"]
    else:
        h.wait_for(dev, h.FAB, last["timeout_s"])
    assert dev.now >= SEQUENCE["launch_delay_seconds"]


def test_post_fab_wait_accepts_editor_after_old_ten_second_limit(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch, editor_delay=SEQUENCE["editor_delay_seconds"])
    h.add_row(dev, ROW)
    assert len(dev.fab_taps) == 1 and dev.saves == 1
    assert dev.typed == [(h.NAME, "Coffee"), (h.AMOUNT, "4.50"), ("category", "Food"), (h.NOTE, "Morning")]


def test_post_fab_wait_retaps_once_if_still_on_home(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch, require_retap=True, editor_delay=SEQUENCE["editor_after_second_fab_seconds"])
    h.add_row(dev, ROW)
    assert len(dev.fab_taps) == 2 and dev.saves == 1
    assert dev.fab_taps[1] - dev.fab_taps[0] >= 30


def test_foreground_is_restored_before_fab_tap(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch, foreground=False)
    h.add_row(dev, ROW)
    assert any("dumpsys" in " ".join(c) for c in dev.adb_calls)
    assert any("monkey" in c for c in dev.adb_calls)
    assert dev.saves == 1


def test_editor_failure_stops_after_one_retap_without_typing_or_saving(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch, never_editor=True)
    with pytest.raises(RuntimeError, match="edt_name"):
        h.add_row(dev, ROW)
    assert len(dev.fab_taps) == 2
    assert 60 <= dev.now < 70
    assert dev.typed == [] and dev.saves == 0


def test_foreign_crash_dialogs_do_not_extend_wait_forever(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch)
    monkeypatch.setattr(h, "nodes", lambda _: [dev.node("android:id/aerr_close")])
    monkeypatch.setattr(h, "dismiss_foreign_crash", lambda *_: dev.sleep(1) or True)
    with pytest.raises(RuntimeError, match="fb_main_add"):
        h.wait_for(dev, h.FAB, timeout_s=5)
    assert dev.now <= 6


def test_editor_appearing_at_timeout_does_not_receive_second_tap(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch, editor_delay=31.5)
    h.add_row(dev, ROW)
    assert len(dev.fab_taps) == 1 and dev.saves == 1


def test_lost_foreground_prevents_fab_retry(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch, never_editor=True)
    tap = dev.tap

    def lose_foreground(*args):
        tap(*args)
        dev.foreground = False

    dev.tap = lose_foreground
    with pytest.raises(RuntimeError, match="edt_name"):
        h.add_row(dev, ROW)
    assert len(dev.fab_taps) == 1 and dev.saves == 0 and dev.typed == []


def test_top_resumed_activity_overrides_background_stack(monkeypatch):
    h = helper()
    dev = FakeUI(h, monkeypatch)
    dev.adb = lambda *_: (
        "topResumedActivity: ActivityRecord{u0 com.android.launcher3/.Launcher}\n" + SEQUENCE["expense_foreground"]
    )
    assert not h.in_foreground(dev)
