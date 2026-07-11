# ghost-ios — iOS device tooling

One command to run the whole iOS device stack for **Ghost in the Droid** on a Mac:
the RemoteXPC tunnel + Appium + backend + web dashboard + a self-healing
supervisor, in a single terminal window. Plus preflight (`doctor`), a JSON device
inventory (`report`), and WDA build/sign helpers.

These are **Mac-fleet-node operational scripts**, not part of the core product. They
carry **no baked-in identifiers** — everything is auto-detected or set via env / a
config file.

## Requirements

- **macOS with Xcode + command-line tools** (`xcrun`, `xctrace`, `devicectl`, `codesign`).
- **A GUI login session.** WDA code-signing needs an interactive desktop session;
  it fails over SSH/headless (`errSecInternalComponent`). Run these from Terminal
  on the Mac itself (or a Mac with auto-login to an unlocked desktop).
- **An Apple Developer account** added in Xcode (a free personal team works; WDA
  then needs a re-sign every 7 days).
- **Appium + the XCUITest driver:**
  ```sh
  npm i -g appium
  appium driver install xcuitest
  ```
- **The repo's Python + Node deps** (the backend in `../..` and `../../frontend`).
- An **iPhone with Developer Mode on**, connected via USB and unlocked.

## Install

No install step — run the scripts in place. Optionally put them on your `PATH`:

```sh
ln -s "$PWD/scripts/ios/ghost-ios" /usr/local/bin/ghost-ios   # optional
```

Zero-config works when exactly one iPhone is attached and one "Apple Development"
identity is in your keychain. Otherwise copy the config template and fill in the
few values it can't detect:

```sh
cp scripts/ios/ghost-ios.env.example scripts/ios/ghost-ios.env
$EDITOR scripts/ios/ghost-ios.env       # set IOS_DEVICE_UDID / IOS_XCODE_ORG_ID, etc.
```

`ghost-ios config` shows what resolved and from where.

## Usage

```
ghost-ios up          start the whole stack + self-healing tunnel supervisor (main one)
ghost-ios doctor      preflight: check every known failure point + the fix for each
ghost-ios status      tunnel / appium / backend / dashboard health
ghost-ios report      JSON inventory of attached device(s) (for remote-fleet discovery)
ghost-ios dashboard   start the web dashboard (vite) and open it
ghost-ios smoke       run the sample Chrome->news smoke test
ghost-ios speak TEXT  speak TEXT aloud on the phone (native WDA TTS)
ghost-ios keychain    one-time: grant CLI codesign access to your signing key
ghost-ios rebuild-wda (re)build + install the patched WebDriverAgent onto the phone
ghost-ios config      show resolved configuration
ghost-ios down        stop tunnel + appium + backend
```

Typical first run:

```sh
ghost-ios keychain      # once: unlock keychain + grant codesign (prevents mid-build re-lock)
ghost-ios doctor        # verify every prerequisite is green
ghost-ios up            # start everything; Ctrl-C tears it down
```

`ghost-ios report` emits (redacted example):

```json
{
  "schema": 1,
  "host": "mac1",
  "generated_at": "2026-01-01T00:00Z",
  "devices": [
    { "udid": "00008XXX-XXXXXXXXXXXXXXXX", "name": "Demo iPhone",
      "ref_slug": "demo-iphone", "ios_version": "26.4.2",
      "wda_up": false, "appium_up": true, "tunnel_up": true }
  ]
}
```

`wda_up` means a WDA session is live *right now* (Appium launches WDA per session);
readiness for "can I start a session" is `tunnel_up && appium_up`.

## Files

| file | what |
|------|------|
| `ghost-ios` | the launcher / supervisor + all subcommands |
| `doctor.sh` | preflight checks (invoked by `ghost-ios doctor`) |
| `fix-wda-signing.sh` | clean WDA build + sign + install (fixes keychain-lock codesign failures) |
| `lib.sh` | shared config resolution + detection (sourced by the above) |
| `ghost-ios.env.example` | config template — copy to `ghost-ios.env` |

## Notes

- **Native TTS (`speak_text` / `ghost-ios speak`)** needs the GhostAgent WDA patch
  (`patches/FBCustomCommands.ghostagent.m`) applied to the vendored WebDriverAgent and
  a rebuild (`ghost-ios rebuild-wda`). `ghost-ios doctor` reports whether it's applied.
- **iOS 17+** physical devices require the privileged RemoteXPC tunnel (`ghost-ios up`
  starts + supervises it; it needs `sudo`).
- To prevent tunnel drops, set the iPhone's **Auto-Lock to Never** while in use.
- `ghost-ios.env` is git-ignored — it may hold your UDID/team/identity; never commit it.
