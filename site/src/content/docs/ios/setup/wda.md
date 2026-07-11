---
title: "WebDriverAgent Setup"
description: Sign, provision, and manage WebDriverAgent — including prebuilt and preinstalled WDA for fast, reliable sessions.
---

WebDriverAgent (WDA) is the on-device automation server that XCUITest drives. On a simulator it just works. On a **real iPhone** it must be code-signed for your device — this page is mostly about making that painless and then never thinking about it again.

## First-time signing (real device)

If session creation fails with signing, provisioning, or `xcodebuild` errors:

1. Open the XCUITest driver's WebDriverAgent project in Xcode:

   ```bash
   appium driver run xcuitest open-wda
   ```

2. Select the **WebDriverAgentRunner** target → Signing & Capabilities → set your development **Team**.
3. If the default bundle ID collides (common with free developer accounts), change it to something unique, e.g. `com.example.WebDriverAgentRunner`, and tell Ghost:

   ```bash
   export IOS_UPDATED_WDA_BUNDLE_ID="com.example.WebDriverAgentRunner"
   ```

4. Run the WebDriverAgentRunner test target once against your phone (⌘U with the device selected). Accept the "Untrusted Developer" prompt on the phone: Settings → General → VPN & Device Management → trust your certificate.

Or skip Xcode's UI and let Appium sign via config:

```bash
export IOS_XCODE_ORG_ID="EXAMPLE123"        # your Apple Team ID
export IOS_XCODE_SIGNING_ID="Apple Development"
export IOS_SHOW_XCODE_LOG="true"            # verbose xcodebuild output while debugging
```

## Signing needs a GUI login session

`codesign` fails with `errSecInternalComponent` when run from a headless context (plain SSH, CI runner without a desktop). The Mac that builds/signs WDA **must have an active Aqua (GUI) login session** and an unlocked keychain. For an interactive workstation this is automatic; for an always-on automation Mac, set up auto-login — see [Remote Fleet: Mac Setup](/ios/remote-fleet/mac-setup/).

## Prebuilt and preinstalled WDA

By default Appium builds, installs, and launches WDA on every fresh session — slow (up to minutes) and dependent on signing working right then. Two flags make sessions fast and predictable:

```bash
export IOS_USE_PREBUILT_WDA="true"        # appium:usePrebuiltWDA — don't rebuild, reuse the built .app
export IOS_USE_PREINSTALLED_WDA="true"    # appium:usePreinstalledWDA — WDA is already on the phone; just launch it
```

- **Prebuilt** skips the `xcodebuild` step: Appium installs the WDA it already built. Build once (per Xcode/iOS update), reuse forever.
- **Preinstalled** skips install too: WDA is already on the device and Appium only launches it. This is the recommended posture for always-on setups and **required thinking for remote fleets** — the Mac owns the WDA lifecycle, and a remote Ghost host never builds, signs, or spawns WDA. Combined with a warm prebuilt WDA, session start drops from minutes to seconds.

Session creation can still be slow the very first time (device symbols, tunnel warmup). Give it room:

```bash
export IOS_WDA_LAUNCH_TIMEOUT="180000"    # ms, appium:wdaLaunchTimeout
```

## Attaching to a running WDA

If WDA is already up (started by a previous session, another tool, or a remote tunnel), point Ghost straight at it:

```bash
export IOS_WDA_URL="http://127.0.0.1:8100"
```

`IOS_WDA_URL` is wired into both the Appium session capabilities (`appium:webDriverAgentUrl`) and Ghost's direct WDA calls, so the WDA client is URL-agnostic: local port, forwarded SSH port — same code path.

## Common signing blockers

| Symptom | Fix |
|---|---|
| `xcodebuild failed` / `wda_signing_failed` | Set the team on WebDriverAgentRunner in Xcode; check `IOS_XCODE_ORG_ID` / `IOS_XCODE_SIGNING_ID` / `IOS_UPDATED_WDA_BUNDLE_ID`; run with `IOS_SHOW_XCODE_LOG=true` |
| `errSecInternalComponent` | You're headless — sign from a GUI login session with the keychain unlocked |
| "Untrusted Developer" on launch | Trust the certificate on the phone under VPN & Device Management |
| Session hangs, then times out | Phone is locked, or Developer Mode is off |
| Works, then breaks after an iOS/Xcode update | Rebuild WDA once (drop `IOS_USE_PREBUILT_WDA` for one session), re-trust if needed |

More in [Troubleshooting](/ios/troubleshooting/).
