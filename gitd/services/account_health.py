"""Account health — verify which TikTok account is logged in / active on a device.

Lives in the public gitd/ namespace so the scheduler can call it without
depending on the premium plugin. The actual UI automation (account switcher
navigation, etc.) lives in internal/ghost_premium/bots/tiktok/upload.py —
we delegate to it if installed, otherwise return a clean "not available"
result so public users see no crashes.

Public API:
    device_account_health(device)        → dict
    switch_active_account(device, handle) → dict
    sync_tiktok_accounts_table(device)    → dict
    all_devices_health()                  → list[dict]
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from gitd.bots.common.device import get_device, is_ios_ref

logger = logging.getLogger(__name__)

# Cache results briefly to avoid hammering the phone with full account-switcher
# navigations on every job preflight (each call takes 8-15s).
_CACHE_TTL_S = 60
_cache: dict[str, tuple[float, dict]] = {}
_TIKTOK_IOS_BUNDLE_ID = "com.zhiliaoapp.musically"
_HANDLE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9._]{2,30})")


def _ios_unsupported_result(device: str, *, action: str = "account_health") -> dict:
    if action == "account_switch":
        message = (
            "TikTok account switching is not implemented on iOS yet; "
            "iOS account health and sync use best-effort visible text detection."
        )
    else:
        message = "This TikTok account operation is not implemented on iOS yet"
    result = {
        "ok": False,
        "device": device,
        "platform": "ios",
        "error": "unsupported_platform",
        "message": message,
        "action": action,
        "checked_at": _now_iso(),
    }
    if action == "account_health":
        result.update({"active": None, "logged_in": [], "cached": False})
    return result


def _normalize_handle(value: str) -> str:
    return value.lstrip("@").strip().strip(".").lower()


def _ios_visible_text(dev, *, max_lines: int = 120) -> tuple[str, list[str]]:
    if hasattr(dev, "extract_visible_text"):
        text = dev.extract_visible_text(max_lines=max_lines)
    else:
        xml = dev.dump_xml()
        lines = []
        seen = set()
        if hasattr(dev, "nodes"):
            for node in dev.nodes(xml):
                parts = []
                for method_name in ("node_text", "node_content_desc", "node_rid"):
                    method = getattr(dev, method_name, None)
                    if method:
                        parts.append(method(node))
                label = " ".join(part for part in parts if part).strip()
                if label and label not in seen:
                    seen.add(label)
                    lines.append(label)
                if len(lines) >= max_lines:
                    break
        text = "\n".join(lines)
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()][:max_lines]
    return "\n".join(lines), lines


def _handles_from_text(text: str) -> list[str]:
    handles: list[str] = []
    seen: set[str] = set()
    for match in _HANDLE_RE.finditer(text or ""):
        handle = _normalize_handle(match.group(1))
        if not handle or handle in seen:
            continue
        seen.add(handle)
        handles.append(handle)
    return handles


def _ios_tiktok_account_health(device: str) -> dict:
    result = {
        "device": device,
        "platform": "ios",
        "ok": False,
        "active": None,
        "logged_in": [],
        "error": None,
        "cached": False,
        "checked_at": _now_iso(),
        "detection": {
            "method": "wda_visible_text",
            "bundle_id": _TIKTOK_IOS_BUNDLE_ID,
            "limitations": [
                "Best-effort iOS detection reads visible TikTok text; full account switcher enumeration is not implemented yet."
            ],
        },
    }
    try:
        dev = get_device(device)
        if hasattr(dev, "launch_app"):
            dev.launch_app(_TIKTOK_IOS_BUNDLE_ID)
            time.sleep(1)
        text, lines = _ios_visible_text(dev)
        handles = _handles_from_text(text)
        result["detection"].update(
            {
                "line_count": len(lines),
                "text_excerpt": "\n".join(lines[:20]),
            }
        )
        if not handles:
            result["error"] = "no visible TikTok account handle detected"
            return result
        result["ok"] = True
        result["active"] = handles[0]
        result["logged_in"] = handles
        return result
    except Exception as e:
        result["error"] = str(e)[:200]
        return result


def _premium_available() -> bool:
    """Whether the premium TikTok upload module is installed."""
    try:
        import ghost_premium.bots.tiktok.upload  # noqa: F401
        return True
    except ImportError:
        return False


def device_account_health(device: str, fresh: bool = False) -> dict:
    """Probe a device for its TikTok account state.

    Args:
        device: ADB serial or ios:<udid> device ref.
        fresh: If True, bypass the 60s cache.

    Returns:
        {
            "device": serial,
            "ok": bool,                  # True if detection succeeded
            "active": "handle" | None,   # currently active account
            "logged_in": ["h1", "h2"],   # all logged-in accounts
            "error": "..." | None,       # error message if detection failed
            "cached": bool,              # True if returned from cache
            "checked_at": iso_ts,
        }
    """
    if is_ios_ref(device):
        if not fresh:
            cached = _cache.get(device)
            if cached and time.time() - cached[0] < _CACHE_TTL_S:
                return {**cached[1], "cached": True}
        result = _ios_tiktok_account_health(device)
        _cache[device] = (time.time(), result)
        return result

    if not fresh:
        cached = _cache.get(device)
        if cached and time.time() - cached[0] < _CACHE_TTL_S:
            return {**cached[1], "cached": True}

    result = {
        "device": device,
        "platform": "android",
        "ok": False,
        "active": None,
        "logged_in": [],
        "error": None,
        "cached": False,
        "checked_at": _now_iso(),
    }

    if not _premium_available():
        result["error"] = "premium not installed"
        return result

    try:
        from ghost_premium.bots.tiktok.upload import get_logged_in_accounts
        accounts = get_logged_in_accounts(device=device)
    except Exception as e:
        result["error"] = str(e)[:200]
        _cache[device] = (time.time(), result)
        return result

    result["ok"] = True
    result["logged_in"] = [a["handle"] for a in accounts]
    active = next((a["handle"] for a in accounts if a.get("active")), None)
    result["active"] = active
    _cache[device] = (time.time(), result)
    return result


def switch_active_account(device: str, handle: str) -> dict:
    """Switch the TikTok active account on the device to `handle`.

    Args:
        device: ADB serial or ios:<udid> device ref.
        handle: Target username (with or without @).

    Returns:
        {"ok": bool, "device": serial, "active": handle | None, "error": str | None}
    """
    handle = handle.lstrip("@").strip()
    if is_ios_ref(device):
        result = _ios_unsupported_result(device, action="account_switch")
        result.update({"active": None, "target": handle})
        return result
    if not _premium_available():
        return {"ok": False, "device": device, "platform": "android", "active": None, "error": "premium not installed"}

    # First check if already active — save 10+ seconds
    health = device_account_health(device, fresh=True)
    if health["active"] == handle:
        return {"ok": True, "device": device, "active": handle, "error": None}
    if not health["ok"]:
        return {"ok": False, "device": device, "active": None, "error": f"can't detect state: {health['error']}"}
    if handle not in health["logged_in"]:
        return {
            "ok": False,
            "device": device,
            "active": health["active"],
            "error": f"@{handle} not logged in on this device (have: {health['logged_in']})",
        }

    try:
        from ghost_premium.bots.tiktok.upload import switch_account
        switch_account(handle, device=device)
    except Exception as e:
        return {"ok": False, "device": device, "active": health["active"], "error": str(e)[:200]}

    # Invalidate cache and re-probe
    _cache.pop(device, None)
    after = device_account_health(device, fresh=True)
    return {
        "ok": after["active"] == handle,
        "device": device,
        "active": after["active"],
        "error": None if after["active"] == handle else f"switch attempted but active is still @{after['active']}",
    }


def _sync_detected_accounts(device: str, health: dict) -> dict:
    if not health["ok"]:
        return {
            "ok": False,
            "device": device,
            "platform": health.get("platform") or ("ios" if is_ios_ref(device) else "android"),
            "added": [],
            "updated": [],
            "active": None,
            "error": health["error"],
        }

    from gitd.db import DEFAULT_DB, get_connection, create_tables

    conn = get_connection(DEFAULT_DB)
    create_tables(conn)

    added, updated = [], []
    active_handle = health["active"]
    for handle in health["logged_in"]:
        existing = conn.execute(
            "SELECT handle, phone_serial FROM tiktok_accounts WHERE handle=?", (handle,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO tiktok_accounts (handle, phone_serial, is_active) VALUES (?, ?, 1)",
                (handle, device),
            )
            added.append(handle)
        elif existing["phone_serial"] != device:
            conn.execute(
                "UPDATE tiktok_accounts SET phone_serial=?, is_active=1 WHERE handle=?",
                (device, handle),
            )
            updated.append(handle)
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "device": device,
        "platform": health.get("platform") or ("ios" if is_ios_ref(device) else "android"),
        "added": added,
        "updated": updated,
        "active": active_handle,
        "error": None,
    }


def sync_tiktok_accounts_table(device: str) -> dict:
    """Refresh the tiktok_accounts DB table to match what's actually on the device.

    On iOS this uses best-effort visible text account detection; it can only
    sync accounts that are visible to WDA/Appium at probe time.

    For each logged-in handle on `device`:
      - Upsert (handle, phone_serial, is_active=1)
      - If the row already exists with a different phone_serial, update it
        (an account is "where it was last seen logged in").

    Returns:
        {"ok": bool, "device": serial, "added": [...], "updated": [...], "active": "...", "error": str | None}
    """
    if is_ios_ref(device):
        health = device_account_health(device, fresh=True)
        return _sync_detected_accounts(device, health)

    health = device_account_health(device, fresh=True)
    return _sync_detected_accounts(device, health)


def all_devices_health() -> list[dict]:
    """Probe every connected Android device and configured iOS device ref."""
    from gitd.bots.common.adb import list_connected
    from gitd.bots.common.device import ios_refs_from_host

    devices: list[str] = []
    seen: set[str] = set()
    for serial in [*list_connected(), *ios_refs_from_host()]:
        if serial and serial not in seen:
            seen.add(serial)
            devices.append(serial)
    return [device_account_health(serial) for serial in devices]


def expected_account_matches(device: str, expected: Optional[str]) -> dict:
    """Lightweight pre-flight check for the scheduler.

    Args:
        device: ADB serial.
        expected: Handle the job expects to run as (without @). None = no check.

    Returns:
        {"ok": bool, "reason": str | None, "active": handle, "expected": expected}

        ok=True when:
          - expected is None / empty (job doesn't care)
          - or detection succeeded and active matches expected
        ok=False when:
          - active is detected but different
        ok=True with reason set ("undetectable") when:
          - premium not installed
          - or detection failed (we don't block jobs on detection failures —
            log warning and let job try, since false-blocks are worse than
            false-allows here)
    """
    if not expected:
        return {"ok": True, "reason": None, "active": None, "expected": expected}

    expected_clean = expected.lstrip("@").strip()
    if is_ios_ref(device):
        health = device_account_health(device)
        if not health["ok"]:
            return {
                "ok": True,
                "reason": f"undetectable: {health['error']}",
                "active": None,
                "expected": expected_clean,
            }
        active = _normalize_handle(health["active"] or "")
        if active == _normalize_handle(expected_clean):
            return {"ok": True, "reason": None, "active": active, "expected": expected_clean}
        return {
            "ok": False,
            "reason": f"wrong active account: have @{active or '?'}, expected @{expected_clean}",
            "active": active,
            "expected": expected_clean,
        }

    health = device_account_health(device)

    if not health["ok"]:
        return {
            "ok": True,
            "reason": f"undetectable: {health['error']}",
            "active": None,
            "expected": expected_clean,
        }

    active = (health["active"] or "").lstrip("@").strip()
    if active == expected_clean:
        return {"ok": True, "reason": None, "active": active, "expected": expected_clean}

    return {
        "ok": False,
        "reason": f"wrong active account: have @{active or '?'}, expected @{expected_clean}",
        "active": active,
        "expected": expected_clean,
    }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
