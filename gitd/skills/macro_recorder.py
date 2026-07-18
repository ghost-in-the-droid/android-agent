"""
Macro Record/Replay — records user actions on device and replays them.

Usage:
    recorder = MacroRecorder(device)
    recorder.start()
    # ... user interacts with device ...
    recorder.stop()
    recorder.save("my_macro.json")

    # Later:
    recorder.load("my_macro.json")
    recorder.replay()
"""
from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from gitd.bots.common.device import is_ios_ref

log = logging.getLogger(__name__)


@dataclass
class MacroStep:
    """Single recorded action."""
    action: str               # tap, swipe, type, back, home, wait
    timestamp: float = 0.0    # seconds since recording start
    params: dict = field(default_factory=dict)  # action-specific params
    element_info: dict | None = None  # optional element context from XML

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> MacroStep:
        return cls(**d)


@dataclass
class Macro:
    """A recorded sequence of actions."""
    name: str
    steps: list[MacroStep] = field(default_factory=list)
    device_serial: str = ""
    platform: str = ""
    app_package: str = ""
    ios_bundle_id: str = ""
    recorded_at: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "device_serial": self.device_serial,
            "platform": self.platform,
            "app_package": self.app_package,
            "ios_bundle_id": self.ios_bundle_id,
            "recorded_at": self.recorded_at,
            "duration_s": self.duration_s,
            "step_count": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Macro:
        steps = [MacroStep.from_dict(s) for s in d.get("steps", [])]
        return cls(
            name=d["name"],
            steps=steps,
            device_serial=d.get("device_serial", ""),
            platform=d.get("platform", ""),
            app_package=d.get("app_package", ""),
            ios_bundle_id=d.get("ios_bundle_id", ""),
            recorded_at=d.get("recorded_at", ""),
            duration_s=d.get("duration_s", 0.0),
        )

    def save(self, path: str | Path):
        """Save macro to JSON file."""
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))
        log.info(f"Saved macro '{self.name}' ({len(self.steps)} steps) to {path}")

    @classmethod
    def load(cls, path: str | Path) -> Macro:
        """Load macro from JSON file."""
        data = json.loads(Path(path).read_text())
        return cls.from_dict(data)


class MacroRecorder:
    """Records and replays sequences of device actions."""

    def __init__(self, dev: Any):
        self.dev = dev
        self._recording = False
        self._start_time = 0.0
        self._steps: list[MacroStep] = []

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self):
        """Start recording actions."""
        self._recording = True
        self._start_time = time.time()
        self._steps = []
        log.info("Recording started")

    def _app_identity(self) -> tuple[str, str]:
        try:
            state = self.dev.get_phone_state()
        except Exception:
            state = {}
        if not isinstance(state, dict):
            return "", ""
        package = (
            state.get("packageName")
            or state.get("package")
            or state.get("bundleId")
            or state.get("bundle_id")
            or state.get("currentApp")
            or ""
        )
        bundle_id = state.get("bundleId") or state.get("bundle_id") or ""
        return str(package or ""), str(bundle_id or "")

    def stop(self) -> Macro:
        """Stop recording and return the Macro."""
        self._recording = False
        duration = time.time() - self._start_time
        platform = "ios" if is_ios_ref(getattr(self.dev, "serial", "")) else "android"
        app_package, ios_bundle_id = self._app_identity()
        macro = Macro(
            name="recording",
            steps=self._steps.copy(),
            device_serial=self.dev.serial,
            platform=platform,
            app_package=app_package,
            ios_bundle_id=ios_bundle_id if platform == "ios" else "",
            recorded_at=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            duration_s=round(duration, 2),
        )
        log.info(f"Recording stopped: {len(self._steps)} steps, {duration:.1f}s")
        return macro

    def record_step(self, action: str, **params):
        """Manually record a step (used by wrapper methods)."""
        if not self._recording:
            return
        step = MacroStep(
            action=action,
            timestamp=round(time.time() - self._start_time, 3),
            params=params,
        )
        self._steps.append(step)

    # ── Recorded action wrappers ──────────────────────────────────────────

    def tap(self, x, y, delay=0.6):
        self.record_step("tap", x=x, y=y)
        self.dev.tap(x, y, delay=delay)

    def swipe(self, x1, y1, x2, y2, ms=500, delay=0.5):
        self.record_step("swipe", x1=x1, y1=y1, x2=x2, y2=y2, ms=ms)
        self.dev.swipe(x1, y1, x2, y2, ms=ms, delay=delay)

    def type_text(self, text: str, delay=0.3):
        self.record_step("type", text=text)
        if is_ios_ref(getattr(self.dev, "serial", "")) and hasattr(self.dev, "type_text"):
            self.dev.type_text(text)
        else:
            from gitd.bots.common.adb import input_text_arg

            self.dev.adb("shell", "input", "text", input_text_arg(text))
        time.sleep(delay)

    def back(self, delay=1.0):
        self.record_step("back")
        self.dev.back(delay=delay)

    def home(self, delay=0.5):
        self.record_step("home")
        if is_ios_ref(getattr(self.dev, "serial", "")) and hasattr(self.dev, "press_key"):
            self.dev.press_key("HOME")
        else:
            self.dev.adb("shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(delay)

    def _replay_back(self, delay: float = 0):
        if is_ios_ref(getattr(self.dev, "serial", "")) and hasattr(self.dev, "browser_back"):
            try:
                self.dev.browser_back(delay=delay)
                return
            except Exception:
                pass
        self.dev.back(delay=delay)

    def wait(self, seconds: float):
        self.record_step("wait", seconds=seconds)
        time.sleep(seconds)

    # ── Replay ────────────────────────────────────────────────────────────

    def replay(self, macro: Macro, speed: float = 1.0):
        """Replay a recorded macro. speed=2.0 plays at 2x speed."""
        log.info(f"Replaying '{macro.name}' ({len(macro.steps)} steps) at {speed}x speed")

        prev_ts = 0.0
        for i, step in enumerate(macro.steps):
            # Wait for relative timing
            wait_time = (step.timestamp - prev_ts) / speed
            if wait_time > 0.05:
                time.sleep(wait_time)
            prev_ts = step.timestamp

            action = step.action
            p = step.params

            log.info(f"  [{i+1}/{len(macro.steps)}] {action} {p}")

            if action == "tap":
                self.dev.tap(p["x"], p["y"], delay=0)
            elif action == "swipe":
                self.dev.swipe(p["x1"], p["y1"], p["x2"], p["y2"],
                              ms=p.get("ms", 500), delay=0)
            elif action == "type":
                if is_ios_ref(getattr(self.dev, "serial", "")) and hasattr(self.dev, "type_text"):
                    self.dev.type_text(p["text"])
                else:
                    from gitd.bots.common.adb import input_text_arg

                    self.dev.adb("shell", "input", "text", input_text_arg(p["text"]))
            elif action == "back":
                self._replay_back(delay=0)
            elif action == "home":
                if is_ios_ref(getattr(self.dev, "serial", "")) and hasattr(self.dev, "press_key"):
                    self.dev.press_key("HOME")
                else:
                    self.dev.adb("shell", "input", "keyevent", "KEYCODE_HOME")
            elif action == "wait":
                time.sleep(p.get("seconds", 1.0) / speed)
            else:
                log.warning(f"  Unknown action: {action}")

        log.info("Replay complete")
