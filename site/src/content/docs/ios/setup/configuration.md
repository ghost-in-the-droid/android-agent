---
title: "iOS Configuration"
description: Every IOS_* environment variable, multi-device JSON config, and how app discovery works on iOS.
---

Ghost's iOS backend is configured entirely through environment variables (or their JSON-config equivalents). The minimal setup is two lines:

```bash
export IOS_DEVICE_UDID="00008XXX-XXXXXXXXXXXXXXXX"
export IOS_APPIUM_URL="http://127.0.0.1:4723"
```

## Core variables

| Variable | Default | Purpose |
|---|---|---|
| `IOS_DEVICE_UDID` | — | UDID of the device to drive |
| `IOS_APPIUM_URL` | `http://127.0.0.1:4723` | Appium server (may be remote) |
| `IOS_APPIUM_COMMAND` | `appium` | Command Ghost uses to launch Appium / the tunnel (`npx appium`, absolute path, …) |
| `IOS_DEVICE_NAME` | — | Human label, e.g. `my-iphone-15-pro` |
| `IOS_PLATFORM_VERSION` | — | iOS version hint, e.g. `18.5` |
| `IOS_BUNDLE_ID` | `com.google.chrome.ios` | Default target app for browser workflows |
| `IOS_WDA_URL` | — | Attach to an already-running WebDriverAgent |
| `IOS_KNOWN_APPS_JSON` | — | Extra name→bundle-ID entries for app discovery |

If `IOS_BUNDLE_ID` is omitted, Ghost targets Chrome because the first release-quality iOS workflow is browser/news automation. Set it to `com.apple.mobilesafari` or any installed browser when needed.

## Streaming and screenshots

WDA serves an MJPEG stream that Ghost uses for live view and recordings. Tune it for your link — the defaults below are chosen for a tunnel-friendly balance:

```bash
export IOS_MJPEG_SERVER_PORT="9100"
export IOS_MJPEG_SERVER_FRAMERATE="12"
export IOS_MJPEG_SCALING_FACTOR="60"            # percent; 50 ≈ 4× less data than full-res
export IOS_MJPEG_SERVER_SCREENSHOT_QUALITY="45"
export IOS_MJPEG_FIX_ORIENTATION="false"
export IOS_SCREENSHOT_QUALITY="2"
export IOS_MJPEG_SCREENSHOT_URL=""              # only when the stream is behind a custom tunnel/proxy
```

By default Ghost builds the MJPEG URL from the `IOS_APPIUM_URL` host plus `IOS_MJPEG_SERVER_PORT`. `/api/phone/health/<device>`, `/api/phone/stream-info`, and the stream headers all expose the effective settings, so you can verify what actually applied.

## WDA lifecycle

```bash
export IOS_USE_PREBUILT_WDA="true"        # skip xcodebuild
export IOS_USE_PREINSTALLED_WDA="true"    # skip install; just launch the WDA already on the phone
export IOS_WDA_LAUNCH_TIMEOUT="180000"    # ms
export IOS_XCODE_ORG_ID="EXAMPLE123"
export IOS_XCODE_SIGNING_ID="Apple Development"
export IOS_UPDATED_WDA_BUNDLE_ID="com.example.WebDriverAgentRunner"
export IOS_SHOW_XCODE_LOG="false"
```

See [WebDriverAgent Setup](/ios/setup/wda/) for what these mean and when to use them.

## Interaction timing

Ghost disables WDA's post-interaction quiescence waits (`animationCoolOffTimeout`, `waitForIdleTimeout`) by default — that's the difference between ~2.7 s and ~0.7 s per tap. If a flaky flow needs the conservative behavior back:

```bash
export IOS_WAIT_FOR_QUIESCENCE="1"   # restore WDA's animation/idle waits (slower, more patient)
```

## Multiple iPhones

For more than one device, list the UDIDs and give each its own config block — each device gets its own Appium URL and MJPEG port so they never collide:

```bash
export IOS_DEVICE_UDIDS="00008XXX-XXXXXXXXXXXXXXXX,00008YYY-YYYYYYYYYYYYYYYY"
export IOS_DEVICES_JSON='{
  "00008XXX-XXXXXXXXXXXXXXXX": {
    "appium_url": "http://127.0.0.1:4723",
    "bundle_id": "com.google.chrome.ios",
    "known_apps": [
      {"name": "Chrome", "bundle_id": "com.google.chrome.ios"},
      {"name": "NPR", "bundle_id": "org.npr.NPR"}
    ],
    "mjpeg_server_port": 9100,
    "mjpeg_server_framerate": 12,
    "mjpeg_scaling_factor": 60,
    "mjpeg_server_screenshot_quality": 45,
    "screenshot_quality": 2,
    "wda_launch_timeout": 180000
  },
  "00008YYY-YYYYYYYYYYYYYYYY": {
    "appium_url": "http://127.0.0.1:4725",
    "bundle_id": "com.apple.mobilesafari",
    "mjpeg_server_port": 9101
  }
}'
```

Or keep it in a file:

```bash
export IOS_CONFIG_FILE="$PWD/config/ios-devices.json"
```

The same file can also hold a `remotes` key for [remote Mac hosts](/ios/remote-fleet/linux-setup/), so one config describes your whole fleet.

## App discovery on iOS

iOS does not expose Android-style full package enumeration. Ghost combines three sources, then verifies through Appium when WDA is available:

1. Bundle IDs you configure (`IOS_KNOWN_APPS_JSON`, per-device `known_apps`)
2. A built-in list of common bundle IDs
3. Appium verification of what is actually installed

```bash
export IOS_KNOWN_APPS_JSON='{"Chrome":"com.google.chrome.ios","TikTok":"com.zhiliaoapp.musically"}'
```

On macOS hosts with Xcode tools, Ghost also discovers connected iPhones and booted simulators from `xcrun xctrace list devices` — discovery supplies device refs and labels, while explicit config remains the place for URLs, ports, and signing capabilities.
