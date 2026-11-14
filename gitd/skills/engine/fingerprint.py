"""Fingerprint distance: how far a device is from the fingerprint a skill was authored against.

Fields: os, os_version, hardware, app_package, app_version. A skill value of ``*`` matches
anything; version fields take SemVer-style ranges (``>=1.4.0``, ``>=14 <16``, ``^1.4``, ``~1.4``,
``1.x``; a bare ``14`` is a prefix match, so it covers 14.1); hardware takes ``Manufacturer/Model`` with ``*`` on either side.
Distance = number of non-matching fields (0..5).

Rule (SKILL_SYSTEM.md section 11): 0 = hit, run. 1-2 = warn and run. 3+ = refuse unless the
caller forces it; the LLM "Adapt" tier is not implemented, so the refusal names the fields.
``--strict-fingerprint`` requires 0.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

FIELDS = ("os", "os_version", "hardware", "app_package", "app_version")
WARN_MAX = 2


@dataclass
class Distance:
    distance: int
    mismatches: list[str] = field(default_factory=list)
    skill: dict = field(default_factory=dict)
    device: dict = field(default_factory=dict)

    @property
    def tier(self) -> str:
        return "hit" if self.distance == 0 else "warn" if self.distance <= WARN_MAX else "refuse"

    def as_dict(self) -> dict:
        return {
            "distance": self.distance,
            "tier": self.tier,
            "mismatches": list(self.mismatches),
            "skill": dict(self.skill),
            "device": dict(self.device),
        }

    def summary(self) -> str:
        if not self.mismatches:
            return "fingerprint hit (distance 0)"
        parts = ", ".join(f"{k}: skill {self.skill.get(k)!r} vs device {self.device.get(k)!r}" for k in self.mismatches)
        return f"fingerprint distance {self.distance} ({parts})"


def _version_tuple(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in numbers) or (0,)


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    width = max(len(a), len(b))
    a, b = a + (0,) * (width - len(a)), b + (0,) * (width - len(b))
    return (a > b) - (a < b)


def version_matches(spec: str, actual: str) -> bool:
    """SemVer-ish range match; a spec of ``*`` or empty matches anything, an unparsable actual never matches a range."""
    spec = (spec or "*").strip()
    if spec == "*" or not spec:
        return True
    actual = (actual or "").strip()
    if not re.search(r"\d", actual):
        return False
    have = _version_tuple(actual)
    for clause in spec.replace(",", " ").split():
        if clause in {"*", "x", "X"}:
            continue
        m = re.fullmatch(r"(>=|<=|>|<|=|==|\^|~)?\s*(.+)", clause)
        op, want_text = (m.group(1) or ""), m.group(2)
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*\.(?:x|X|\*)", want_text):
            prefix = _version_tuple(want_text)
            if have[: len(prefix)] != prefix:
                return False
            continue
        want = _version_tuple(want_text)
        c = _cmp(have, want)
        if op in {"", "=", "=="}:
            if have[: len(want)] != want:  # bare spec is a prefix: `14` matches 14.1, `1.4.0` does not match 1.4.1
                return False
        elif op == ">=" and c < 0:
            return False
        elif op == ">" and c <= 0:
            return False
        elif op == "<=" and c > 0:
            return False
        elif op == "<" and c >= 0:
            return False
        elif op == "^":
            upper = (want[0] + 1,) if want[0] else (0, (want[1] if len(want) > 1 else 0) + 1)
            if c < 0 or _cmp(have, upper) >= 0:
                return False
        elif op == "~":
            upper = want[:1] + ((want[1] if len(want) > 1 else 0) + 1,)
            if c < 0 or _cmp(have, upper) >= 0:
                return False
    return True


def field_matches(name: str, skill_value: str, device_value: str) -> bool:
    skill_value = (skill_value or "*").strip()
    device_value = (device_value or "").strip()
    if skill_value == "*":
        return True
    if name in {"os_version", "app_version"}:
        return version_matches(skill_value, device_value)
    if name == "hardware":
        want = [p.strip().casefold() for p in skill_value.split("/", 1)] + ["*"]
        have = [p.strip().casefold() for p in device_value.split("/", 1)] + [""]
        return all(w == "*" or w == h for w, h in zip(want[:2], have[:2]))
    return skill_value.casefold() == device_value.casefold()


def distance(skill_fingerprint, device_fingerprint: dict) -> Distance:
    """Compare a skill's ``Fingerprint`` (dataclass or dict) with a concrete device fingerprint dict."""
    skill = {
        k: str(
            getattr(skill_fingerprint, k, None)
            if not isinstance(skill_fingerprint, dict)
            else skill_fingerprint.get(k) or "*"
        )
        for k in FIELDS
    }
    skill = {k: (v if v not in {"None", ""} else "*") for k, v in skill.items()}
    device = {k: str(device_fingerprint.get(k) or "") for k in FIELDS}
    mismatches = [k for k in FIELDS if not field_matches(k, skill[k], device[k])]
    return Distance(len(mismatches), mismatches, skill, device)


def probe_device(serial: str, app_package: str) -> dict | None:
    """Read-only device fingerprint for one app; None when the platform cannot be probed (iOS)."""
    if serial.startswith("fake:"):
        from gitd.skills.engine.fake_device import FakeDevice

        return dict(FakeDevice(serial).fingerprint)
    if serial.startswith("ios:"):
        return None

    def shell(*arguments: str) -> str:
        try:
            return subprocess.run(
                ["adb", "-s", serial, "shell", *arguments], check=True, capture_output=True, text=True, timeout=20
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Cannot probe device fingerprint: {exc}") from exc

    version = re.search(r"^\s*versionName=(\S+)", shell("dumpsys", "package", app_package), re.M)
    return {
        "os": "android",
        "os_version": shell("getprop", "ro.build.version.release"),
        "hardware": shell("getprop", "ro.product.manufacturer") + "/" + shell("getprop", "ro.product.model"),
        "app_package": app_package if version else "",
        "app_version": version.group(1) if version else "",
    }


def check(
    skill, serial: str, *, strict: bool = False, force: bool = False, device_fingerprint: dict | None = None
) -> Distance | None:
    """Probe the device (or take a supplied fingerprint) and apply the rule.

    Returns None when the device cannot be probed (iOS, adb unreachable) and the caller is not
    strict; raises ValueError when the run must not proceed.
    """
    authored = getattr(skill, "fingerprint", None)
    if authored is None:
        return None
    try:
        device = device_fingerprint if device_fingerprint is not None else probe_device(serial, authored.app_package)
    except (RuntimeError, OSError, ValueError) as exc:  # adb unreachable, missing fake fixture, bad profile
        if strict:
            raise ValueError(f"--strict-fingerprint: {exc}") from exc
        return None
    if device is None:
        if strict:
            raise ValueError("--strict-fingerprint: this device cannot be probed; pass --fingerprint <json>")
        return None
    result = distance(authored, device)
    if strict and result.distance:
        raise ValueError(f"--strict-fingerprint: {result.summary()}")
    if result.tier == "refuse" and not force:
        raise ValueError(
            f"{result.summary()}; the skill was authored for a different setup. "
            "Pass --force-fingerprint to run anyway (Adapt is not implemented)."
        )
    return result
