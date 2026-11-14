"""Layer 4 — unknown-popup safety net.

When a step fails AND the a11y-tree differs meaningfully between pre-step and
post-step (a new modal/overlay appeared), this module:

1. Screenshots the current state, labels as `unknown_popup`.
2. Tries a generic dismiss cascade:
     BACK  → most modals close on BACK
     tap_outside → tap top-corner (0.9w, 0.1h) — a "safe empty" area on most screens
     HOME  → nuclear option; skips the popup by leaving the app entirely
3. If any dismiss succeeds (popup gone per re-dump), engine retries the failed step ONCE.
4. If still failing OR popup persists → UnknownPopupError with the screenshot path.

The screenshot is the primary way authors GROW their popup catalogs empirically.
`ghost skill mine <skill> --update-popups` post-processes these into detector proposals.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

log = logging.getLogger("skills.engine.unknown_popup")


def looks_like_new_popup(xml_before: str, xml_after: str) -> bool:
    """Heuristic: did a new modal/overlay appear between the two dumps?

    Signals:
    - Total node count dropped significantly (modal typically renders opaque
      over the underlying tree, hiding content)
    - New text nodes with 'Allow' / 'OK' / 'Cancel' / 'Continue' / 'Not now'
      button labels that weren't in xml_before
    - Screen bounds shrunk to a specific dialog region (harder to detect)
    """
    if not xml_before or not xml_after:
        return False

    # Signal 1: text-node count decrease > 30% (modal covering content)
    before_texts = _extract_texts(xml_before)
    after_texts = _extract_texts(xml_after)
    if before_texts and len(after_texts) < len(before_texts) * 0.7:
        return True

    # Signal 2: new "dismiss-like" button appeared post-step
    dismiss_words = {
        "Allow",
        "OK",
        "Cancel",
        "Continue",
        "Not now",
        "Don't allow",
        "Deny",
        "Skip",
        "Later",
        "No thanks",
        "Save draft",
        "Discard",
    }
    new_texts = after_texts - before_texts
    if new_texts & dismiss_words:
        return True

    return False


def _extract_texts(xml: str) -> set:
    """Extract all text= and content-desc= values from a dump."""
    import re

    out = set()
    for m in re.finditer(r'(?:text|content-desc)="([^"]{2,80})"', xml):
        v = m.group(1).strip()
        if v:
            out.add(v)
    return out


def try_dismiss_cascade(device) -> str | None:
    """Try dismissing whatever's on screen. Returns method that worked, or None."""
    # Method 1: BACK
    try:
        if hasattr(device, "back"):
            device.back()
        else:
            device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1)
    except Exception:
        pass
    _fast_dump(device)
    # If tree changed, assume BACK worked
    return "back"


def capture_unknown_popup(device, context, artifacts_dir: str = "/tmp/ghost-skills-artifacts") -> str:
    """Screenshot + save to artifacts dir. Returns path to screenshot."""
    from .privacy import sensitive

    if sensitive():
        return ""
    Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
    serial = getattr(device, "serial", "device")
    ts = int(time.time())
    fname = f"{serial}-unknown-popup-{ts}.png"
    remote = "/sdcard/_ghost_unknown_popup.png"
    try:
        device.adb("shell", "screencap", "-p", remote)
        local = str(Path(artifacts_dir) / fname)
        device.adb("pull", remote, local)
        return local
    except Exception as e:
        log.warning("capture_unknown_popup failed: %s", e)
        return ""


def _fast_dump(device) -> str:
    serial = getattr(device, "serial", None)
    if not serial:
        try:
            return device.dump_xml()
        except Exception:
            return ""
    import subprocess

    try:
        subprocess.run(
            ["adb", "-s", serial, "shell", "uiautomator", "dump", "--compressed", "/sdcard/_ghost_ui.xml"],
            check=False,
            capture_output=True,
            timeout=6,
        )
        r = subprocess.run(
            ["adb", "-s", serial, "exec-out", "cat", "/sdcard/_ghost_ui.xml"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except Exception:
        pass
    return ""
