"""Settings aggregates only; private preference screens are never opened or read."""
from __future__ import annotations

import re
import time

# Filtering runs ON the device: Wi-Fi identifiers never cross the ADB boundary.
WIFI_STATUS = """cmd wifi status | awk '
/[Ww]ifi is enabled/{print "enabled=true"}
/[Ww]ifi is disabled/{print "enabled=false"}
/[Ss]upplicant state: COMPLETED/{print "connected=true"}
/[Ss]upplicant state: (DISCONNECTED|INACTIVE|INTERFACE_DISABLED|UNINITIALIZED|SCANNING|ASSOCIATING|ASSOCIATED|FOUR_WAY_HANDSHAKE|GROUP_HANDSHAKE|DORMANT|INVALID)/{print "connected=false"}
'"""
BATTERY_STATUS = """dumpsys battery | awk '/^  (level|scale|status): [0-9]+$/{print $1, $2}'"""
STORAGE_TOTALS = """df -k /data | awk 'NR==2 && $2 ~ /^[0-9]+$/ && $3 ~ /^[0-9]+$/ && $4 ~ /^[0-9]+$/ {print $2, $3, $4}'"""


def _result(key, data, valid):
    if not valid:
        return {"success": False, "error": "Native aggregate unavailable or invalid"}
    return {"success": True, "data": {key: data}}


def close_settings(device, params, context):
    device.adb("shell", "am", "force-stop", "com.android.settings")
    device.adb("shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(1)
    return {"success": True}


def read_device_info(device, params, context):
    # Never enumerate getprop: only these three non-unique platform properties.
    keys = {"model": "ro.product.model", "android_version": "ro.build.version.release",
            "build_number": "ro.build.display.id"}
    info = {key: (device.adb("shell", "getprop", prop) or "").strip()
            for key, prop in keys.items()}
    return _result("device_info", info, _device_info_valid(info))


def read_battery(device, params, context):
    raw = device.adb("shell", BATTERY_STATUS) or ""
    fields = dict(re.findall(r"^(level|scale|status): ([0-9]+)$", raw, re.M))
    data = {}
    if set(fields) == {"level", "scale", "status"}:
        level, scale, status = (int(fields[k]) for k in ("level", "scale", "status"))
        if scale > 0 and 0 <= level <= scale and status in (2, 3, 4, 5):
            data = {"level_percent": round(100 * level / scale), "charging": status == 2}
    return _result("battery", data, _battery_valid(data))


def read_storage(device, params, context):
    raw = (device.adb("shell", STORAGE_TOTALS) or "").strip()
    data = {}
    if re.fullmatch(r"[0-9]+ [0-9]+ [0-9]+", raw):
        data = dict(zip(("total_kib", "used_kib", "free_kib"), map(int, raw.split())))
    return _result("storage", data, _storage_valid(data))


def read_wifi(device, params, context):
    raw = device.adb("shell", WIFI_STATUS) or ""
    values = {key: set(re.findall(r"^" + key + r"=(true|false)$", raw, re.M))
              for key in ("enabled", "connected")}
    # Disabled radio cannot have a current association; absence while enabled
    # is unknown, never silently interpreted as disconnected.
    if values["enabled"] == {"false"} and not values["connected"]:
        values["connected"] = {"false"}
    data = {key: next(iter(v)) == "true" for key, v in values.items() if len(v) == 1}
    valid = _wifi_valid(data) and not (data.get("connected") and not data.get("enabled"))
    return _result("wifi", data, valid)


def set_dark_theme(device, params, context):
    """Set Android's night-mode state independently of OEM switch labels."""
    want = bool(params.get("enabled"))
    current = night_mode(device)
    if current is None:
        return {"success": False, "error": "Automatic/custom or unreadable night-mode state; existing schedule preserved"}
    if current != want:
        device.adb("shell", "cmd", "uimode", "night", "yes" if want else "no")
    for _ in range(10):
        if night_mode(device) == want:
            return {"success": True, "data": {"dark_theme": want, "night_mode": "yes" if want else "no"}}
        time.sleep(.2)
    return {"success": False, "error": f"Android night mode did not reach enabled={want}"}


def night_mode(device):
    out = device.adb("shell", "cmd", "uimode", "night") or ""
    match = re.search(r"Night mode:\s*(yes|no)\b", out, re.I)
    return match.group(1).lower() == "yes" if match else None


def _device_info_valid(info):
    return set(info) == {"model", "android_version", "build_number"} and all(
        isinstance(v, str) and 0 < len(v) <= 256 and "\n" not in v for v in info.values())


def _battery_valid(data):
    return (set(data) == {"level_percent", "charging"}
            and type(data.get("level_percent")) is int and 0 <= data["level_percent"] <= 100
            and type(data.get("charging")) is bool)


def _storage_valid(data):
    return (set(data) == {"total_kib", "used_kib", "free_kib"}
            and all(type(v) is int and v >= 0 for v in data.values())
            and data["total_kib"] > 0
            and data["used_kib"] + data["free_kib"] <= data["total_kib"])


def _wifi_valid(data):
    return set(data) == {"enabled", "connected"} and all(type(v) is bool for v in data.values())


def device_info_ok(device, context):
    return _device_info_valid(context.result.get("device_info") or {})


def battery_ok(device, context):
    return _battery_valid(context.result.get("battery") or {})


def storage_ok(device, context):
    return _storage_valid(context.result.get("storage") or {})


def wifi_ok(device, context):
    data = context.result.get("wifi") or {}
    return _wifi_valid(data) and not (data["connected"] and not data["enabled"])


def dark_theme_matches(device, context):
    want = bool(context.params.get("enabled"))
    return context.result.get("dark_theme") is want and night_mode(device) == want
