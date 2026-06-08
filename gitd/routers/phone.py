"""Phone admin routes: devices, nickname, input, tap, type, back, key, etc."""

import re
import subprocess
import time as _time

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from gitd.bots.common.device import get_device, is_ios_ref, list_configured_ios_devices
from gitd.models.base import get_db

router = APIRouter(prefix="/api/phone", tags=["phone"])

_last_wifi_reconnect: float = 0

def _ios_unsupported(feature: str) -> dict:
    return {"ok": False, "platform": "ios", "error": f"{feature} is Android-only and is not supported for iOS devices"}


def _platform(device: str) -> str:
    return "ios" if is_ios_ref(device) else "android"


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
        rows = db.execute(
            text("SELECT wifi_ip, wifi_port FROM phones WHERE wifi_ip IS NOT NULL AND wifi_port IS NOT NULL")
        ).fetchall()

        for ip, port in rows:
            addr = f"{ip}:{port}"
            if addr not in connected:
                # Try connecting in background (non-blocking, 2s timeout)
                subprocess.Popen(["adb", "connect", addr], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


@router.get("/devices", summary="List Connected Phone Devices")
def phone_devices(probe: str = "", db: Session = Depends(get_db)):
    """List ADB-connected devices with model info and nicknames."""
    try:
        devices = []
        adb_error = ""
        deep_ios_probe = probe.lower() in {"1", "true", "deep", "full", "wda"}
        # Try reconnecting known WiFi devices that aren't currently connected
        _try_wifi_reconnect(db)

        try:
            out = subprocess.check_output(["adb", "devices", "-l"], timeout=5).decode()
        except Exception as e:
            out = ""
            adb_error = str(e)
        if out:
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
                    db.execute(
                        text("""
                        UPDATE phones SET wifi_ip=:ip, wifi_port=:port, connection_type=:conn
                        WHERE model=:model AND wifi_ip IS NULL
                    """),
                        {"ip": wifi_ip, "port": wifi_port, "conn": conn_type, "model": model},
                    )

                db.execute(
                    text("""
                    INSERT INTO phones (serial, model, first_seen, last_seen, wifi_ip, wifi_port, connection_type)
                    VALUES (:serial, :model, :now, :now, :ip, :port, :conn)
                    ON CONFLICT(serial) DO UPDATE SET model=:model, last_seen=:now,
                        wifi_ip=COALESCE(:ip, wifi_ip), wifi_port=COALESCE(:port, wifi_port),
                        connection_type=:conn
                """),
                    {
                        "serial": serial,
                        "model": model,
                        "now": now_str,
                        "ip": wifi_ip,
                        "port": wifi_port,
                        "conn": conn_type,
                    },
                )
                db.commit()
                devices.append(
                    {
                        "serial": serial,
                        "model": model or serial,
                        "connection": conn_type,
                        "platform": "android",
                    }
                )

        # Deduplicate: if same model has both USB and WiFi, keep USB only
        usb_models = {d["model"] for d in devices if d["connection"] == "usb"}
        devices = [d for d in devices if d["connection"] == "usb" or d["model"] not in usb_models]

        for ios_device in list_configured_ios_devices(deep_probe=deep_ios_probe):
            if not any(d["serial"] == ios_device["serial"] for d in devices):
                devices.append(ios_device)

        registry_rows = db.execute(text("SELECT * FROM phones")).mappings().all()
        registry = {r["serial"]: dict(r) for r in registry_rows}
        for d in devices:
            d["nickname"] = registry.get(d["serial"], {}).get("nickname", "")
        response = {"devices": devices}
        if adb_error:
            response["adb_error"] = adb_error
        return response
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
    if is_ios_ref(device):
        dev = get_device(device)
        try:
            if action == "tap":
                dev.tap(int(data["x"]), int(data["y"]))
            elif action == "swipe":
                dur = int(data.get("duration", 300))
                dev.swipe(int(data["x1"]), int(data["y1"]), int(data["x2"]), int(data["y2"]), ms=dur)
            elif action == "keyevent":
                dev.press_key(str(data["keycode"]))
            elif action == "text":
                dev.type_text(data["text"])
            else:
                return {"ok": False, "error": "unknown action"}
            return {"ok": True, "device": device, "platform": "ios"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
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
        return {"ok": True, "device": device, "platform": "android"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/elements/{device}", summary="Get Phone UI Elements")
def api_phone_elements(device: str):
    """Get interactive UI elements from device screen."""
    from gitd.bots.common.adb import Device
    from gitd.services.device_context import get_interactive_elements

    elements = get_interactive_elements(device)
    screen_size = {}
    try:
        if is_ios_ref(device):
            width, height = get_device(device).get_screen_size()
        else:
            out = Device(device).adb("shell", "wm", "size", timeout=3)
            m = re.search(r"(\d+)x(\d+)", out)
            width, height = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        if width and height:
            screen_size = {"width": width, "height": height}
    except Exception:
        screen_size = {}
    return {"elements": elements, "count": len(elements), "platform": _platform(device), "screen_size": screen_size}


@router.post("/tap", summary="Tap On Phone Screen")
def api_phone_tap(data: dict = Body({})):
    """Tap at coordinates or send a keyevent to a device."""
    from gitd.bots.common.adb import Device

    device = data.get("device", "")
    dev = get_device(device)
    if data.get("keyevent"):
        if is_ios_ref(device):
            dev.press_key(str(data["keyevent"]))
        else:
            dev.adb("shell", "input", "keyevent", data["keyevent"])
    else:
        x, y = int(data.get("x", 0)), int(data.get("y", 0))
        stream_w = int(data.get("stream_w", 0))
        stream_h = int(data.get("stream_h", 0))
        if stream_w and stream_h:
            try:
                if is_ios_ref(device):
                    real_w, real_h = dev.get_screen_size()
                else:
                    out = Device(device).adb("shell", "wm", "size", timeout=3)
                    m = re.search(r"(\d+)x(\d+)", out)
                    real_w, real_h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
                if real_w and real_h:
                    x = int(x * real_w / stream_w)
                    y = int(y * real_h / stream_h)
            except Exception:
                pass
        dev.tap(x, y)
    return {"ok": True, "device": device, "platform": _platform(device)}


@router.post("/type", summary="Type Text On Phone")
def api_phone_type(data: dict = Body({})):
    """Type text into the focused input field on a device."""
    device = data.get("device", "")
    dev = get_device(device)
    text_val = data.get("text", "")
    if is_ios_ref(device):
        dev.type_text(text_val)
    else:
        dev.adb("shell", "input", "text", text_val.replace(" ", "%s"))
    return {"ok": True, "device": device, "platform": _platform(device)}


@router.get("/clipboard/{device}", summary="Get Device Clipboard")
def api_phone_clipboard_get(device: str):
    """Read plain-text clipboard contents from Android or iOS."""
    from gitd.services.device_context import clipboard_get

    text_value = clipboard_get(device)
    return {
        "ok": True,
        "device": device,
        "platform": "ios" if is_ios_ref(device) else "android",
        "text": text_value,
    }


@router.post("/clipboard", summary="Set Device Clipboard")
def api_phone_clipboard_set(data: dict = Body({})):
    """Set plain-text clipboard contents on Android or iOS."""
    from gitd.services.device_context import clipboard_set

    device = data.get("device", "")
    text_value = data.get("text", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    ok = clipboard_set(device, str(text_value))
    return {"ok": bool(ok), "device": device, "platform": "ios" if is_ios_ref(device) else "android"}


@router.post("/paste-text", summary="Paste Text On Phone")
def api_phone_paste_text(data: dict = Body({})):
    """Set clipboard text and paste it into the focused field."""
    from gitd.services.device_context import clipboard_set

    device = data.get("device", "")
    text_value = data.get("text", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    if is_ios_ref(device):
        ok = bool(get_device(device).paste_text(str(text_value)))
    else:
        ok = clipboard_set(device, str(text_value))
        if ok:
            from gitd.bots.common.adb import Device

            Device(device).adb("shell", "input", "keyevent", "KEYCODE_PASTE")
    return {"ok": bool(ok), "device": device, "platform": "ios" if is_ios_ref(device) else "android"}


@router.post("/back", summary="Press Back Button")
def api_phone_back(data: dict = Body({})):
    """Press the platform back/navigation control on a device."""
    device = data.get("device", "")
    dev = get_device(device)
    dev.back(delay=0.3)
    return {"ok": True, "device": device, "platform": _platform(device)}


@router.post("/key", summary="Send Keyevent To Phone")
def api_phone_key(data: dict = Body({})):
    """Send a keyevent to device."""
    device = data.get("device", "")
    dev = get_device(device)
    key = data.get("key", "")
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    if is_ios_ref(device):
        dev.press_key(key)
    elif not key.startswith("KEYCODE_"):
        key = "KEYCODE_" + key
        dev.adb("shell", "input", "keyevent", key)
    else:
        dev.adb("shell", "input", "keyevent", key)
    return {"ok": True, "device": device, "platform": _platform(device)}


@router.post("/launch", summary="Launch App On Phone")
def api_phone_launch(data: dict = Body({})):
    """Launch an Android package or iOS bundle id on a device."""
    device = data.get("device", "")
    dev = get_device(device)
    pkg = data.get("package", "")
    if not pkg:
        raise HTTPException(status_code=400, detail="package required")
    if is_ios_ref(device):
        dev.launch_app(pkg)
        return {"ok": True, "device": device, "platform": "ios", "package": pkg, "bundle_id": pkg}
    else:
        dev.adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    return {"ok": True, "device": device, "platform": "android", "package": pkg, "bundle_id": ""}


@router.post("/browser/open-url", summary="Open URL In Browser")
def api_phone_browser_open_url(data: dict = Body({})):
    """Open a URL in the platform browser."""
    from gitd.services.browser import open_url

    device = data.get("device", "")
    url = data.get("url", "")
    if not device or not url:
        raise HTTPException(status_code=400, detail="device and url required")
    return open_url(device, url, bundle_id=data.get("bundle_id") or None)


@router.post("/browser/search", summary="Search Web In Browser")
def api_phone_browser_search(data: dict = Body({})):
    """Open a web search in the platform browser."""
    from gitd.services.browser import web_search

    device = data.get("device", "")
    query = data.get("query", "")
    if not device or not query:
        raise HTTPException(status_code=400, detail="device and query required")
    return web_search(device, query, engine=data.get("engine", "google"), bundle_id=data.get("bundle_id") or None)


@router.post("/browser/back", summary="Navigate Browser Back")
def api_phone_browser_back(data: dict = Body({})):
    """Navigate back in the browser/app context."""
    from gitd.services.browser import browser_back

    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    return browser_back(device)


@router.get("/browser/current-url/{device}", summary="Get Current Browser URL")
def api_phone_browser_current_url(device: str):
    """Return the current browser URL when available."""
    from gitd.services.tool_platforms import platform_error, supports_platform

    platform = _platform(device)
    if not supports_platform("get_current_url", platform):
        return platform_error("get_current_url", platform)
    from gitd.services.browser import get_current_url

    return get_current_url(device)


@router.post("/browser/wait-for-text", summary="Wait For Browser Text")
def api_phone_browser_wait_for_text(data: dict = Body({})):
    """Wait for text to appear on screen."""
    from gitd.services.browser import wait_for_text

    device = data.get("device", "")
    text_value = data.get("text", "")
    if not device or not text_value:
        raise HTTPException(status_code=400, detail="device and text required")
    return wait_for_text(device, text_value, timeout=float(data.get("timeout", 12.0)))


@router.get("/browser/visible-text/{device}", summary="Extract Browser Visible Text")
def api_phone_browser_visible_text(device: str, max_lines: int = 200, include_controls: bool = False):
    """Extract visible text from the current screen."""
    from gitd.services.browser import extract_visible_text

    return extract_visible_text(device, max_lines=max_lines, include_controls=include_controls)


@router.get("/browser/articles/{device}", summary="Extract Browser Articles")
def api_phone_browser_articles(device: str, max_items: int = 5):
    """Extract likely visible article/headline candidates from the current page."""
    from gitd.services.browser import extract_articles

    return extract_articles(device, max_items=max_items)


@router.post("/browser/read-news", summary="Read News In Browser")
def api_phone_browser_read_news(data: dict = Body({})):
    """Open a news page and return headlines plus article snippets."""
    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    from gitd.services.tool_platforms import platform_error, supports_platform

    platform = _platform(device)
    if not supports_platform("read_news", platform):
        return platform_error("read_news", platform)

    from gitd.services.browser import read_news

    return read_news(
        device,
        data.get("url", "https://text.npr.org/"),
        max_headlines=int(data.get("max_headlines", 5)),
        max_articles=int(data.get("max_articles", 3)),
        bundle_id=data.get("bundle_id") or None,
        wait_s=float(data.get("wait_s", 2.0)),
        save_screenshots=bool(data.get("save_screenshots", False)),
        out_dir=data.get("out_dir") or None,
    )


@router.post("/reconnect/{device}", summary="Reconnect Phone Portal")
def api_phone_reconnect(device: str):
    """Clear Portal cache for a device and re-establish connection."""
    if is_ios_ref(device):
        return _ios_unsupported("Portal reconnect")
    from gitd.bots.common.adb import Device

    dev = Device(device)
    port = dev._ensure_portal_forward(force=True)
    if port:
        return {"ok": True, "port": port}
    raise HTTPException(status_code=500, detail="Portal not reachable")


@router.post("/force-stop", summary="Force Stop App On Phone")
def api_phone_force_stop(data: dict = Body({})):
    """Force-stop an app by package name on a device."""
    device = data.get("device", "")
    pkg = data.get("package", "")
    if is_ios_ref(device):
        if not pkg:
            raise HTTPException(status_code=400, detail="package required")
        get_device(device).terminate_app(pkg)
        return {"ok": True, "device": device, "platform": "ios", "bundle_id": pkg}
    from gitd.bots.common.adb import Device

    dev = Device(device)
    if not pkg:
        raise HTTPException(status_code=400, detail="package required")
    dev.adb("shell", "am", "force-stop", pkg)
    return {"ok": True, "device": device, "platform": "android", "package": pkg}


@router.get("/app-state/{device}", summary="Get App State")
def api_phone_app_state_get(device: str, package: str = ""):
    """Check whether an Android package or iOS bundle id is installed/running/foreground."""
    from gitd.services.device_context import app_state

    if not package:
        raise HTTPException(status_code=400, detail="package required")
    return app_state(device, package)


@router.post("/app-state", summary="Get App State")
def api_phone_app_state_post(data: dict = Body({})):
    """Check whether an Android package or iOS bundle id is installed/running/foreground."""
    from gitd.services.device_context import app_state

    device = data.get("device", "")
    package = data.get("package", "")
    if not device or not package:
        raise HTTPException(status_code=400, detail="device and package required")
    return app_state(device, package)


@router.post("/swipe", summary="Swipe On Phone Screen")
def api_phone_swipe(data: dict = Body({})):
    """Perform a swipe gesture on a device with coordinate scaling."""
    from gitd.bots.common.adb import Device

    device = data.get("device", "")
    dev = get_device(device)
    x1, y1 = int(data.get("x1", 540)), int(data.get("y1", 1600))
    x2, y2 = int(data.get("x2", 540)), int(data.get("y2", 400))
    stream_w = int(data.get("stream_w", 0))
    stream_h = int(data.get("stream_h", 0))
    if stream_w and stream_h:
        try:
            if is_ios_ref(device):
                real_w, real_h = dev.get_screen_size()
            else:
                out = Device(device).adb("shell", "wm", "size", timeout=3)
                m = re.search(r"(\d+)x(\d+)", out)
                real_w, real_h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            if real_w and real_h:
                x1 = int(x1 * real_w / stream_w)
                y1 = int(y1 * real_h / stream_h)
                x2 = int(x2 * real_w / stream_w)
                y2 = int(y2 * real_h / stream_h)
        except Exception:
            pass
    dev.swipe(x1, y1, x2, y2)
    return {"ok": True, "device": device, "platform": _platform(device)}


@router.get("/screenshot/{device}", summary="Take Phone Screenshot")
def api_phone_screenshot(device: str):
    """Take screenshot, return as base64 JPEG."""
    from gitd.services.device_context import screenshot

    result = screenshot(device)
    return {"ok": True, **result}


@router.get("/screenshot-annotated/{device}", summary="Take Annotated Screenshot")
def api_phone_screenshot_annotated(device: str):
    """Take a screenshot with server-side numbered element labels."""
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
    from gitd.services.device_context import ocr_region, ocr_screen

    if x1 or y1 or x2 or y2:
        texts = ocr_region(device, x1, y1, x2, y2)
    else:
        texts = ocr_screen(device)
    return {"ok": True, "texts": texts, "count": len(texts)}


@router.get("/notifications/{device}", summary="Get Device Notifications")
def api_phone_notifications(device: str):
    """Read visible active notifications from Android or iOS."""
    from gitd.services.device_context import get_notifications

    items = get_notifications(device)
    return {
        "ok": True,
        "device": device,
        "platform": "ios" if is_ios_ref(device) else "android",
        "notifications": items,
        "count": len(items),
    }


@router.post("/notifications/open", summary="Open Notifications")
def api_phone_notifications_open(data: dict = Body({})):
    """Open Android notification shade or iOS Notification Center."""
    from gitd.services.device_context import open_notifications

    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    ok = open_notifications(device)
    return {"ok": bool(ok), "device": device, "platform": "ios" if is_ios_ref(device) else "android"}


@router.post("/notifications/clear", summary="Clear Notifications")
def api_phone_notifications_clear(data: dict = Body({})):
    """Dismiss visible notifications when the platform exposes a clear control."""
    from gitd.services.device_context import clear_notifications

    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    ok = clear_notifications(device)
    return {"ok": bool(ok), "device": device, "platform": "ios" if is_ios_ref(device) else "android"}


@router.get("/classify/{device}", summary="Classify Phone Screen")
def api_phone_classify(device: str):
    """Classify current screen type (home, search, dialog, error, etc.)."""
    from gitd.services.device_context import classify_screen

    return classify_screen(device)


@router.post("/recording/start", summary="Start Screen Recording")
def api_phone_recording_start(data: dict = Body({})):
    """Start cross-platform screen recording for Android or iOS."""
    from gitd.services.phone_recording import start_recording

    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    result = start_recording(device, filename=data.get("filename", ""))
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/recording/stop", summary="Stop Screen Recording")
def api_phone_recording_stop(data: dict = Body({})):
    """Stop a running screen recording and save the MP4."""
    from gitd.services.phone_recording import stop_recording

    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    result = stop_recording(device)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/recording/status/{device}", summary="Screen Recording Status")
def api_phone_recording_status(device: str):
    """Return active screen recording status for a device."""
    from gitd.services.phone_recording import recording_status

    return recording_status(device)


@router.get("/recordings", summary="List Screen Recordings")
def api_phone_recordings():
    """List saved phone screen recordings."""
    from gitd.services.phone_recording import list_recordings

    return {"recordings": list_recordings()}


@router.get("/recording/{filename:path}", summary="Serve Screen Recording")
def api_phone_recording_file(filename: str):
    """Serve a saved phone screen recording MP4."""
    from gitd.services.phone_recording import recording_file

    try:
        return FileResponse(str(recording_file(filename)), media_type="video/mp4")
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="recording not found")


@router.delete("/recording/{filename:path}", summary="Delete Screen Recording")
def api_phone_recording_delete(filename: str):
    """Delete a saved phone screen recording."""
    from gitd.services.phone_recording import delete_recording

    try:
        return delete_recording(filename)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="recording not found")


@router.post("/overlay/{device}", summary="Toggle Phone Overlay")
def api_phone_overlay(device: str, data: dict = Body({})):
    """Toggle Droidrun Portal overlay on/off."""
    if is_ios_ref(device):
        return _ios_unsupported("Portal overlay")
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
    """List Android packages or known iOS bundle ids on a device."""
    if is_ios_ref(device):
        from gitd.services.device_context import list_apps

        apps = list_apps(device, verify=True)
        packages = [app.get("bundle_id") or app.get("package", "") for app in apps]
        return {
            "packages": [pkg for pkg in packages if pkg],
            "apps": apps,
            "count": len(packages),
            "platform": "ios",
            "note": "iOS app inventory is limited to configured/common bundle ids verified through Appium when available.",
        }
    from gitd.bots.common.adb import Device

    dev = Device(device)
    flag = "" if all else "-3"
    if flag:
        raw = dev.adb("shell", "pm", "list", "packages", flag, timeout=15)
    else:
        raw = dev.adb("shell", "pm", "list", "packages", timeout=15)
    packages = sorted([pkg.replace("package:", "").strip() for pkg in raw.splitlines() if pkg.startswith("package:")])
    return {"packages": packages, "count": len(packages)}


@router.get("/apps/{device}", summary="List Installed Apps")
def api_phone_apps(device: str, query: str = "", all: str = "", verify: bool = True):
    """List app inventory with display names and Android package or iOS bundle IDs."""
    from gitd.services.device_context import list_apps

    include_system = str(all).lower() in {"1", "true", "yes", "all"}
    apps = list_apps(device, query=query, verify=verify, include_system=include_system)
    packages = [app.get("bundle_id") or app.get("package", "") for app in apps]
    return {
        "apps": apps,
        "packages": [pkg for pkg in packages if pkg],
        "count": len(apps),
        "platform": "ios" if is_ios_ref(device) else "android",
        "query": query,
    }


# ── Device health ────────────────────────────────────────────────────────────


@router.get("/health/{device}", summary="Device Health Check")
def api_phone_health(device: str):
    """Comprehensive health check — portal, wifi, battery, storage, apps."""
    from gitd.services.device_context import device_health

    return device_health(device)


@router.post("/health/{device}/fix", summary="Auto-Fix Device Issue")
def api_phone_health_fix(device: str, data: dict = Body({})):
    """Fix a specific device issue (portal_service, portal_install, screen_capture)."""
    from gitd.services.device_context import fix_device_health

    return fix_device_health(device, data.get("issue", ""))


# ── Wireless ADB ─────────────────────────────────────────────────────────────


@router.post("/wireless/enable", summary="Enable Wireless ADB")
def api_wireless_enable(data: dict = Body({}), db: Session = Depends(get_db)):
    """Switch USB device to WiFi mode."""
    from gitd.services.device_context import wireless_enable

    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device serial required")
    if is_ios_ref(device):
        return _ios_unsupported("Wireless ADB")
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
    if is_ios_ref(device):
        return _ios_unsupported("Wireless ADB disconnect")
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
