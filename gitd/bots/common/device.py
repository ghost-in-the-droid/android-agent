"""Platform-aware device factory.

Bare device refs remain Android ADB serials.  Refs with the ``ios:`` prefix are
handled by the Appium/WebDriverAgent iOS backend.

iOS support is feature-gated (dev-only for one release cycle): when
``settings.ios_platform_enabled`` is false and ``GITD_ENABLE_IOS`` is unset,
``ios:`` refs raise NotImplementedError and iOS devices are excluded from
discovery. The Android path is unaffected either way.
"""

from __future__ import annotations

import os

from gitd.bots.common.adb import Device, list_connected
from gitd.bots.common.ios import (
    IOS_PREFIX,
    IOSDevice,
    configured_ios_udids,
    discover_host_ios_devices,
    ios_config_for_udid,
    is_ios_ref,
    probe_ios_device,
)


def ios_enabled() -> bool:
    """Whether the iOS backend is enabled for this process."""
    if os.environ.get("GITD_ENABLE_IOS") == "1":
        return True
    from gitd.config import settings

    return settings.ios_platform_enabled


def _require_ios_enabled(device: str) -> None:
    if not ios_enabled():
        raise NotImplementedError(
            f"iOS device refs are not supported ({device}): iOS support is disabled. "
            "Set GITD_ENABLE_IOS=1 (or ios_platform_enabled=true in .env) to enable."
        )


def platform_for_device(device: str | None) -> str:
    return "ios" if is_ios_ref(device) else "android"


def get_device(device: str):
    if is_ios_ref(device):
        _require_ios_enabled(device)
        return IOSDevice(device)
    return Device(device)


def require_android_device(device: str, tool_name: str) -> None:
    if is_ios_ref(device):
        raise NotImplementedError(f"{tool_name} is Android-only and is not supported for iOS device refs")


def ios_refs_from_env() -> list[str]:
    if not ios_enabled():
        return []
    return [f"{IOS_PREFIX}{udid}" for udid in configured_ios_udids()]


def ios_refs_from_host() -> list[str]:
    if not ios_enabled():
        return []
    values = configured_ios_udids()
    values.extend(item["udid"] for item in discover_host_ios_devices(include_simulators=True))
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        udid = value.removeprefix(IOS_PREFIX) if isinstance(value, str) else str(value)
        if udid and udid not in seen:
            seen.add(udid)
            refs.append(f"{IOS_PREFIX}{udid}")
    return refs


def session_device_ref() -> str:
    """Optional process-local device scope (discovery filter and strict ref check); GHOST_DEVICE wins."""
    return os.environ.get("GHOST_DEVICE", "").strip() or os.environ.get("ANDROID_SERIAL", "").strip()


def list_configured_ios_devices(*, deep_probe: bool = False) -> list[dict]:
    selected = session_device_ref()
    if selected and not is_ios_ref(selected):
        return []
    if not ios_enabled():
        return []
    devices: list[dict] = []
    discovered = {item["udid"]: item for item in discover_host_ios_devices(include_simulators=True)}
    for ref in ios_refs_from_host():
        if selected and ref != selected:
            continue
        udid = ref.removeprefix(IOS_PREFIX)
        cfg = ios_config_for_udid(ref)
        host = discovered.get(udid, {})
        try:
            status = probe_ios_device(ref, deep=deep_probe).to_dict()
        except Exception as e:
            status = {
                "platform": "ios",
                "device": ref,
                "udid": udid,
                "state": "session_error",
                "message": str(e),
            }
        devices.append(
            {
                "serial": ref,
                "model": host.get("name") or cfg.device_name or "iOS device",
                "connection": "appium-wda",
                "platform": "ios",
                "source": host.get("source", "configured"),
                "host_state": host.get("state", ""),
                "status": status.get("state", "session_error"),
                "status_message": status.get("message", ""),
                "appium_url": status.get("appium_url", cfg.appium_url),
                "device_name": host.get("name") or cfg.device_name,
                "platform_version": cfg.platform_version or host.get("platform_version", ""),
                "bundle_id": cfg.bundle_id,
                "browser_name": cfg.browser_name,
                "wda_url": cfg.wda_url,
                "mjpeg_server_port": cfg.mjpeg_server_port,
                "mjpeg_settings": cfg.mjpeg_settings(),
                "details": status,
            }
        )
    return devices


def list_connected_device_refs() -> list[str]:
    selected = session_device_ref()
    devices: list[str] = []
    if not selected or not is_ios_ref(selected):
        try:
            devices.extend(list_connected())
        except Exception:
            pass
    if not selected or is_ios_ref(selected):
        devices.extend(ios_refs_from_host())
    return [ref for ref in devices if ref == selected] if selected else devices


class DeviceRefError(ValueError):
    """A device argument that is not a usable ref in this session's scope."""


_WRAPPERS = " \t\r\n\"'`"


def _clean_device_ref(raw: str) -> str:
    """Strip quotes/backticks/whitespace and any display suffix (" (model)", "  model=...")."""
    text = raw.strip(_WRAPPERS)
    parts = text.split(None, 1)
    return parts[0].strip(_WRAPPERS) if parts else ""


def _refused(raw: str, valid: list[str], why: str) -> DeviceRefError:
    ids = ", ".join(valid) if valid else "none (no devices connected)"
    hint = f' Pass only the id, e.g. device="{valid[0]}".' if valid else ""
    return DeviceRefError(f"device {raw!r} {why}. Valid device id(s): {ids}.{hint}")


def resolve_device_ref(raw):
    """Single normalizer for every device-taking entry point (MCP tools, agent tools, run_skill).

    With a session scope (GHOST_DEVICE/ANDROID_SERIAL) every non-empty ref, verbatim or
    recovered from a pasted display line, quotes or backticks, must be that scope or it is
    refused naming the valid id. Unscoped, a verbatim id passes untouched and a rewritten
    value must be a connected ref. "" means the caller's own default.
    """
    if not isinstance(raw, str):
        return raw
    candidate = _clean_device_ref(raw)
    if not candidate:
        return candidate
    scope = session_device_ref()
    if not scope and candidate == raw:
        return candidate
    valid = [scope] if scope else list_connected_device_refs()
    if candidate in valid:
        return candidate
    why = "is outside this session's device scope (GHOST_DEVICE)" if scope else "is not a connected device id"
    raise _refused(raw, valid, why)


def normalize_device_param(fn, *, param: str = "device", on_error=lambda exc, arguments: f"Error: {exc}"):
    """Decorator: resolve ``param`` through resolve_device_ref; keeps fn's signature for schemas."""
    import inspect
    from functools import wraps

    signature = inspect.signature(fn)
    if param not in signature.parameters:
        return fn

    @wraps(fn)
    def wrapper(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        if param in bound.arguments:
            try:
                bound.arguments[param] = resolve_device_ref(bound.arguments[param])
            except DeviceRefError as exc:
                return on_error(exc, bound.arguments)
        return fn(*bound.args, **bound.kwargs)

    return wrapper
