---
title: "iOS Utility Scripts"
description: The ghost-ios host toolkit — one command to start, check, repair, and report on the Mac↔iPhone leg.
---

<!-- DRAFT NOTE (remove before merge): ghost-ios currently lives as an operational helper
     outside the repo tree; packaging into the repo is pending. Install section below is
     provisional until packaging lands — flagged with core-dev/ios-tester. -->

`ghost-ios` is the Mac-side host toolkit: everything about the Mac↔iPhone leg (RemoteXPC tunnel, WDA, Appium, backend) in one command, designed so both humans and a remote Linux Ghost host can operate the node the same way.

Two ground rules, both consequences of how Apple's tooling works:

- **Run it from a GUI Terminal session** — WDA code-signing needs the login keychain of an interactive desktop session and fails headless (see [Mac Setup](/ios/remote-fleet/mac-setup/)).
- **It prompts for sudo once** — the iOS 17+ RemoteXPC tunnel is privileged.

## Install

```bash
git clone https://github.com/ghost-in-the-droid/android-agent.git
cd android-agent
pip install -e .
```

<!-- [PENDING packaging]: exact ghost-ios install path once it ships in the repo tree. -->

## Subcommands

| Command | What it does |
|---|---|
| `ghost-ios up` | Start the whole stack — backend, Appium, and a **self-healing RemoteXPC tunnel supervisor** that auto-reconnects until you Ctrl-C |
| `ghost-ios doctor` | Preflight every known failure point (tunnel registry, Appium, WDA signing, device trust) and apply fixes where it can |
| `ghost-ios status` | Human-readable health lines per attached device |
| `ghost-ios report --json` | Machine-readable device inventory — the remote-fleet discovery source |
| `ghost-ios dashboard` | Launch the web dashboard (Vite) |
| `ghost-ios smoke` | Run the Chrome→news end-to-end smoke workflow |
| `ghost-ios speak` | Test native TTS through the `/wda/speak` endpoint |
| `ghost-ios keychain` | One-time grant of CLI codesign access to the login keychain |
| `ghost-ios rebuild-wda` (alias `wda`) | Rebuild and re-sign WebDriverAgent (see below) |
| `ghost-ios down` | Stop tunnel, Appium, and backend |

Day-one sequence on a fresh node: `keychain` (once) → `up` → `status`.

## `ghost-ios report --json`

The discovery source the Linux side consumes (directly or via `ssh my-mac ghost-ios report --json`). Runs in about 1.6 s; device identity comes from `xctrace list devices` — chosen over `devicectl`, which can hang indefinitely — and is cached, so a slow Xcode toolchain still yields a full record.

```json
{
  "schema": 1,
  "host": "mac1",
  "generated_at": "2026-01-01T00:00Z",
  "devices": [
    {
      "udid": "00008XXX-XXXXXXXXXXXXXXXX",
      "name": "Demo iPhone",
      "ref_slug": "demo-iphone",
      "ios_version": "26.4.2",
      "wda_up": false,
      "appium_up": true,
      "tunnel_up": true
    }
  ]
}
```

Field notes:

| Field | Meaning |
|---|---|
| `schema` | Envelope version (currently `1`) — the envelope is extensible on purpose |
| `host` | The Mac self-identifies; useful when aggregating several nodes |
| `ref_slug` | Slug of the phone's *user-assigned* device name — this is the `<name>` in `<name>@<host>` refs. Two phones of the same model stay distinct |
| `wda_up` | A WDA session is live *right now*. Idle ⇒ `false` (normal — Appium launches WDA per-session) |
| `appium_up` / `tunnel_up` | The two legs that must both be up to start a session: readiness = `tunnel_up && appium_up` |

## WDA build/signing repair

`ios-fix-wda-signing.sh` (companion script, also reachable as `ghost-ios rebuild-wda`) builds and signs a known-good prebuilt WebDriverAgent — including Ghost's `/wda/speak` TTS patch — into a fixed DerivedData path, so Appium reuses it on every session with **no per-launch codesign**. This is the fix for `wda_signing_failed` loops and the setup step behind `IOS_USE_PREBUILT_WDA`; background in [WebDriverAgent Setup](/ios/setup/wda/).

## Using the toolkit from Linux

In a [remote fleet](/ios/remote-fleet/), the Linux host runs the report over the restricted SSH key (the forced-command wrapper must allow exactly this command):

```bash
ssh my-mac ghost-ios report --json
```

That one line is device discovery: no hand-typed UDIDs, no stale device lists.
