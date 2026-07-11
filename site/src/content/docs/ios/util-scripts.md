---
title: "iOS Utility Scripts"
description: The ghost-ios host toolkit — status, JSON reports, doctor preflight, and WDA signing repair on the Mac node.
---

<!-- DRAFT NOTE (remove before merge): sections marked [PENDING ios-tester] await the
     util-script inventory interview — exact install path, args, and sample outputs. -->

`ghost-ios` is the Mac-side host toolkit: everything about the Mac↔iPhone leg (tunnel, WDA, Appium health) in one command, designed so both humans and the Linux Ghost host can query the node the same way.

## Install

<!-- [PENDING ios-tester]: confirm packaging/install path for the toolkit. -->

The toolkit ships with the repo and installs on the Mac node alongside Ghost:

```bash
git clone https://github.com/ghost-in-the-droid/android-agent.git
cd android-agent
pip install -e .
```

## `ghost-ios status`

Human-readable node overview: attached devices plus tunnel/WDA/Appium health per phone. Your first stop when anything on the Mac leg misbehaves.

```bash
ghost-ios status
```

## `ghost-ios report --json`

The machine-readable version — the discovery source the Linux side consumes (directly or via `ssh <mac> ghost-ios report --json`). Runs in about 1.6 s; device identity comes from `xctrace list devices` (chosen over `devicectl`, which can hang indefinitely) and is cached, so a slow Xcode toolchain still yields a full record.

```json
{
  "schema": 1,
  "host": "my-mac",
  "generated_at": "2026-07-11T21:33Z",
  "devices": [
    {
      "udid": "00008110-0012345678901234",
      "name": "my iPhone",
      "ref_slug": "my-iphone",
      "ios_version": "26.4",
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

## `ghost-ios doctor`

Preflight that walks every known failure point of the Mac leg — tunnel registry, Appium, WDA signing state, device trust — before you burn time on a session that was never going to start.

```bash
ghost-ios doctor
```

<!-- [PENDING ios-tester]: doctor's exact check list + sample output. -->

## WDA build/signing helpers

`ios-fix-wda-signing.sh` repairs the WDA signing/install state (the fix for `wda_signing_failed` loops) — see [WebDriverAgent Setup](/ios/setup/wda/) for when signing breaks and why it needs a GUI session.

<!-- [PENDING ios-tester]: helper script inventory — exact names/paths/args for the WDA
     build helpers, and any additional utilities to document here. -->

## Using the toolkit from Linux

In a [remote fleet](/ios/remote-fleet/), the Linux host runs these over the restricted SSH key (the forced-command wrapper must allow the report command):

```bash
ssh my-mac ghost-ios report --json
```

That one line is device discovery: no hand-typed UDIDs, no stale device lists.
