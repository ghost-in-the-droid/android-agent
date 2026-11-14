"""Layer 1 — engine-global OS popup catalog.

Runs before every a11y-reading step in every skill. No per-skill config needed
for the common OS-level modals (permission dialogs, battery-opt, keyboard-default,
Google Play services, screen-recording confirmations).

Per-skill overrides via skill.yaml `os_popup_policy:`:
    os_popup_policy:
      allow_permissions: [storage, location]   # tap Allow for these
      deny_permissions:  [contacts]            # tap Deny (default)
      ignore: [google_play_update, keyboard_default]   # don't touch

Default policy = DENY everything (safest). Skills that need permissions must
opt-in explicitly.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger("skills.engine.os_popups")

# Permission dialog patterns (Android runtime perms). Each entry:
#   name: identifier for os_popup_policy allow/deny/ignore lists
#   detect: substring in a11y XML
#   allow_button: text of "grant" button
#   deny_button:  text of "deny" button (varies by Android version)
# Button labels differ by Android version: "Deny" (<=10), "Don’t allow" with a curly
# apostrophe (13+), and location/camera/mic grants as "While using the app" (11+).
_ALLOW = ["While using the app", "Allow", "Only this time"]
_DENY = ["Don’t allow", "Don't allow", "Deny"]

_PERMISSION_POPUPS = [
    {
        "name": "location",
        "detect": ["Allow precise location", "location for this app", "access this device's location"],
        "allow_button": _ALLOW,
        "deny_button": _DENY,
    },
    {
        "name": "contacts",
        "detect": ["access your contacts", "Allow.*to access your contacts"],
        "allow_button": _ALLOW,
        "deny_button": _DENY,
    },
    {
        "name": "storage",
        "detect": ["access photos, media", "files on your device", "access your photos"],
        "allow_button": _ALLOW,
        "deny_button": _DENY,
    },
    {
        "name": "camera",
        "detect": ["take pictures and record video", "access the Camera"],
        "allow_button": _ALLOW,
        "deny_button": _DENY,
    },
    {
        "name": "microphone",
        "detect": ["record audio", "access the microphone"],
        "allow_button": _ALLOW,
        "deny_button": _DENY,
    },
    {
        "name": "notifications",
        "detect": ["send you notifications", "post notifications"],
        "allow_button": _ALLOW,
        "deny_button": _DENY,
    },
]

# Non-permission OS popups — action depends on skill preference
_OTHER_OS_POPUPS = [
    {
        "name": "battery_optimization",
        "detect": ["Battery optimization", "Optimise battery usage", "Ignore optimization"],
        "dismiss_button": "Cancel",  # decline optimization changes
        "method": "button",
    },
    {
        "name": "google_play_update",
        "detect": ["Update Google Play services", "New version available"],
        "dismiss_button": "Not now",
        "method": "button",
    },
    {
        "name": "keyboard_default",
        "detect": ["Change your keyboard", "Set default input method", "Set as default"],
        "dismiss_button": "Cancel",
        "method": "button",
    },
    {
        "name": "screen_recording",
        "detect": ["Start recording or casting", "capture everything that's displayed"],
        "dismiss_button": "Start now",  # Ghost NEEDS this — allow
        "method": "button",
    },
    {
        "name": "immersive_mode_cling",
        "detect": ["Viewing full screen", "To exit, swipe down from the top"],
        "dismiss_button": "Got it",  # Android's one-time hint when an app goes immersive
        "method": "button",
    },
    {
        "name": "system_update",
        "detect": ["System update available", "Update your device"],
        "dismiss_button": "Later",
        "method": "button",
    },
]


def sweep(device, policy: dict | None = None) -> bool:
    """Run one OS-popup sweep. Returns True if any popup was dismissed.

    Args:
        device: Device wrapper (Android)
        policy: skill.yaml's os_popup_policy dict, or None for defaults
    """
    policy = policy or {}
    allow_perms = set(policy.get("allow_permissions") or [])
    deny_perms = set(policy.get("deny_permissions") or [])
    ignore = set(policy.get("ignore") or [])

    xml = _fast_dump(device)
    if not xml:
        return False
    return _sweep_xml(device, xml, allow_perms, deny_perms, ignore)


def sweep_if_system_dialog(device, policy: dict | None = None) -> bool:
    """Layer 1 for the runner: one cheap focus check per a11y-reading step; the tree is
    dumped and swept only when a system dialog (permission controller, package
    installer, system UI) owns focus."""
    serial = getattr(device, "serial", None)
    if not serial or getattr(device, "is_fake", False) or not _system_dialog_focused(serial):
        return False
    return sweep(device, policy)


def _system_dialog_focused(serial: str) -> bool:
    from gitd.bots.common.adb import Device
    try:
        package = Device(serial).foreground_package()
    except Exception:
        return False
    return package == "android" or any(
        owner in package for owner in _SYSTEM_DIALOG_OWNERS
    )


def _sweep_xml(device, xml, allow_perms, deny_perms, ignore) -> bool:

    # Permission popups
    for p in _PERMISSION_POPUPS:
        if p["name"] in ignore:
            continue
        if not any(re.search(pat, xml) for pat in p["detect"]):
            continue
        buttons = p["allow_button"] if p["name"] in allow_perms else p["deny_button"]  # default: deny
        for btn in ([buttons] if isinstance(buttons, str) else buttons):
            if _tap_button(device, xml, btn):
                log.info("os_popup [%s] tapped %r", p["name"], btn)
                return True

    # Other OS popups
    for p in _OTHER_OS_POPUPS:
        if p["name"] in ignore:
            continue
        if not any(pat in xml for pat in p["detect"]):
            continue
        btn = p.get("dismiss_button")
        if p.get("method") == "back":
            device.back() if hasattr(device, "back") else device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
            log.info("os_popup [%s] BACK dismissed", p["name"])
            return True
        elif btn and _tap_button(device, xml, btn):
            log.info("os_popup [%s] tapped %r", p["name"], btn)
            return True

    return False


_SYSTEM_DIALOG_OWNERS = ("permissioncontroller", "packageinstaller", "com.android.systemui")


def _fast_dump(device) -> str:
    """Tree for the sweep. Portal cannot see system permission dialogs, so when one of
    those owns focus (static, so uiautomator reaches idle fast) use uiautomator;
    otherwise use the engine's Portal-first dump."""
    from gitd.skills.engine.dispatch import _fast_dump as engine_dump, _uiautomator_dump

    serial = getattr(device, "serial", None)
    if serial and not getattr(device, "is_fake", False):
        if _system_dialog_focused(serial):
            xml = _uiautomator_dump(serial)
            if xml:
                return xml
    try:
        return engine_dump(device)
    except Exception:
        return ""


def _tap_button(device, xml: str, button_text: str) -> bool:
    """Tap the first element with matching text/content-desc. Returns True on tap."""
    pat = re.compile(
        rf'<node[^>]*(?:text|content-desc)="{re.escape(button_text)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
    )
    m = pat.search(xml)
    if not m:
        return False
    cx = (int(m.group(1)) + int(m.group(3))) // 2
    cy = (int(m.group(2)) + int(m.group(4))) // 2
    device.tap(cx, cy)
    return True
