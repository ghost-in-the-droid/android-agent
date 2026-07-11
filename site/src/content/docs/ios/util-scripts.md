---
title: "iOS Utility Scripts"
description: The ghost-ios host toolkit — one command to start, check, repair, and report on the Mac↔iPhone leg.
---

`ghost-ios` is the Mac-side host toolkit, vendored in the repo at `scripts/ios/`: the whole iOS device stack — RemoteXPC tunnel, Appium, backend, web dashboard, and a self-healing supervisor — in a single terminal window, plus preflight, a JSON device inventory, and WDA build/sign helpers. It carries no baked-in identifiers; everything is auto-detected or comes from env/config. Both humans and a remote Linux Ghost host operate the node the same way. (Full reference also ships in-repo: `scripts/ios/README.md`.)

Two ground rules, both consequences of how Apple's tooling works:

- **Run it from a GUI Terminal session** — WDA code-signing needs an interactive desktop session and fails over SSH/headless (`errSecInternalComponent`); see [Mac Setup](/ios/remote-fleet/mac-setup/).
- **It prompts for sudo once** — the iOS 17+ RemoteXPC tunnel is privileged.

## Install

There is no install step — run the scripts in place from a repo checkout. Optionally put the launcher on your `PATH`:

```bash
ln -s "$PWD/scripts/ios/ghost-ios" /usr/local/bin/ghost-ios   # optional
```

**Zero-config** works when exactly one iPhone is attached and one "Apple Development" identity is in your keychain — UDID, team, signing identity, Appium, and repo location are auto-detected. Otherwise copy the template and set the few values it can't detect:

```bash
cp scripts/ios/ghost-ios.env.example scripts/ios/ghost-ios.env
$EDITOR scripts/ios/ghost-ios.env       # e.g. IOS_DEVICE_UDID, IOS_XCODE_ORG_ID
```

`ghost-ios.env` is gitignored, so your identifiers never end up in a commit. `ghost-ios config` shows what resolved and from where.

## Subcommands

| Command | What it does |
|---|---|
| `ghost-ios up` | Start the whole stack — backend, Appium, and a **self-healing RemoteXPC tunnel supervisor** that auto-reconnects until you Ctrl-C |
| `ghost-ios doctor` | Preflight every known failure point (tunnel registry, Appium, WDA signing, device trust) with the fix for each |
| `ghost-ios status` | Tunnel / Appium / backend / dashboard health lines |
| `ghost-ios report` | Machine-readable JSON device inventory — the remote-fleet discovery source |
| `ghost-ios dashboard` | Start the web dashboard (Vite) and open it |
| `ghost-ios smoke` | Run the sample Chrome→news end-to-end smoke workflow |
| `ghost-ios speak TEXT` | Speak `TEXT` aloud on the phone (native WDA TTS) |
| `ghost-ios keychain` | One-time: grant CLI codesign access to your signing key (prevents mid-build keychain re-locks) |
| `ghost-ios rebuild-wda` | (Re)build, sign, and install the patched WebDriverAgent onto the phone |
| `ghost-ios config` | Show resolved configuration and where each value came from |
| `ghost-ios down` | Stop tunnel, Appium, and backend |

Typical first run on a fresh node:

```bash
ghost-ios keychain      # once
ghost-ios doctor        # verify every prerequisite is green
ghost-ios up            # start everything; Ctrl-C tears it down
```

## `ghost-ios report`

The discovery source the Linux side consumes (directly or via `ssh my-mac ghost-ios report`). Runs in about 1.6 s; device identity comes from `xctrace list devices` — chosen over `devicectl`, which can hang indefinitely — and is cached, so a slow Xcode toolchain still yields a full record.

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

## The files in `scripts/ios/`

| File | What |
|---|---|
| `ghost-ios` | The launcher / supervisor + all subcommands |
| `doctor.sh` | Preflight checks (invoked by `ghost-ios doctor`) |
| `fix-wda-signing.sh` | Clean WDA build + sign + install — the fix for keychain-lock codesign failures and `wda_signing_failed` loops (also reachable as `ghost-ios rebuild-wda`) |
| `lib.sh` | Shared config resolution + auto-detection (sourced by the others) |
| `ghost-ios.env.example` | Config template — copy to `ghost-ios.env` (gitignored) |

The rebuilt WDA includes Ghost's `/wda/speak` TTS patch and lands in a fixed DerivedData path so Appium reuses it on every session with no per-launch codesign — the setup step behind `IOS_USE_PREBUILT_WDA`; background in [WebDriverAgent Setup](/ios/setup/wda/).

## Using the toolkit from Linux

In a [remote fleet](/ios/remote-fleet/), the Linux host runs the report over the restricted SSH key (the forced-command wrapper must allow exactly this command):

```bash
ssh my-mac ghost-ios report
```

That one line is device discovery: no hand-typed UDIDs, no stale device lists.
