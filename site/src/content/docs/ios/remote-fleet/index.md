---
title: "Remote Fleet: iPhones from Linux"
description: Drive a USB iPhone attached to a Mac from a Linux Ghost host over one SSH tunnel — topology, principles, and rollout status.
---

Your Ghost host runs on Linux, but iPhones can only be driven from a Mac. The remote-fleet feature bridges that gap with one SSH tunnel:

```
Linux Ghost host ──SSH──> Mac (Appium + WDA) ──RemoteXPC tunnel──> USB iPhone
```

The iPhone-facing leg (RemoteXPC tunnel, code-signing, WDA lifecycle) stays **entirely Mac-local** — exactly as in a single-Mac setup. The only new leg is Ghost→Mac, and it follows one core principle:

> **The Ghost host talks to Appium/WDA HTTP over an SSH port-forward; it never touches the device's IPv6 tunnel directly.**

## Why a Mac is unavoidable

`xcodebuild`/`codesign`, the CoreDevice/RemoteXPC tunnel, and the Simulator runtime are macOS-only with no Linux equivalent. Linux cannot talk to an iPhone. So "iOS in the fleet" means "the fleet contains at least one always-logged-in Mac node" — the Mac is a dumb worker, the Linux master stays the brain.

## How it fits together

- **One persistent, multiplexed SSH tunnel per Mac** (`ControlMaster` + `ControlPersist`, supervised with `autossh`), forwarding four ports: Appium `:4723` (control plane), WDA `:8100` (direct `/wda/*` calls Appium doesn't proxy), MJPEG `:9100`, H.264 WebSocket `:9200`. Not per-session forwards — one warm tunnel, sessions come and go.
- **Latency is WDA-bound, not transport-bound.** Measured WDA-side: `status` ~5 ms, `screenshot` ~190 ms, `tap` ~730 ms. LAN SSH adds ~1–3 ms — HTTP-over-SSH is comfortably good enough for interactive control.
- **An SSH drop does not kill your session.** The Appium/WDA session lives on the Mac and survives a transport blip until Appium's `newCommandTimeout` (default posture: 300 s). Ghost reconnects with backoff, revalidates the cached session, and reattaches — it re-initializes only if the session actually expired.
- **Remote devices are named, not numbered.** A remote iPhone is `my-iphone-15-pro@my-mac` — the UDID stays out of the ref and is resolved on the Mac. Refs stay stable and human-readable; a phone that moves Macs just changes its `@host`.
- **Destructive actions get a confirmation gate.** A remote phone is often a real, personal device. Destructive tool calls on a remote device return `CONFIRM_REQUIRED` unless explicitly confirmed. See [Security](/ios/remote-fleet/security/).

## Rollout status

Remote fleet is rolling out in slices. **Local (on-Mac) iOS automation and streaming work today**; the Linux→Mac remote-drive path becomes real-device-ready once the security hardening lands — it is deliberately gated on that, not on features.

| Piece | Status |
|---|---|
| `remotes:` config, `<name>@<host>` ref grammar, remote→iOS routing | ✅ Built (slice 1) |
| Destructive-action confirmation gate | ✅ Built (slice 1) |
| `ghost-ios report --json` device discovery from the Mac | 🚧 In progress (slice 2) |
| Security hardening pass (gates real-device remote use) | 🚧 In progress |
| Remote H.264 streaming over the forwarded port | 🔜 Pending |
| WireGuard underlay, SSH certificate CA (multi-site fleets) | 🔮 Planned |

## Setup guides

Set up the two ends in order:

1. **[Mac Setup](/ios/remote-fleet/mac-setup/)** — auto-login session, restricted SSH key, keychain, installer
2. **[Linux Setup](/ios/remote-fleet/linux-setup/)** — `remotes:` config, the tunnel, device refs, probing
3. **[Security Model](/ios/remote-fleet/security/)** — threat model and why it's built this way
