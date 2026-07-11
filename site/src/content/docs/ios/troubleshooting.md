---
title: "iOS Troubleshooting"
description: Diagnose iOS automation failures layer by layer — Appium, WDA, RemoteXPC tunnel, sessions, streaming, and remote fleets.
---

Work from the health payload, not from guesses: `GET /api/phone/health/ios:<udid>` returns `connection.status`, a `recommended_fix`, `recovery.steps`, and — when Ghost can't fix it automatically — copyable `recovery.commands`. `recovery.auto_fixable=true` means one call (or the dashboard button) applies the fix:

```bash
curl -X POST "http://localhost:5055/api/phone/health/ios:<udid>/fix" \
  -H 'Content-Type: application/json' -d '{"issue":"reset_session"}'
```

The sections below follow the stack bottom-up: control plane → device tunnel → WDA → session → streaming → remote.

## Appium (control plane)

**`Could not create Appium iOS session`** — confirm Appium is running and `IOS_APPIUM_URL` is right.

**`appium_down`** — `fix_device_health("ios:<udid>", "start_appium")` or the dashboard button starts a *local* Appium (`http://127.0.0.1:...` URLs only). Remote or HTTPS Appium URLs get manual steps instead — start it yourself on that host. If `appium` isn't on `PATH`, set `IOS_APPIUM_COMMAND` (e.g. `npx appium`).

**`configured_unreachable`** — some part of the config points nowhere. Re-check `ios:<udid>`, `IOS_DEVICE_UDID`, `IOS_DEVICES_JSON`, the Appium URL, WDA URL, and ports. A dry run prints the fully-resolved plan without touching the device:

```bash
uv run python scripts/ios_chrome_news_smoke.py --dry-run
```

## RemoteXPC tunnel (Mac ↔ iPhone, iOS 17+)

**`remote_xpc_tunnel_unavailable`** — the CoreDevice tunnel to the phone is down or stale:

```bash
sudo appium driver run xcuitest tunnel-creation --udid <udid>
```

Then verify the registry entry at `http://127.0.0.1:42314/remotexpc/tunnels/<udid>` points at the same tunnel address reported by `xcrun devicectl device info details --device <udid>`. Non-default registry ports: set `IOS_REMOTE_XPC_REGISTRY_PORT` / `IOS_REMOTE_XPC_REGISTRY_PORTS`.

The health fix endpoint can attempt this (`{"issue":"restart_remote_xpc_tunnel"}`) when the stale tunnel process belongs to your user; root-owned tunnels still need sudo by hand. `IOS_REMOTE_XPC_TUNNEL_START_TIMEOUT` controls how long the automatic fix waits before falling back to manual steps.

**Tunnel IPv6 quirk:** the tunnel gives the phone an `fdxx::` IPv6 address that is **only routable on the Mac itself**. Anything that discovers device URLs through the tunnel registry (e.g. stream candidates) only works Mac-locally — a remote client must use forwarded localhost ports instead. If a URL with an `fdxx::` host leaks into a remote config, that's the bug.

**Wedged CoreDevice connection** — when the tunnel won't come back at all, reset `usbmuxd` (unplug/replug USB helps too).

## WebDriverAgent

**Signing failures** (`xcodebuild failed`, `wda_signing_failed`, `errSecInternalComponent`) — see [WebDriverAgent Setup](/ios/setup/wda/); the short version: set a team in Xcode, trust the cert on the phone, and make sure signing runs in a GUI login session, never headless.

**WDA crashes or dies mid-session** — Appium relaunches WDA on the next session; with `IOS_USE_PREBUILT_WDA`/`IOS_USE_PREINSTALLED_WDA` that's seconds. Crash loops usually mean an iOS/Xcode version mismatch: rebuild WDA once against the current Xcode, re-trust, re-enable the prebuilt flags.

**`wda_up: false` on a healthy idle phone is not a fault.** Appium launches WDA per-session; `:8100` is only up while a session is live. Readiness for a new session is `tunnel_up && appium_up`.

**Single WDA owner per device.** One iPhone supports one WDA session at a time. If a local process and a remote Ghost host both drive the same phone — or two Ghost instances share it — they contend and sessions die confusingly. Route everything through the one Appium on the owning Mac so access serializes. Symptoms of a second owner: sessions that vanish immediately after creation, or `Could not create Appium iOS session` while another session is visibly running.

## Sessions

**Session hangs on a real device / `locked`** — unlock the iPhone; accept any trust/automation prompts. A locked phone is the most common hang.

**Stale session** — `{"issue":"reset_session"}` on the fix endpoint, restart Appium, or run the smoke script with `--close`.

**Session expired while you weren't looking** — Appium kills idle sessions after `newCommandTimeout` (default posture 300 s). Ghost caches session IDs and revalidates before reuse, so normally you just get a fresh session. If your workflow legitimately idles for minutes (or rides a flaky link), raise `newCommandTimeout` or send a periodic no-op `GET /status` keepalive.

**Taps land in the wrong place** — compare screenshot dimensions with the WDA window rect in `get_phone_state`. Ghost scales WDA points to screenshot pixels and back for gestures; a mismatch there (orientation change mid-session, unusual display zoom) is the culprit. Reset the session after rotating.

**Every tap takes ~3 seconds** — WDA's animation/idle quiescence waits are on. Ghost disables them by default (~0.7 s taps); if you set `IOS_WAIT_FOR_QUIESCENCE=1` (or another client re-enabled the WDA settings), that's the cost. Conversely, if a *flaky* flow mis-taps during animations, turning quiescence back on is the fix, not shorter waits.

## UDIDs and device identity

**Don't hand-maintain UDID lists — they rot.** UDIDs are 40-char opaque strings; typos and stale entries produce phantom devices that exist nowhere and mislead every later debugging step. Discover instead:

```bash
xcrun xctrace list devices        # Mac-local
ghost-ios report                  # fleet node inventory
```

Prefer name-based refs (`my-iphone@my-mac`) and let the Mac resolve name→UDID. If a configured UDID stops matching (phone restored, replaced, or re-provisioned), re-run discovery rather than editing by hand.

**`xcrun devicectl device info details` hangs** — known flake; it can hang indefinitely where `xctrace list devices` answers reliably. Ghost's tooling uses `xctrace` for identity for exactly this reason. If your own scripts wrap `devicectl`, add a timeout.

## Streaming

**Stream shows a frozen frame but health is green** — MJPEG can stall silently (no error event, connection stays open). Ghost's viewer runs a stall-watchdog that force-reconnects after ~7.5 s of frozen frames; if you consume the stream yourself, watch frame arrival, not endpoint reachability.

**Stream URL unreachable from another machine** — the MJPEG/H.264 ports are loopback-only by design. Use the documented proxy (`/api/phone/stream?device=ios:<udid>`) or, in a remote fleet, the forwarded localhost port — never try to reach the Mac's `:9100`/`:9200` directly across the network.

## Remote fleet

**Remote ref not recognized (`my-iphone@my-mac` treated as unknown device)** — the host after `@` must exactly match a remote name in the remotes map, and malformed JSON makes the whole map empty (by design, malformed entries are skipped silently). Validate: `echo "$GITD_REMOTES_JSON" | python3 -m json.tool`.

**Everything times out after a network blip** — the SSH tunnel died and isn't supervised. Run it under `autossh` (or systemd with restart). Remember the session itself survives on the Mac until `newCommandTimeout` — a supervised tunnel usually reattaches without losing the session.

**Destructive call returns `CONFIRM_REQUIRED`** — not an error: the [confirmation gate](/ios/remote-fleet/security/#the-destructive-action-confirmation-gate) is doing its job on a remote device. Re-issue with `confirm: true` if intended.

**Reconnected, but the phone leg is dead** — two failure domains: Linux→Mac SSH (yours to supervise) and Mac→iPhone RemoteXPC (the Mac's). A Linux-side reconnect must not try to repair the device tunnel; check `ghost-ios status` on the Mac.

## Still stuck?

Grab the health payload, the resolved dry-run plan, and (for remote setups) `ghost-ios report` from the Mac, and open an issue — those three artifacts answer the first ten questions we'd ask.
