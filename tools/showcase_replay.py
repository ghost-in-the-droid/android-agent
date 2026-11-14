"""Opt-in isolation protocol for owned showcase demo apps, never normal user runs.

The production run_action API intentionally preserves persistent user state. A
review harness must supply a verified fixture, recording context, and execution
callback for EACH action. It must not derive fixtures from the preceding action.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

DEMO_PACKAGES = frozenset(
    {
        "org.fossify.math",
        "com.google.android.deskclock",
        "net.gsantner.markor",
        "org.tasks",
        "com.arduia.expense",
    }
)
SNAPSHOT_DEMOS = frozenset({"org.fossify.math", "net.gsantner.markor", "org.tasks"})
CLOCK = "com.google.android.deskclock"


class ResetRefused(RuntimeError):
    """No capture or action may run when isolation cannot be established."""


@dataclass(frozen=True)
class ReplayCase:
    skill: str
    action: str
    package: str
    params: dict


class DemoReplay:
    def __init__(
        self,
        device,
        *,
        baseline_packages,
        installed_by_lane,
        snapshot_reset_packages=(),
        snapshot_name=None,
        sleep=time.sleep,
    ):
        self.device = device
        self.baseline = frozenset(baseline_packages)
        self.installed = frozenset(installed_by_lane)
        self.snapshot_packages = frozenset(snapshot_reset_packages)
        self.snapshot_name = snapshot_name
        self.sleep = sleep
        self.events = []

    def _event(self, event, **details):
        self.events.append({"event": event, "at": datetime.now(timezone.utc).isoformat(), **details})

    def _system_packages(self):
        lines = self.device.adb("shell", "pm", "list", "packages", "-s").splitlines()
        if not lines or any(line and not line.startswith("package:") for line in lines):
            raise ResetRefused("Cannot establish system-package inventory")
        return {line.removeprefix("package:").strip() for line in lines if line}

    def clear_demo(self, package):
        if package not in DEMO_PACKAGES:
            raise ResetRefused("Package is outside the five showcase demo apps")
        if package in self._system_packages():
            raise ResetRefused("Never pm clear a system app, including system Clock")
        owned_new = package in self.installed and package not in self.baseline
        snapshot_authorized = (
            bool(self.snapshot_name) and package in self.snapshot_packages and package in SNAPSHOT_DEMOS
        )
        if not (owned_new or snapshot_authorized):
            raise ResetRefused("App is not a new lane install or an explicitly snapshot-authorized demo")
        self.device.adb("shell", "am", "force-stop", package)
        self._event("force_stop", package=package)
        if self.device.adb("shell", "pm", "clear", package).strip() != "Success":
            raise ResetRefused("pm clear did not return Success")
        self._event("pm_clear", package=package, snapshot=self.snapshot_name if snapshot_authorized else None)

    def _home(self, package):
        # Also stop any fixture-seeding activity: the recorded action must launch
        # from HOME, even when a prerequisite calculation/task was seeded by UI.
        self.device.adb("shell", "am", "force-stop", package)
        self.device.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        self.device.adb("shell", "input", "keyevent", "KEYCODE_HOME")
        self.sleep(1)
        resolved = self.device.adb(
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.HOME",
        )
        components = re.findall(r"^([\w.]+/[\w.$]+)\s*$", resolved, re.M)
        if len(components) != 1:
            raise ResetRefused("Cannot resolve a unique HOME activity")
        launcher = components[0].split("/")[0]
        activities = self.device.adb("shell", "dumpsys", "activity", "activities")
        resumed = re.findall(r"(?:mResumedActivity|topResumedActivity)[^\n]*?\bu\d+\s+([\w.]+)/", activities)
        if not resumed or any(p != launcher for p in resumed):
            raise ResetRefused("HOME is not the confirmed resumed activity")
        windows = self.device.adb("shell", "dumpsys", "window")
        focused = re.findall(r"mCurrentFocus[^\n]*?\bu\d+\s+([\w.]+)/", windows)
        if not focused or any(package != launcher for package in focused):
            raise ResetRefused("HOME is obscured or does not own input focus")
        self._event("home_verified", launcher_package=launcher)

    def _launch(self, package):
        resolved = self.device.adb(
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            package,
        )
        components = re.findall(r"^([\w.]+/[\w.$]+)\s*$", resolved, re.M)
        if len(components) != 1 or components[0].split("/")[0] != package:
            raise ResetRefused("Cannot resolve the target demo launcher activity")
        response = self.device.adb("shell", "am", "start", "-W", "-n", components[0])
        if "Error" in response or "Exception" in response:
            raise ResetRefused("Demo launch failed")
        self.sleep(1)
        self._event("app_launched", package=package)

    def run(self, case, *, seed, execute, capture, ui_reset=None):
        """Run one isolated action; setup failures raise before recording starts.

        seed() returns {'verified': True, ...} only after its named minimal fixture
        has been checked. It must also reset external demo files (pm clear does not
        erase a Markor notebook). execute() runs the actual action, including app
        launch. capture() must start a real recorder and confirm it is running
        before yielding; it must stop/pull/remove its recording on exit.
        """
        self.events = []
        if ui_reset is not None:
            if case.package != CLOCK or CLOCK not in self._system_packages():
                raise ResetRefused("UI-reset exception is only for the emulator system Clock")
            self.device.adb("shell", "am", "force-stop", CLOCK)
            reset = ui_reset()
            if not isinstance(reset, dict) or reset.get("verified") is not True:
                raise ResetRefused("Clock UI reset was not verified")
            self._event("ui_reset_verified", **reset)
            reset_mode = "verified_ui_reset"
        else:
            self.clear_demo(case.package)
            reset_mode = "pm_clear"
        fixture = seed()
        if not isinstance(fixture, dict) or fixture.get("verified") is not True:
            raise ResetRefused("Minimal per-action fixture was not verified")
        self._event("seed_verified", fixture=fixture)
        self._home(case.package)
        with capture():
            self._event("capture_started")
            self.sleep(2)  # Preserve a visible HOME lead-in; never trim it out.
            self._launch(case.package)
            self._event("action_started")
            result = execute()
            self._event("action_finished")
            self.sleep(2)
        self._event("capture_stopped")
        return {
            "protocol_complete": True,
            "reset_mode": reset_mode,
            "fixture": fixture,
            "protocol": list(self.events),
            "result": result,
        }
