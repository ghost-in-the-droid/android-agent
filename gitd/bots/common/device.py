"""Platform-aware device factory.

Bare device refs remain Android ADB serials.  Refs with the ``ios:`` prefix are
handled by the Appium/WebDriverAgent iOS backend.
"""
from __future__ import annotations

import os

from gitd.bots.common.adb import Device, list_connected
from gitd.bots.common.ios import IOSDevice, IOS_PREFIX, is_ios_ref, strip_ios_prefix


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
    values: list[str] = []
    single = os.getenv("IOS_DEVICE_UDID", "").strip()
    if single:
        values.append(single)
    multi = os.getenv("IOS_DEVICE_UDIDS", "").strip()
    if multi:
        values.extend(v.strip() for v in multi.split(",") if v.strip())

    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        udid = strip_ios_prefix(value)
        if not udid or udid in seen:
            continue
        seen.add(udid)
        refs.append(f"{IOS_PREFIX}{udid}")
    return refs


def list_connected_device_refs() -> list[str]:
    devices: list[str] = []
    try:
        devices.extend(list_connected())
    except Exception:
        pass
    devices.extend(ios_refs_from_env())
    return devices
