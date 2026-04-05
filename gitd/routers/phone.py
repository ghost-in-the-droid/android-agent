"""Phone admin routes: devices, nickname, input, tap, type, back, key, etc."""

import base64
import io
import re
import subprocess

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from gitd.models.base import get_db

router = APIRouter(prefix="/api/phone", tags=["phone"])

import time as _time
_last_wifi_reconnect: float = 0


def _try_wifi_reconnect(db: Session):
    """Try reconnecting known WiFi devices that aren't currently connected (max once per 30s)."""
    global _last_wifi_reconnect
    if _time.time() - _last_wifi_reconnect < 30:
        return
    _last_wifi_reconnect = _time.time()

    try:
        # Get currently connected serials
        out = subprocess.check_output(["adb", "devices"], timeout=3).decode()
        connected = {line.split()[0] for line in out.strip().split("\n")[1:] if "device" in line}

        # Get known WiFi devices from DB
        rows = db.execute(text(
            "SELECT wifi_ip, wifi_port FROM phones WHERE wifi_ip IS NOT NULL AND wifi_port IS NOT NULL"
        )).fetchall()

        for ip, port in rows:
            addr = f"{ip}:{port}"
            if addr not in connected:
                # Try connecting in background (non-blocking, 2s timeout)
                subprocess.Popen(
                    ["adb", "connect", addr],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
    except Exception:
        pass


@router.get("/devices", summary="List Connected Phone Devices")
def phone_devices(db: Session = Depends(get_db)):
    """List ADB-connected devices with model info and nicknames."""
    try:
        # Try reconnecting known WiFi devices that aren't currently connected
        _try_wifi_reconnect(db)

        out = subprocess.check_output(["adb", "devices", "-l"], timeout=5).decode()
        devices = []
        for line in out.strip().split("\n")[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2 or parts[1] not in ("device", "recovery", "sideload"):
                continue
            serial = parts[0]
            model = ""
            if "model:" in line:
                model = line.split("model:")[1].split()[0].replace("_", " ")
            now_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            is_wifi = ":" in serial

            # Save WiFi IP to DB for auto-reconnect
            wifi_ip = serial.split(":")[0] if is_wifi else None
            wifi_port = int(serial.split(":")[1]) if is_wifi and ":" in serial else None
            conn_type = "wifi" if is_wifi else "usb"

            if is_wifi:
                # For WiFi devices, also update the USB entry if we know the model
                db.execute(text("""
                    UPDATE phones SET wifi_ip=:ip, wifi_port=:port, connection_type=:conn
                    WHERE model=:model AND wifi_ip IS NULL
                """), {"ip": wifi_ip, "port": wifi_port, "conn": conn_type, "model": model})

            db.execute(text("""
                INSERT INTO phones (serial, model, first_seen, last_seen, wifi_ip, wifi_port, connection_type)
                VALUES (:serial, :model, :now, :now, :ip, :port, :conn)
                ON CONFLICT(serial) DO UPDATE SET model=:model, last_seen=:now,
                    wifi_ip=COALESCE(:ip, wifi_ip), wifi_port=COALESCE(:port, wifi_port),
                    connection_type=:conn
            """), {"serial": serial, "model": model, "now": now_str,
                   "ip": wifi_ip, "port": wifi_port, "conn": conn_type})
            db.commit()
            devices.append({"serial": serial, "model": model or serial, "connection": conn_type})

        # Deduplicate: if same model has both USB and WiFi, keep USB only
        usb_models = {d["model"] for d in devices if d["connection"] == "usb"}
        devices = [d for d in devices if d["connection"] == "usb" or d["model"] not in usb_models]

        registry_rows = db.execute(text("SELECT * FROM phones")).mappings().all()
        registry = {r["serial"]: dict(r) for r in registry_rows}
        for d in devices:
            d["nickname"] = registry.get(d["serial"], {}).get("nickname", "")
        return {"devices": devices}
    except Exception as e:
        return {"devices": [], "error": str(e)}


@router.post("/nickname", summary="Set Phone Nickname")
def phone_nickname(data: dict = Body({}), db: Session = Depends(get_db)):
    """Set a display nickname for a phone by serial."""
    serial = data.get("serial", "").strip()
    nickname = data.get("nickname", "").strip()
    if not serial:
        return {"ok": False, "error": "serial required"}
    db.execute(
        text("UPDATE phones SET nickname = :nickname WHERE serial = :serial"), {"nickname": nickname, "serial": serial}
    )
    db.commit()
    return {"ok": True}


@router.post("/input", summary="Send Input To Phone")
def phone_input(data: dict = Body({})):
    """Send a tap, swipe, keyevent, or text input to a device."""
    device = data.get("device")
    action = data.get("action")
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    try:
        if action == "tap":
            cmd += ["shell", "input", "tap", str(int(data["x"])), str(int(data["y"]))]
        elif action == "swipe":
            dur = int(data.get("duration", 300))
            cmd += [
                "shell",
                "input",
                "swipe",
                str(int(data["x1"])),
                str(int(data["y1"])),
                str(int(data["x2"])),
                str(int(data["y2"])),
                str(dur),
            ]
        elif action == "keyevent":
            cmd += ["shell", "input", "keyevent", str(data["keycode"])]
        elif action == "text":
            cmd += ["shell", "input", "text", data["text"]]
        else:
            return {"ok": False, "error": "unknown action"}
        subprocess.check_output(cmd, timeout=6)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/elements/{device}", summary="Get Phone UI Elements")
def api_phone_elements(device: str):
    """Get interactive UI elements from device screen."""
    from gitd.services.device_context import get_interactive_elements
    elements = get_interactive_elements(device)
    return {"elements": elements, "count": len(elements)}


@router.post("/tap", summary="Tap On Phone Screen")
def api_phone_tap(data: dict = Body({})):
    """Tap at coordinates or send a keyevent to a device."""
    from gitd.bots.common.adb import Device

    dev = Device(data.get("device", ""))
    if data.get("keyevent"):
        dev.adb("shell", "input", "keyevent", data["keyevent"])
    else:
        x, y = int(data.get("x", 0)), int(data.get("y", 0))
        stream_w = int(data.get("stream_w", 0))
        stream_h = int(data.get("stream_h", 0))
        if stream_w and stream_h:
            try:
                out = dev.adb("shell", "wm", "size", timeout=3)
                m = re.search(r"(\d+)x(\d+)", out)
                if m:
                    real_w, real_h = int(m.group(1)), int(m.group(2))
                    x = int(x * real_w / stream_w)
                    y = int(y * real_h / stream_h)
            except Exception:
                pass
        dev.tap(x, y)
    return {"ok": True}


@router.post("/type", summary="Type Text On Phone")
def api_phone_type(data: dict = Body({})):
    """Type text into the focused input field on a device."""
    from gitd.bots.common.adb import Device

    dev = Device(data.get("device", ""))
    text_val = data.get("text", "").replace(" ", "%s")
    dev.adb("shell", "input", "text", text_val)
    return {"ok": True}


@router.post("/back", summary="Press Back Button")
def api_phone_back(data: dict = Body({})):
    """Press the Android back button on a device."""
    from gitd.bots.common.adb import Device

    dev = Device(data.get("device", ""))
    dev.back(delay=0.3)
    return {"ok": True}


@router.post("/key", summary="Send Keyevent To Phone")
def api_phone_key(data: dict = Body({})):
    """Send a keyevent to device."""
    from gitd.bots.common.adb import Device

    dev = Device(data.get("device", ""))
    key = data.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    if not key.startswith("KEYCODE_"):
        key = "KEYCODE_" + key
    dev.adb("shell", "input", "keyevent", key)
    return {"ok": True}


@router.post("/launch", summary="Launch App On Phone")
def api_phone_launch(data: dict = Body({})):
    """Launch an app by package name on a device."""
    from gitd.bots.common.adb import Device

    dev = Device(data.get("device", ""))
    pkg = data.get("package", "")
    dev.adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    return {"ok": True}


@router.post("/reconnect/{device}", summary="Reconnect Phone Portal")
def api_phone_reconnect(device: str):
    """Clear Portal cache for a device and re-establish connection."""
    from gitd.bots.common.adb import Device

    dev = Device(device)
    port = dev._ensure_portal_forward(force=True)
    if port:
        return {"ok": True, "port": port}
    raise HTTPException(status_code=500, detail="Portal not reachable")


@router.post("/force-stop", summary="Force Stop App On Phone")
def api_phone_force_stop(data: dict = Body({})):
    """Force-stop an app by package name on a device."""
    from gitd.bots.common.adb import Device

    dev = Device(data.get("device", ""))
    pkg = data.get("package", "")
    if not pkg:
        raise HTTPException(status_code=400, detail="package required")
    dev.adb("shell", "am", "force-stop", pkg)
    return {"ok": True}


@router.post("/swipe", summary="Swipe On Phone Screen")
def api_phone_swipe(data: dict = Body({})):
    """Perform a swipe gesture on a device with coordinate scaling."""
    from gitd.bots.common.adb import Device

    dev = Device(data.get("device", ""))
    x1, y1 = int(data.get("x1", 540)), int(data.get("y1", 1600))
    x2, y2 = int(data.get("x2", 540)), int(data.get("y2", 400))
    stream_w = int(data.get("stream_w", 0))
    stream_h = int(data.get("stream_h", 0))
    if stream_w and stream_h:
        try:
            out = dev.adb("shell", "wm", "size", timeout=3)
            m = re.search(r"(\d+)x(\d+)", out)
            if m:
                real_w, real_h = int(m.group(1)), int(m.group(2))
                x1 = int(x1 * real_w / stream_w)
                y1 = int(y1 * real_h / stream_h)
                x2 = int(x2 * real_w / stream_w)
                y2 = int(y2 * real_h / stream_h)
        except Exception:
            pass
    dev.swipe(x1, y1, x2, y2)
    return {"ok": True}


@router.get("/screenshot/{device}", summary="Take Phone Screenshot")
def api_phone_screenshot(device: str):
    """Take screenshot, return as base64 JPEG."""
    from gitd.services.device_context import screenshot
    result = screenshot(device)
    return {"ok": True, **result}


@router.get("/screenshot-annotated/{device}", summary="Take Annotated Screenshot")
def api_phone_screenshot_annotated(device: str):
    """Take screenshot with Portal's numbered element overlay."""
    from gitd.services.device_context import screenshot_annotated
    result = screenshot_annotated(device)
    return {"ok": True, **result}


@router.get("/screenshot-crop/{device}", summary="Take Cropped Screenshot")
def api_phone_screenshot_crop(device: str, x1: int = 0, y1: int = 0, x2: int = 1080, y2: int = 2400):
    """Take a cropped screenshot of a specific screen region."""
    from gitd.services.device_context import screenshot_cropped
    result = screenshot_cropped(device, x1, y1, x2, y2)
    return {"ok": True, **result}


@router.get("/xml/{device}", summary="Dump Phone UI XML")
def api_phone_xml(device: str):
    """Dump current UI XML."""
    from gitd.services.device_context import get_screen_xml
    xml = get_screen_xml(device)
    return {"ok": True, "xml": xml[:10000], "length": len(xml)}


@router.get("/screen-tree/{device}", summary="Get LLM-Readable Screen Tree")
def api_phone_screen_tree(device: str):
    """Get indented UI hierarchy optimized for LLM consumption."""
    from gitd.services.device_context import get_screen_tree
    return {"ok": True, "tree": get_screen_tree(device)}


@router.get("/ocr/{device}", summary="OCR Phone Screen")
def api_phone_ocr(device: str, x1: int = 0, y1: int = 0, x2: int = 0, y2: int = 0):
    """OCR the screen (or a region if x1/y1/x2/y2 provided). Returns text with positions."""
    from gitd.services.device_context import ocr_screen, ocr_region
    if x1 or y1 or x2 or y2:
        texts = ocr_region(device, x1, y1, x2, y2)
    else:
        texts = ocr_screen(device)
    return {"ok": True, "texts": texts, "count": len(texts)}


@router.get("/classify/{device}", summary="Classify Phone Screen")
def api_phone_classify(device: str):
    """Classify current screen type (home, search, dialog, error, etc.)."""
    from gitd.services.device_context import classify_screen
    return classify_screen(device)


@router.post("/overlay/{device}", summary="Toggle Phone Overlay")
def api_phone_overlay(device: str, data: dict = Body({})):
    """Toggle Droidrun Portal overlay on/off."""
    import json as _json
    import urllib.request

    from gitd.bots.common.adb import Device

    dev = Device(device)
    port = dev._ensure_portal_forward()
    if not port:
        raise HTTPException(status_code=500, detail="Portal not available")
    visible = data.get("visible", True)
    try:
        payload = _json.dumps({"visible": visible}).encode()
        req = urllib.request.Request(
            f"http://localhost:{port}/overlay",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = _json.loads(urllib.request.urlopen(req, timeout=3).read())
        return {"ok": True, "result": resp.get("result", "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/{device}", summary="List Installed Packages")
def api_phone_packages(device: str, all: str = ""):
    """List installed packages on device."""
    from gitd.bots.common.adb import Device

    dev = Device(device)
    flag = "" if all else "-3"
    if flag:
        raw = dev.adb("shell", "pm", "list", "packages", flag, timeout=15)
    else:
        raw = dev.adb("shell", "pm", "list", "packages", timeout=15)
    packages = sorted([pkg.replace("package:", "").strip() for pkg in raw.splitlines() if pkg.startswith("package:")])
    return {"packages": packages, "count": len(packages)}


# ── Device health ────────────────────────────────────────────────────────────


@router.get("/health/{device}", summary="Device Health Check")
def api_phone_health(device: str):
    """Comprehensive health check — portal, wifi, battery, storage, apps."""
    from gitd.services.device_context import device_health
    return device_health(device)


@router.post("/health/{device}/fix", summary="Auto-Fix Device Issue")
def api_phone_health_fix(device: str, data: dict = Body({})):
    """Fix a specific device issue (portal_service, portal_install, screen_capture)."""
    from gitd.routers.streaming import portal_fix
    issue = data.get("issue", "")
    if issue in ("portal_service", "portal_install", "portal"):
        return portal_fix(device)
    if issue == "screen_wake":
        subprocess.run(["adb", "-s", device, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                       capture_output=True, timeout=3)
        return {"ok": True, "message": "Screen woken"}
    return {"ok": False, "error": f"Unknown issue: {issue}"}


# ── Wireless ADB ─────────────────────────────────────────────────────────────


@router.post("/wireless/enable", summary="Enable Wireless ADB")
def api_wireless_enable(data: dict = Body({}), db: Session = Depends(get_db)):
    """Switch USB device to WiFi mode."""
    from gitd.services.device_context import wireless_enable
    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device serial required")
    result = wireless_enable(device)
    if result.get("ok"):
        # Persist in DB
        from gitd.models.phone import Phone
        phone = db.get(Phone, device)
        if phone:
            phone.wifi_ip = result["wifi_ip"]
            phone.wifi_port = result.get("wifi_port", 5555)
            phone.connection_type = "wifi"
            db.commit()
    return result


@router.post("/wireless/pair", summary="Pair Wireless Device")
def api_wireless_pair(data: dict = Body({})):
    """Pair with Android 11+ Wireless Debugging."""
    from gitd.services.device_context import wireless_pair
    ip = data.get("ip", "")
    port = data.get("port", 5555)
    code = data.get("code", "")
    if not ip or not code:
        raise HTTPException(status_code=400, detail="ip and code required")
    return wireless_pair(ip, int(port), str(code))


@router.post("/wireless/connect", summary="Connect Wireless Device")
def api_wireless_connect(data: dict = Body({})):
    """Connect to a WiFi device by IP."""
    from gitd.services.device_context import wireless_connect
    ip = data.get("ip", "")
    port = data.get("port", 5555)
    if not ip:
        raise HTTPException(status_code=400, detail="ip required")
    return wireless_connect(ip, int(port))


@router.post("/wireless/disconnect", summary="Disconnect Wireless Device")
def api_wireless_disconnect(data: dict = Body({})):
    """Disconnect a wireless device."""
    from gitd.services.device_context import wireless_disconnect
    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    return wireless_disconnect(device)


# ── Structural fingerprint ───────────────────────────────────────────────────


@router.get("/fingerprint/{device}", summary="Get Screen Fingerprint")
def api_phone_fingerprint(device: str):
    """Structural fingerprint of current screen — stable regardless of visual changes."""
    from gitd.services.device_context import fingerprint_screen
    return fingerprint_screen(device)


@router.post("/fingerprint/{device}/validate", summary="Validate Screen Fingerprint")
def api_phone_fingerprint_validate(device: str, data: dict = Body({})):
    """Compare current screen against an expected fingerprint."""
    from gitd.services.device_context import validate_fingerprint
    expected = data.get("expected", {})
    return validate_fingerprint(device, expected)
