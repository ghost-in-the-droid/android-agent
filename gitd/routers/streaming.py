"""Streaming routes: MJPEG phone stream, WebRTC signaling."""

import asyncio
import hashlib
import json
import subprocess
import time
import urllib.request

from fastapi import APIRouter, Body, HTTPException, Request
from starlette.responses import StreamingResponse

router = APIRouter(tags=["streaming"])

# Portal package names — support both Ghost Portal and droidrun Portal
_PORTAL_PACKAGES = ("com.ghostinthedroid.portal", "com.droidrun.portal")

# Per-device signaling message queues + async events for SSE push
_signaling_queues: dict = {}  # device_serial -> list of messages
_signaling_events: dict[str, asyncio.Event] = {}  # notify SSE listeners instantly

# Cache ADB setup per device — skip wakeup + reverse if done recently
_adb_setup_cache: dict[str, float] = {}  # device -> last_setup_timestamp
_ADB_SETUP_TTL = 60.0  # seconds

# WebSocket relay state
_ws_relays: dict = {}  # device_serial -> {'ws': WebSocket, 'queue': list}


def _stable_ws_port(serial: str) -> int:
    return 19000 + int(hashlib.md5(serial.encode()).hexdigest()[:3], 16) % 1000


# ── MJPEG Stream ────────────────────────────────────────────────────────────


@router.get("/api/phone/stream", summary="Stream Phone Screen MJPEG")
def phone_stream(device: str = "", fps: int = 30, quality: int = 8, mode: str = "screencap"):
    """Stream phone screen via MJPEG."""
    fps = max(1, min(fps, 60))
    quality = max(1, min(quality, 31))
    dev_args = ["-s", device] if device else []

    def gen_h264():
        import io as _io

        from PIL import Image

        try:
            raw = subprocess.check_output(["adb"] + dev_args + ["exec-out", "screencap", "-p"], timeout=5)
            img = Image.open(_io.BytesIO(raw)).convert("RGB")
            w, h = img.size
            img = img.resize((w // 2, h // 2), Image.NEAREST)
            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=50)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.getvalue() + b"\r\n")
        except Exception:
            pass
        while True:
            adb_cmd = (
                ["adb"]
                + dev_args
                + ["exec-out", "screenrecord", "--output-format=h264", "--size", "720x1280", "--bit-rate", "4M", "-"]
            )
            ffmpeg_cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "+nobuffer+flush_packets",
                "-flags",
                "low_delay",
                "-probesize",
                "32",
                "-analyzeduration",
                "0",
                "-f",
                "h264",
                "-i",
                "pipe:0",
                "-q:v",
                str(quality),
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-flush_packets",
                "1",
                "pipe:1",
            ]
            adb_proc = ff_proc = None
            try:
                adb_proc = subprocess.Popen(adb_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                ff_proc = subprocess.Popen(
                    ffmpeg_cmd, stdin=adb_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                )
                adb_proc.stdout.close()
                buf = b""
                SOI = b"\xff\xd8"
                EOI = b"\xff\xd9"
                while True:
                    chunk = ff_proc.stdout.read(16384)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        start = buf.find(SOI)
                        if start == -1:
                            buf = b""
                            break
                        end = buf.find(EOI, start + 2)
                        if end == -1:
                            buf = buf[start:]
                            break
                        frame = buf[start : end + 2]
                        buf = buf[end + 2 :]
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            except Exception:
                pass
            finally:
                for p in [adb_proc, ff_proc]:
                    try:
                        if p:
                            p.kill()
                    except Exception:
                        pass
            time.sleep(1)

    def gen_screencap():
        import io as _io

        from PIL import Image

        delay = max(0, 1.0 / min(fps, 10) - 0.5)
        while True:
            try:
                raw = subprocess.check_output(["adb"] + dev_args + ["exec-out", "screencap", "-p"], timeout=6)
                img = Image.open(_io.BytesIO(raw)).convert("RGB")
                img = img.resize((img.width // 2, img.height // 2), Image.NEAREST)
                buf = _io.BytesIO()
                img.save(buf, format="JPEG", quality=40)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.getvalue() + b"\r\n")
            except Exception:
                time.sleep(0.5)
                continue
            time.sleep(delay)

    def gen_portal():
        import base64 as _b64
        import io as _io

        from PIL import Image

        from gitd.bots.common.adb import _stable_port

        portal_port = _stable_port(device, 18000) if device else 18067
        if device:
            try:
                subprocess.run(
                    ["adb", "-s", device, "forward", f"tcp:{portal_port}", "tcp:8080"], capture_output=True, timeout=3
                )
            except Exception:
                pass
        delay = max(0, 1.0 / min(fps, 10) - 0.2)
        while True:
            try:
                resp = urllib.request.urlopen(
                    f"http://localhost:{portal_port}/screenshot?hideOverlay=false", timeout=5
                ).read()
                j = json.loads(resp)
                if j.get("status") == "success" and j.get("result"):
                    png_data = _b64.b64decode(j["result"])
                    img = Image.open(_io.BytesIO(png_data)).convert("RGB")
                    img = img.resize((img.width // 2, img.height // 2), Image.NEAREST)
                    buf = _io.BytesIO()
                    img.save(buf, format="JPEG", quality=45)
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.getvalue() + b"\r\n")
            except Exception:
                time.sleep(1)
                continue
            time.sleep(delay)

    gen = gen_portal if mode == "portal" else (gen_h264 if mode == "h264" else gen_screencap)
    return StreamingResponse(
        gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Portal health / fix ─────────────────────────────────────────────────────


@router.get("/api/phone/portal-status/{device}", summary="Check Portal Health")
def portal_status(device: str):
    """Check Portal health on a device: process, accessibility service, HTTP API."""
    import urllib.error

    from gitd.bots.common.adb import Device

    result = {
        "device": device,
        "process": False,
        "accessibility": False,
        "http": False,
        "screen_on": True,
        "error": None,
    }
    try:
        ps = subprocess.run(
            ["adb", "-s", device, "shell", "ps -A | grep -E 'ghostinthedroid.portal|droidrun.portal'"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        result["process"] = any(pkg in ps.stdout for pkg in _PORTAL_PACKAGES)
        acc = subprocess.run(
            ["adb", "-s", device, "shell", "settings get secure enabled_accessibility_services"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        result["accessibility"] = any(pkg in acc.stdout for pkg in _PORTAL_PACKAGES)
        dev = Device(device)
        port = dev._ensure_portal_forward()
        if port:
            try:
                urllib.request.urlopen(f"http://localhost:{port}/status", timeout=2)
                result["http"] = True
            except urllib.error.HTTPError:
                result["http"] = True
            except Exception:
                result["http"] = False
        display = subprocess.run(
            ["adb", "-s", device, "shell", "dumpsys", "power"], capture_output=True, text=True, timeout=5
        )
        result["screen_on"] = "mWakefulness=Awake" in display.stdout or "Display Power: state=ON" in display.stdout
        if not result["accessibility"]:
            result["error"] = "Portal Accessibility Service disabled"
        elif not result["process"]:
            result["error"] = "Portal app not running"
        elif not result["http"] and not result["screen_on"]:
            result["error"] = "Screen is off — Portal suspends HTTP when display off"
        elif not result["http"]:
            result["error"] = "Portal HTTP not responding"
    except Exception as e:
        result["error"] = str(e)
    return result


@router.post("/api/phone/portal-fix/{device}", summary="Auto-Fix Phone Portal")
def portal_fix(device: str):
    """Auto-fix Portal: wake screen, enable accessibility service, restart."""
    import urllib.error

    from gitd.bots.common.adb import _stable_port

    try:
        subprocess.run(
            ["adb", "-s", device, "shell", "input", "keyevent", "KEYCODE_WAKEUP"], capture_output=True, timeout=10
        )
        subprocess.run(
            ["adb", "-s", device, "shell", "am", "force-stop", "com.ghostinthedroid.portal"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(1)
        subprocess.run(
            ["adb", "-s", device, "shell", "am", "start", "-n", "com.ghostinthedroid.portal/.MainActivity"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(1)
        subprocess.run(
            [
                "adb",
                "-s",
                device,
                "shell",
                "settings",
                "put",
                "secure",
                "enabled_accessibility_services",
                "com.ghostinthedroid.portal/.GhostAccessibilityService",
            ],
            capture_output=True,
            timeout=5,
        )
        subprocess.run(
            ["adb", "-s", device, "shell", "settings", "put", "secure", "accessibility_enabled", "1"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(3)
        local_port = _stable_port(device, 18000)
        subprocess.run(
            ["adb", "-s", device, "forward", f"tcp:{local_port}", "tcp:8080"], capture_output=True, timeout=3
        )
        try:
            urllib.request.urlopen(f"http://localhost:{local_port}/status", timeout=3)
            return {"ok": True, "message": "Portal fixed and responding"}
        except urllib.error.HTTPError:
            return {"ok": True, "message": "Portal fixed and responding"}
        except Exception:
            return {"ok": True, "message": "Portal restarted — may take a few seconds"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── WebRTC signaling ────────────────────────────────────────────────────────


@router.post("/api/phone/webrtc-callback/{device}", summary="WebRTC Signaling Callback")
async def webrtc_callback_handler(device: str, request: Request):
    """Receive signaling messages from Portal's HTTP callback."""
    raw = await request.body()
    raw_text = raw.decode("utf-8", errors="replace")
    try:
        msg = json.loads(raw_text) if raw_text else {}
    except Exception:
        msg = {}
    if device not in _signaling_queues:
        _signaling_queues[device] = []
    _signaling_queues[device].append(msg)
    # Wake up SSE listeners instantly
    evt = _signaling_events.get(device)
    if evt:
        evt.set()
    return {"ok": True}


@router.get("/api/phone/webrtc-poll-signals/{device}", summary="Poll WebRTC Signals")
def webrtc_poll_signals(device: str):
    """Poll pending signaling messages from Portal for this device (legacy)."""
    msgs = _signaling_queues.pop(device, [])
    return {"ok": True, "messages": msgs}


@router.get("/api/phone/webrtc-signals-stream/{device}", summary="SSE Signal Stream")
async def webrtc_signals_stream(device: str):
    """Server-Sent Events stream — pushes signaling messages instantly (no polling)."""

    async def generate():
        # Create per-device event for notifications
        _signaling_events[device] = asyncio.Event()
        try:
            yield 'data: {"type":"connected"}\n\n'
            while True:
                # Wait for signal or timeout (keepalive every 15s)
                try:
                    await asyncio.wait_for(_signaling_events[device].wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                # Drain queue and push all pending messages
                _signaling_events[device].clear()
                msgs = _signaling_queues.pop(device, [])
                for msg in msgs:
                    yield f"data: {json.dumps(msg)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _signaling_events.pop(device, None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/api/phone/webrtc-signal", summary="Relay WebRTC Signal To Portal")
async def webrtc_signal(data: dict = Body({})):
    """Relay WebRTC signaling to Portal via its HTTP API.
    Runs blocking I/O in a thread to avoid starving the async event loop."""
    import asyncio

    return await asyncio.to_thread(_webrtc_signal_sync, data)


def _webrtc_signal_sync(data: dict):
    device = data.get("device", "")
    method = data.get("method", "")
    params = data.get("params", {})

    if not device or not method:
        raise HTTPException(status_code=400, detail="device and method required")

    from gitd.bots.common.adb import Device

    dev = Device(device)
    port = dev._ensure_portal_forward()
    if not port:
        return {"ok": False, "error": "Portal not available — check Settings > Accessibility > Portal"}

    import urllib.error

    try:
        if method == "stream/start":
            _signaling_queues[device] = []
            from gitd.config import settings

            server_port = str(getattr(settings, "port", 5055))

            # Only run ADB setup if not done recently (saves ~300ms)
            last_setup = _adb_setup_cache.get(device, 0)
            if time.time() - last_setup > _ADB_SETUP_TTL:
                subprocess.run(
                    ["adb", "-s", device, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                    capture_output=True,
                    timeout=10,
                )
                try:
                    subprocess.run(
                        ["adb", "-s", device, "reverse", f"tcp:{server_port}", f"tcp:{server_port}"],
                        capture_output=True,
                        timeout=3,
                    )
                except Exception:
                    pass
                _adb_setup_cache[device] = time.time()

            # WiFi devices can't use adb reverse — use LAN IP instead of 127.0.0.1
            is_wifi = ":" in device
            if is_wifi:
                import socket

                lan_ip = socket.gethostbyname(socket.gethostname())
                # gethostbyname may return 127.0.0.1 — fall back to interface scan
                if lan_ip.startswith("127."):
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.connect(("8.8.8.8", 80))
                        lan_ip = s.getsockname()[0]
                        s.close()
                    except Exception:
                        lan_ip = "127.0.0.1"
                params["callbackUrl"] = f"http://{lan_ip}:{server_port}/api/phone/webrtc-callback/{device}"
            else:
                params["callbackUrl"] = f"http://127.0.0.1:{server_port}/api/phone/webrtc-callback/{device}"

        payload = json.dumps(params).encode()
        req = urllib.request.Request(
            f"http://localhost:{port}/{method}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return {"ok": True, "result": result}
    except urllib.error.URLError:
        # Portal not responding — check accessibility service
        try:
            acc = subprocess.run(
                ["adb", "-s", device, "shell", "settings", "get", "secure", "enabled_accessibility_services"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if not any(pkg in acc.stdout for pkg in _PORTAL_PACKAGES):
                return {
                    "ok": False,
                    "error": "Portal Accessibility Service disabled — use portal-fix or enable in Settings > Accessibility",
                }
        except Exception:
            pass
        return {"ok": False, "error": "Portal not responding — try portal-fix"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/phone/webrtc-ws-send", summary="Send WebSocket Message To Portal")
def webrtc_ws_send(data: dict = Body({})):
    """Send a message to Portal's WebSocket and return any pending responses."""
    device = data.get("device", "")
    message = data.get("message", {})

    if not device:
        raise HTTPException(status_code=400, detail="device required")

    import websocket as ws_client

    local_ws = _stable_ws_port(device)
    try:
        subprocess.run(["adb", "-s", device, "forward", f"tcp:{local_ws}", "tcp:8081"], capture_output=True, timeout=3)
    except Exception:
        pass

    relay = _ws_relays.get(device)
    if not relay or not relay["ws"].connected:
        try:
            w = ws_client.WebSocket()
            w.connect(f"ws://localhost:{local_ws}", timeout=3)
            w.settimeout(0.5)
            relay = {"ws": w, "queue": []}
            _ws_relays[device] = relay
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"WS connect failed: {e}")

    try:
        relay["ws"].send(json.dumps(message))
    except Exception as e:
        _ws_relays.pop(device, None)
        raise HTTPException(status_code=500, detail=f"WS send failed: {e}")

    responses = []
    for _ in range(20):
        try:
            r = relay["ws"].recv()
            responses.append(json.loads(r))
        except Exception:
            break

    return {"ok": True, "responses": responses}


@router.post("/api/phone/webrtc-ws-poll", summary="Poll WebSocket Messages")
def webrtc_ws_poll(data: dict = Body({})):
    """Poll for pending WebSocket messages from Portal."""
    device = data.get("device", "")
    relay = _ws_relays.get(device)
    if not relay or not relay["ws"].connected:
        return {"ok": False, "responses": []}

    responses = []
    for _ in range(20):
        try:
            r = relay["ws"].recv()
            responses.append(json.loads(r))
        except Exception:
            break

    return {"ok": True, "responses": responses}
