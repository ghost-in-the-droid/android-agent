---
title: "🎥 WebRTC Streaming"
description: Live phone screen streaming via WebRTC and MJPEG fallback — signaling, multi-device views, FPS overlay, and element overlay.
---

WebRTC streaming provides a live view of the phone screen in the browser at 720x1280 resolution. The server acts as a signaling proxy between the browser and the Droidrun Portal APK on the device.

## Architecture

```
Browser (dashboard or standalone viewer)
    |
    |  1. POST /api/phone/webrtc-signal {method: "stream/start"}
    v
Server (Flask) -- sets callbackUrl
    |
    |  2. HTTP POST to Portal (localhost:<port>/stream/start)
    v
Droidrun Portal APK (on device)
    |
    |  3. Captures screen via MediaProjection
    |  4. POSTs signaling (offer/ice) -> /api/phone/webrtc-callback/<device>
    v
Server stores in _signaling_queues[device]
    |
    |  5. Browser polls GET /api/phone/webrtc-poll-signals/<device>
    |  6. Browser sends answer/ice -> POST /api/phone/webrtc-signal
    v
WebRTC peer connection established -- video flows device -> browser
```

## Prerequisites

```bash
# Install Droidrun Portal APK on the device
adb install portal.apk

# Enable accessibility service
# Settings -> Accessibility -> Droidrun Portal -> Enable

# Port forwards (set up automatically by server)
adb -s <serial> forward tcp:18XXX tcp:8080   # Portal HTTP
adb -s <serial> forward tcp:19XXX tcp:8081   # Portal WebSocket
```

Port allocation is deterministic: `_stable_port(serial, base)` uses MD5 of the device serial. Each device gets a unique port pair.

## Usage

### Dashboard

1. Start server: `python3 run.py`
2. Open http://localhost:5055 -> **Phone Agent** tab
3. Select device -> click **Start Stream**
4. FPS counter overlay: green (20+), yellow (10-19), red (<10)

### Standalone Viewers

```
# Single device
http://localhost:5055/api/phone/webrtc-viewer?device=YOUR_DEVICE_SERIAL

# Multi-device grid
http://localhost:5055/api/phone/webrtc-multi?device=YOUR_DEVICE_SERIAL&device=YOUR_DEVICE_SERIAL_2
```

## MJPEG Fallback

If WebRTC fails, three MJPEG streaming modes are available:

| Mode | How It Works | FPS | Quality |
|------|-------------|-----|---------|
| `portal` | Portal `/screenshot` -> base64 PNG -> JPEG | ~3-5 | Good |
| `screencap` | `adb exec-out screencap -p` -> PIL -> JPEG | ~2 | OK |
| `h264` | `screenrecord --output-format=h264` -> ffmpeg -> MJPEG | ~25 | Best |

All modes halve the resolution (width/2, height/2) for bandwidth. Access via:

```
GET /api/phone/stream/<device>?mode=portal
```

Use as an `<img>` src for live view in any HTML page.

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/phone/stream/<device>` | MJPEG stream |
| POST | `/api/phone/webrtc-signal` | Relay signaling to Portal |
| POST | `/api/phone/webrtc-callback/<device>` | Receive signaling from Portal |
| GET | `/api/phone/webrtc-poll-signals/<device>` | Poll pending signaling messages |
| POST | `/api/phone/webrtc-ws-send` | Send via Portal WebSocket |
| POST | `/api/phone/webrtc-ws-poll` | Poll WebSocket messages |
| GET | `/api/phone/webrtc-viewer` | Standalone single-device viewer |
| GET | `/api/phone/webrtc-multi` | Multi-device grid viewer |
| GET | `/api/phone/elements/<device>` | Interactive elements for overlay |

## Element Overlay

When used in the Skill Creator tab, the WebRTC stream shows numbered labels on interactive elements. This overlay is generated from `GET /api/phone/elements/<device>` and rendered as positioned HTML elements on top of the video feed.

## Firewall Configuration

```bash
# Allow Flask server
sudo ufw allow 5055

# Allow WebRTC UDP traffic on local network
sudo ufw allow proto udp from 192.168.0.0/24
```

## Troubleshooting

### Stream not starting

1. Verify Portal APK is installed: `adb shell pm list packages | grep droidrun`
2. Check accessibility service is enabled on the device
3. The first `stream/start` may return `prompting_user` (MediaProjection dialog) -- approve on device
4. Fallback to MJPEG if WebRTC fails: Phone Agent tab -> MJPEG toggle

### Low FPS

- WebRTC is limited by Portal's MediaProjection capture rate (~5-15 FPS)
- MJPEG h264 mode gives ~25 FPS but requires ffmpeg

### Firewall blocking

WebRTC uses UDP for media transport. If behind a strict firewall, use MJPEG mode instead.

## Related

- [Dashboard](/features/dashboard/) -- where streaming is integrated
- [Skill Creator](/features/skill-creator/) -- uses stream + element overlay
- [Phone Farm](/guides/phone-farm/) -- multi-device streaming
