# WebRTC Device Streaming — Feature Summary

## What It Does

Live phone screen streaming from Android devices to the browser dashboard via WebRTC and MJPEG fallbacks. The server acts as a signaling proxy between the browser and the Droidrun Portal APK running on each device, enabling real-time video streams with FPS overlay, multi-device views, and standalone viewer pages.

## Current State

**Working:**
- WebRTC streaming via Droidrun Portal MediaProjection (primary method)
- MJPEG streaming via 3 fallback modes: Portal screenshot polling, screencap, h264 pipe
- Browser viewer embedded in Phone Agent tab (single-device + multi-device)
- Standalone viewer pages (`/api/phone/webrtc-viewer`, `/api/phone/webrtc-multi`)
- Start/Stop stream controls with FPS counter overlay (green 20+, yellow 10-19, red <10)
- WebRTC signaling relay via HTTP callback and WebSocket channels
- Per-device deterministic port allocation (avoids port conflicts across devices)
- Element overlay for Skill Creator (numbered interactive elements on stream)

**Limitations:**
- WebRTC FPS limited by Portal's MediaProjection capture rate (~5-15 FPS)
- Requires Droidrun Portal APK installed + accessibility service enabled on device
- First `stream/start` returns `prompting_user` (MediaProjection dialog) — needs manual approve or auto-accept
- Touch forwarding not yet implemented (view only, no remote interaction via stream)
- MJPEG screencap fallback is slow (~2 FPS over USB)

## Architecture

```
Browser (dashboard.html / standalone viewer)
        │
        │  1. POST /api/phone/webrtc-signal {method: "stream/start"}
        ▼
Server (Flask) — sets callbackUrl in params
        │
        │  2. HTTP POST to Portal (localhost:<port>/stream/start)
        ▼
Droidrun Portal APK (device, port 8080 → forwarded)
        │
        │  3. Portal captures screen via MediaProjection
        │  4. Portal POSTs signaling (offer/ice) → /api/phone/webrtc-callback/<device>
        ▼
Server stores in _signaling_queues[device]
        │
        │  5. Browser polls GET /api/phone/webrtc-poll-signals/<device>
        │  6. Browser sends answer/ice → POST /api/phone/webrtc-signal
        ▼
WebRTC peer connection established — video flows directly device → browser
```

**Port allocation:** `_stable_port(serial, base)` uses MD5 of device serial for deterministic ports:
- HTTP (Portal API): base 18000 + hash % 1000
- WebSocket: base 19000 + hash % 1000

## Files

| File | Purpose |
|------|---------|
| `gitd/server.py` | 12 WebRTC/streaming endpoints (lines ~3526-4760) |
| `gitd/static/dashboard.html` | Phone Agent tab — WebRTC viewer, element overlay |
| `gitd/bots/common/adb.py` | `_stable_port()`, `_ensure_portal_forward()`, Portal HTTP/JSON |
| `reference/droidrun-portal/` | Portal APK source (Kotlin) — MediaProjection, accessibility, WS server |

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/phone/stream` | MJPEG stream (modes: `portal`, `screencap`, `h264`) |
| POST | `/api/phone/webrtc-signal` | Relay signaling to Portal HTTP API |
| POST | `/api/phone/webrtc-callback/<device>` | Receive signaling from Portal (callback) |
| GET | `/api/phone/webrtc-poll-signals/<device>` | Poll pending signaling messages |
| POST | `/api/phone/webrtc-ws-send` | Send message via Portal WebSocket |
| POST | `/api/phone/webrtc-ws-poll` | Poll WebSocket messages |
| GET | `/api/phone/webrtc-viewer` | Standalone single-device viewer page |
| GET | `/api/phone/webrtc-multi` | Multi-device viewer (grid layout) |
| GET | `/api/phone/elements/<device>` | Get interactive UI elements (for overlay) |

## MJPEG Streaming Modes

| Mode | How It Works | FPS | Quality |
|------|-------------|-----|---------|
| `portal` | Portal `/screenshot` → base64 PNG → JPEG | ~3-5 | Good |
| `screencap` | `adb exec-out screencap -p` → PIL → JPEG | ~2 | OK |
| `h264` | `screenrecord --output-format=h264` → ffmpeg → MJPEG | ~25 | Best |

All modes half the resolution (width/2, height/2) for bandwidth.

## Configuration / Prerequisites

```bash
# Droidrun Portal must be installed and accessibility enabled
adb install portal.apk
# Enable in: Settings → Accessibility → Droidrun Portal

# UFW rules for WebRTC (UDP) and server (TCP)
sudo ufw allow 5055
sudo ufw allow proto udp from 192.168.0.0/24

# ADB port forwards (set up automatically by server)
adb -s <serial> forward tcp:18XXX tcp:8080   # Portal HTTP
adb -s <serial> forward tcp:19XXX tcp:8081   # Portal WebSocket
```

## How to Use

1. Start server: `python3 run.py`
2. Open `http://localhost:5055` → Phone Agent tab
3. Select device → click Start Stream (or use standalone: `/api/phone/webrtc-viewer?device=<serial>`)
4. For multi-device: `/api/phone/webrtc-multi?device=SER1&device=SER2`

## Known Issues & TODOs

- [ ] Touch forwarding — click/swipe on video should send ADB input to device
- [ ] Upgrade to scrcpy 2.x for native 30+ FPS H.264 without ffmpeg
- [ ] Auto-accept MediaProjection dialog (Portal has `MediaProjectionAutoAccept` but needs accessibility)
- [ ] WebSocket relay (`_ws_relays`) leaks connections — no cleanup on disconnect
- [ ] Multi-device viewer grid caps at 3 columns — should be responsive
- [ ] MJPEG h264 mode restarts screenrecord in infinite loop on disconnect (intentional but wasteful)
- [ ] Element overlay refresh rate tied to manual button press — should auto-refresh on screen change
