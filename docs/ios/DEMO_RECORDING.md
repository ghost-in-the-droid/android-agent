# iOS demo recording — how it's done

How we capture agent-driven iOS demos (phone video + terminal cast) for the
marketing pipeline, plus the hard-won gotchas. Companion to
[REMOTE_DRIVE.md](REMOTE_DRIVE.md) and the `scripts/ios/` tooling.

## TL;DR pipeline

1. **Stack up:** `ghost-ios up` (RemoteXPC tunnel + Appium + backend + supervisor).
2. **Drive the phone:** an agent (Claude Code TUI, or `ghost "<task>"`) runs a task
   on `ios:<udid>`.
3. **Capture the phone:** `ghost-ios record` (silent, WDA MJPEG) or QuickTime
   (`record-av.sh`, video **+ audio**).
4. **Capture the terminal:** `asciinema rec --cols 100 --rows 24 --idle-time-limit`
   **NOT set** (real timing — no idle compression, so terminal stays synced to the
   phone video). The marketing pipeline (`record_demo.py`) does this via a
   `spec.yaml` (`terminal_exec` action) + `--_inner` replay.
5. **Composite + deliver:** `record_demo.py --demo <name> --serial <ios>` composites
   (phone panel in an iPhone-15-Pro bezel on a 1920×1080 canvas @30fps). Deliver to
   the Linux showcase (see below).

## Capturing the phone screen

Two methods, both proven on real hardware:

**A. Silent — WDA MJPEG (smooth, ~25fps)** — the default/baseline:
```sh
curl -sN "http://[<tunnel-addr>]:9100" \
  | ffmpeg -y -f mpjpeg -i - -an -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
      -c:v libx264 -pix_fmt yuv420p out.mp4
# stop with SIGINT (finalizes the mp4). The WDA mjpeg server only serves when a
# session set mjpegServerPort; a plain raw session doesn't start it.
```
Wrapped as `ghost-ios record [seconds] [--out PATH]`.

**B. Screenshot-sequence (fallback, ~6fps)** — when the mjpeg server won't start:
poll `GET /session/<sid>/screenshot` (base64 PNG) as fast as possible, save frames,
`ffmpeg -framerate <fps> -i f%04d.png ... -r 30 out.mp4`. Choppier, but robust.

**C. With AUDIO — QuickTime / CoreMediaIO** — the *only* way to get the phone's
system audio (an app talking, TTS): a human does QuickTime → New Movie Recording →
iPhone as **Camera + Mic** → record → save `.mov`, then `scripts/ios/record-av.sh
<mov>` transcodes to a crisp `H.264 High + AAC` mp4. **Cannot be automated headless**
(GUI only). Native iPhone res is 1179×2556 → pad to even (1180) for yuv420p; keeps
the bezel calibration.

## Driving the phone

The MCP tools (`launch_app`, `tap`, `screenshot`…) drive `IOSDevice`. Two transports:
- **Appium (default):** IOSDevice → Appium `:4723` → WDA. Fragile — Appium does a
  **CoreDevice device lookup** that dies when the connection wedges (`Could not find
  the expected device`).
- **Direct-WDA (`IOS_WDA_DIRECT=1`, PR #52):** IOSDevice talks straight to WDA over
  the RemoteXPC tunnel, **no Appium, no device lookup** → immune to the CoreDevice
  wedge. Base URL resolves FRESH per session from the registry
  (`IOS_REMOTEXPC_REGISTRY`, default `http://127.0.0.1:42314`). This is the durable
  fix; it's the exact HTTP recipe used to make every baseline clip. See
  [REMOTE_DRIVE.md] for the endpoint map.

For the **Claude Code TUI hero** style: `scripts/showcase/claude_tui_driver.py`
spawns a real Claude Code TUI via pexpect (24×100 PTY), mirrors it to stdout so
asciinema records the native render. The claude session must have
`GITD_ENABLE_IOS=1` in the android-agent MCP server env (iOS ships gate-OFF by
default) or it won't see `ios:` tools, and `--strict-mcp-config --mcp-config
.mcp.json` so only android-agent loads.

## Delivery to the showcase

`scp` the clip to the showcase host over your configured SSH route and place it in
the demo server's serve-root under `ios-test/demo.mp4` (the pipeline's
`site/public/showcase/` dir), so it previews at
`http://<showcase-host>:8899/ios-test/demo.mp4`. The pipeline converts mp4→webm there.
(Deployment host/paths are environment-specific — see the internal fleet config, not
this public doc.)

## Gotchas that WILL bite (learned the hard way)

- **DeveloperDiskImage must be mounted** or WDA's xcodebuild dies instantly / times
  out ("failed to initialize for UI testing / enabling automation mode"). The DDI
  **won't mount while the phone is locked**. Fix: unlock + Auto-Lock=Never +
  Developer Mode ON, then restart the phone (toggling Dev Mode forces it). Check in
  Xcode → Devices.
- **Appium can't find the device** = the CoreDevice/usbmux wedge → `ghost-ios reset`
  (bounces usbmuxd/remoted/CoreDeviceService). The direct-WDA transport sidesteps
  this entirely.
- **Physical connection is everything.** A marginal cable/port (charges but no data
  enumeration, touch-sensitive, iPhone popping in/out of Photos) makes the WDA
  automation handshake time out even when it "looks" connected. Use a real **data**
  cable (Thunderbolt/USB4 or genuine Apple), clean the iPhone's USB-C port (lint
  blocks data pins but not power), direct Mac port, phone propped still. No software
  works around a phone that isn't solidly on the data bus.
- **Don't compress idle time** in the terminal cast (agg render uses
  `--idle-time-limit 600`) — real timing keeps terminal↔phone in sync.
- **Disable Photos auto-open** so it stops grabbing the device on each connect:
  `defaults -currentHost write com.apple.ImageCapture disableHotPlug -bool YES`.
