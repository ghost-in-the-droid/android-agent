# Ghost Fleet — Distributed Device Orchestration (Design)

**Status:** design / roadmap. Parts are implemented (single-host iOS + streaming);
the federation layer is proposed.

## Goal

One **Linux master** orchestrates a mixed pool of phones. Android devices hang off
the master directly (adb runs on Linux). iOS devices hang off **Mac nodes** (Apple
signing/tunnelling is macOS-only). The master sees a **single unified device pool**
regardless of which host a phone is physically attached to, can drive any device,
and streams any screen back to the Linux GUI.

```
   Linux master (orchestrator + GUI)
        │  aggregates devices from all nodes; proxies control + stream
        ├──────────── adb ───────────► Android phones     (local, direct)
        │
        └── HTTP (Tailscale/LAN) ──► Mac node: Ghost + Appium + RemoteXPC tunnel
                                          └── USB + WDA ──► iPhone
```

Provisioning a new iOS capacity = "give the master the SSH of a Mac; install Ghost;
register the node." From then on the Mac is a dumb worker; the master is the brain.

## Why a Mac is unavoidable for iOS

Everything that touches an iPhone is macOS-only and has no Linux equivalent:
`xcodebuild` + `codesign` (build/sign WebDriverAgent), the CoreDevice/RemoteXPC
tunnel to a physical device, and the Simulator runtime. Linux **cannot** talk to an
iPhone directly. So iOS support = "the fleet needs ≥1 always-logged-in Mac node."
(See the validation report: codesign requires a GUI/Aqua login session — F3.)

## What already exists (single-host)

- Ghost backend binds `0.0.0.0:5055` — reachable from other hosts out of the box.
- `IOS_APPIUM_URL` already lets a backend target a **remote** Appium — the seed of
  delegation.
- Streaming is plain **HTTP MJPEG** (`/api/phone/stream?...`) — trivially proxyable
  across hosts; a remote GUI just points an `<img>` at `node:5055/api/phone/stream`.
- The device model already carries `platform` (`ios`/`android`), `host_state`,
  `appium_url`, and the serial encodes platform (`ios:` prefix vs raw adb serial).
- The web UI distinguishes platforms **per device**: `isIosDevice()` / `platformOf()`,
  and `effectiveStreamMode(serial)` forces MJPEG for iOS cards, RTC for Android —
  including in the multi-device grid (`multiStreamMode` is per-serial). Mixed
  iOS+Android grids already render each device with its correct pipeline.

## What's net-new (the federation layer)

1. **Node registry** — the master holds a list of Ghost nodes:
   `{ id: "mac-1", url: "http://mac-1.tailnet:5055", kind: "mac" }`. Health-pinged.
2. **Device aggregation** — the master's `/api/phone/devices` = union of every node's
   devices, each annotated with `node`. This is the "one mixed pool." Serials stay
   globally unique (`ios:<udid>` / adb serials already are; namespace by node if not).
3. **Command + stream proxy** — for a device owned by `mac-1`, the master forwards
   control calls and the stream to that node. MJPEG proxy is a straight pass-through;
   **H.264-over-WebSocket (see Streaming below) relays even more cleanly** than
   multipart MJPEG.
4. **Provisioning** — `ssh mac 'bash <(curl -sSL …/install-mcp.sh)'` installs Ghost +
   deps on the Mac; then `POST /api/fleet/nodes {url}` registers it. One-time per Mac:
   the WDA signing/trust dance (see the iOS setup guide) — needs a human at the Mac
   GUI once, then it self-heals.

### Node vs master responsibilities

| Concern | Master (Linux) | Node (Mac) |
|---|---|---|
| Orchestration, scheduling, agent loop | ✅ | — |
| Android devices (adb) | ✅ direct | — |
| iOS device host (Appium, tunnel, WDA sign) | — | ✅ (macOS-only) |
| Aggregated device list / routing | ✅ | serves its local list |
| Stream to GUI | ✅ proxies | ✅ produces |

## Streaming roadmap

Streaming is the part that most benefits the fleet, and it evolves in three steps:

### Step 1 — MJPEG (done, tuned + robust)
WDA's built-in MJPEG server (`:9100`). Tuned for the tunnel: `mjpegScalingFactor=50`
(half-res ≈ 4× less data), `mjpegServerFramerate=25`, `mjpegServerScreenshotQuality=65`
(set via `IOS_MJPEG_*`, baked into `ghost-ios`). A **stall-watchdog** samples the
rendered frame; if it's frozen for ~7.5s (silent MJPEG stall — no error event, so
health stays green) it force-reconnects with a cache-busted URL. Fine for a local
viewer; heavier and less clean to relay across a fleet.

### Step 2 — Native H.264 over WebSocket (B — the fleet transport)
Add a `/wda/stream` WebSocket route to the GhostAgent-patched WDA:
capture frames → **hardware-encode H.264/HEVC with VideoToolbox** (`VTCompressionSession`)
→ push Annex-B NAL units over the WebSocket. Browser side: **WebCodecs `VideoDecoder`**
decodes NALs → `<canvas>`. This is a real video codec instead of a stream of full
JPEGs: far less bandwidth, smoother pacing, and a single ordered byte stream that a
master relays through a WebSocket proxy without re-encoding. **This is why B is the
transport layer for the whole fleet, not just a local jank fix.**

Design notes:
- Keyframe on connect + periodic IDR so a late/relaying client can start decoding.
- Config: fps, bitrate, keyframe interval, scale — mirror the `IOS_MJPEG_*` pattern
  as `IOS_STREAM_*`.
- Fallback: if WebCodecs/route unavailable, fall back to the Step-1 MJPEG path.

**Status: native encoder BUILT.** `patches/FBH264StreamServer.ghostagent.{h,m}` —
a self-contained server that captures via `FBScreenshot`, hardware-encodes with
`VTCompressionSession` (Baseline, real-time, ~2s keyframe interval), and speaks
WebSocket (handshake + binary framing) directly over a `GCDAsyncSocket` listener.
Emits Annex-B access units (SPS/PPS prepended on keyframes). Compiles clean;
co-compiled via a textual include in `FBMjpegServer.m` + declared in
`FBMjpegServer.h` (avoids a pbxproj entry — move to its own fork target file).
Started by `FBWebServer.m` on `mjpegServerPort + 100` (e.g. 9200).

**Open decision — reachability/transport.** Appium only forwards the *one*
`mjpegServerPort` (`driver.js` `allocateMjpegServerPort`); a device port like 9200
is NOT auto-forwarded, so the browser can't hit `localhost:9200` directly. Three
ways to bridge, to pick + validate on-device:
  1. **Dedicated forward** — establish a device:9200→localhost forward (usbmux/
     tunnel) alongside Appium's. Simplest client (browser dials localhost:9200)
     but needs a forward we manage.
  2. **Backend/master WS proxy** (fleet-aligned) — Ghost proxies
     `/api/phone/h264/<device>` ↔ the node's device stream. Browser talks same-
     origin to the backend; the master relays across hosts. Best for the fleet,
     but the node still needs to reach device:9200.
  3. **Serve on WDA's :8100** (already forwarded) — integrate the WS into WDA's
     RoutingHTTPServer/CocoaHTTPServer instead of a separate port. No new forward,
     but requires CocoaHTTPServer WS integration (more vendored surgery).
  Recommendation: **2 for the fleet endgame**, but **3 is the least-friction path
  to a first working end-to-end** (no forward plumbing). Validate on-device.

**Remaining for B:** pick transport (above) → frontend WebCodecs `VideoDecoder`
→ canvas → WDA rebuild + on-device test (must be at the Mac console; codesign).

### Step 3 — Fleet relay
Master exposes `/api/fleet/stream/<device>` (WebSocket). For a node-owned device it
dials the node's `/wda/stream` and relays frames to the GUI client(s). Multiple GUI
viewers fan out from one node stream. Reconnect/backoff at the relay so a node blip
doesn't kill the viewer.

## Robustness principles (learned this session)

- **Prevent:** tunnel supervisor auto-reconnects; keychain `no-timeout`; dashboard
  auto-resets stale WDA sessions.
- **Detect early:** `ghost-ios doctor` preflights every known failure point; features
  return **diagnostics** (e.g. `/wda/speak` returns an `audio` block — that's how the
  TTS bug was cracked). Build diagnostics *into* the stream route too (fps, dropped
  frames, encoder errors).
- **Recover:** stream watchdog + reconnect; `ios-fix-wda-signing.sh` for sign/install;
  `usbmuxd` reset for a wedged CoreDevice connection.
- **No silent green:** a "healthy" light must reflect the *actual data path* (the MJPEG
  freeze taught us: green health + frozen picture is the worst failure). Stream health
  should be driven by frame-arrival, not just endpoint reachability.
