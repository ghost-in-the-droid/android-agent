"""Platform-aware device factory.

Bare device refs remain Android ADB serials.  Refs with the ``ios:`` prefix are
handled by the Appium/WebDriverAgent iOS backend.
"""
from __future__ import annotations

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


def platform_for_device(device: str | None) -> str:
    return "ios" if is_ios_ref(device) else "android"


def get_device(device: str):
    if is_ios_ref(device):
        return IOSDevice(device)
    return Device(device)


def require_android_device(device: str, tool_name: str) -> None:
    if is_ios_ref(device):
        raise NotImplementedError(f"{tool_name} is Android-only and is not supported for iOS device refs")


def ios_refs_from_env() -> list[str]:
    return [f"{IOS_PREFIX}{udid}" for udid in configured_ios_udids()]


def ios_refs_from_host() -> list[str]:
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


def list_configured_ios_devices(*, deep_probe: bool = False) -> list[dict]:
    devices: list[dict] = []
    discovered = {item["udid"]: item for item in discover_host_ios_devices(include_simulators=True)}
    for ref in ios_refs_from_host():
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
    devices: list[str] = []
    try:
        devices.extend(list_connected())
    except Exception:
        pass
    devices.extend(ios_refs_from_host())
    return devices
