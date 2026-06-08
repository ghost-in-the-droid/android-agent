"""Platform-aware device factory.

Bare device refs remain Android ADB serials.  Refs with the ``ios:`` prefix are
handled by the Appium/WebDriverAgent iOS backend.
"""
from __future__ import annotations

from gitd.bots.common.adb import Device, list_connected
from gitd.bots.common.ios import (
    IOSDevice,
    IOS_PREFIX,
    configured_ios_udids,
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


def list_configured_ios_devices(*, deep_probe: bool = False) -> list[dict]:
    devices: list[dict] = []
    for ref in ios_refs_from_env():
        cfg = ios_config_for_udid(ref)
        try:
            status = probe_ios_device(ref, deep=deep_probe).to_dict()
        except Exception as e:
            status = {
                "platform": "ios",
                "device": ref,
                "udid": ref.removeprefix(IOS_PREFIX),
                "state": "session_error",
                "message": str(e),
            }
        devices.append(
            {
                "serial": ref,
                "model": cfg.device_name or "iOS device",
                "connection": "appium-wda",
                "platform": "ios",
                "status": status.get("state", "session_error"),
                "status_message": status.get("message", ""),
                "appium_url": status.get("appium_url", cfg.appium_url),
                "device_name": cfg.device_name,
                "platform_version": cfg.platform_version,
                "bundle_id": cfg.bundle_id,
                "browser_name": cfg.browser_name,
                "wda_url": cfg.wda_url,
                "mjpeg_server_port": cfg.mjpeg_server_port,
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
    devices.extend(ios_refs_from_env())
    return devices
