---
title: "iOS Requirements"
description: What you need before Ghost in the Droid can drive an iPhone — macOS, Xcode, Appium 2, and a trusted device.
---

Ghost in the Droid drives iOS devices through [Appium](https://appium.io/) XCUITest and WebDriverAgent (WDA). Android devices keep using ADB — nothing about your Android setup changes.

Everything that touches an iPhone is macOS-only: `xcodebuild` and `codesign` (to build and sign WebDriverAgent), the CoreDevice/RemoteXPC tunnel to a physical device, and the Simulator runtime. **Linux cannot talk to an iPhone directly.** If your Ghost host is a Linux machine, you drive the iPhone through a Mac — see [Remote Fleet](/ios/remote-fleet/) for that topology. This page covers the Mac itself.

## Checklist

| Requirement | Why |
|---|---|
| macOS with Xcode installed | Builds and signs WebDriverAgent; provides the device tunnel |
| Node.js + Appium 2 with the XCUITest driver | The automation control plane Ghost talks to |
| A physical iPhone or a booted iOS Simulator | The device under automation |
| An Apple developer team (free tier works, but its certificates expire every 7 days — WDA needs weekly re-signing; a paid team avoids that, which matters for always-on setups) | Signs WebDriverAgent for a real device |
| `ffmpeg` (optional) | iOS screen recordings from the WDA MJPEG stream |

## Real-device prerequisites

A physical iPhone needs a one-time trust dance:

1. **Trust the Mac** — connect via USB and accept the "Trust This Computer?" prompt on the phone.
2. **Enable Developer Mode** — Settings → Privacy & Security → Developer Mode (iOS 16+). The phone reboots.
3. **Enable UI Automation** if prompted — Settings → Developer → UI Automation.
4. **Sign WebDriverAgent** with your Apple developer team — see [WebDriverAgent Setup](/ios/setup/wda/).
5. **Keep the phone unlocked** during sessions. A locked device is the single most common cause of session hangs.

## Install Appium

```bash
npm install -g appium
appium driver install xcuitest
appium --base-path /
```

Run Appium in its own terminal (or as a service). The default URL Ghost expects is `http://127.0.0.1:4723`.

If `appium` is not directly on your `PATH`, tell Ghost how to launch it:

```bash
export IOS_APPIUM_COMMAND="npx appium"   # or "/opt/homebrew/bin/appium"
```

Ghost uses the same command when it starts the XCUITest RemoteXPC tunnel for you.

## Simulator shortcut

Simulators are useful for development and CI — no signing, no trust prompts. Boot one with Xcode or `simctl`, then point Ghost at its UDID:

```bash
xcrun simctl list devices booted
export IOS_DEVICE_UDID="<simulator-udid>"
```

The same Appium/WDA route works for simulators and real iPhones, so anything you build against a simulator carries over.

## Device addressing

iOS devices are addressed with an `ios:` prefix wherever Ghost takes a device ref:

```text
ios:00008XXX-XXXXXXXXXXXXXXXX
```

Android serials stay as-is. Remote iPhones attached to another Mac use `<name>@<host>` refs instead — see [Remote Fleet](/ios/remote-fleet/).

## Next steps

- [WebDriverAgent Setup](/ios/setup/wda/) — signing, provisioning, prebuilt/preinstalled WDA
- [Configuration](/ios/setup/configuration/) — every `IOS_*` variable, multi-device JSON
- [Verify the Connection](/ios/setup/verify/) — smoke tests and health probes
