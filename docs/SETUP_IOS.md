# iOS Setup

Ghost in the Droid supports iOS through Appium XCUITest and WebDriverAgent.
Android devices still use ADB. iOS devices are addressed with `ios:<udid>`.

## Requirements

- macOS with Xcode installed.
- A physical iPhone or an iOS simulator.
- For a real iPhone: trust the Mac, enable Developer Mode, enable UI Automation if prompted, and sign WebDriverAgent with an Apple developer team.
- Node.js and Appium 2.

## Install Appium XCUITest

```bash
npm install -g appium
appium driver install xcuitest
appium --base-path /
```

Use a separate terminal for Appium. The default backend URL is `http://127.0.0.1:4723`.

## Configure Ghost

```bash
export IOS_DEVICE_UDID="00008110-0012345678901234"
export IOS_APPIUM_URL="http://127.0.0.1:4723"
```

Optional:

```bash
export IOS_DEVICE_NAME="My iPhone"
export IOS_PLATFORM_VERSION="18.5"
export IOS_BUNDLE_ID="com.google.chrome.ios" # or another installed iOS app bundle id
export IOS_WDA_URL="http://127.0.0.1:8100"
```

`IOS_WDA_URL` lets Ghost/Appium attach to an already-running WebDriverAgent in a later setup. The default path lets Appium create and manage the WDA session.

## Real Device Signing Notes

Real devices require WDA to be signed for your phone. If session creation fails with signing, provisioning, or `xcodebuild` errors, open the XCUITest driver's WebDriverAgent project in Xcode, set a development team for WebDriverAgentRunner, and run it once against the device.

Common real-device blockers:

- The phone has not trusted the Mac.
- Developer Mode is disabled.
- WebDriverAgentRunner has no signing team.
- The device is locked.
- Another Appium/WDA session is still running.

## Simulator Shortcut

Simulators are useful for development and CI. Boot one with Xcode or `simctl`, then set `IOS_DEVICE_UDID` to the simulator UDID from:

```bash
xcrun simctl list devices booted
```

`idb` can still be useful for simulator inspection and accessibility experiments, but Ghost's first iOS backend is Appium/WDA so the same route works for real iPhones.

## Smoke Test

The smoke script is browser/app configurable. On a phone that uses Chrome:

```bash
IOS_DEVICE_UDID="<udid>" IOS_BUNDLE_ID="com.google.chrome.ios" \
python scripts/ios_safari_smoke.py \
  --url https://ghostinthedroid.com \
  --screenshot-out data/ios_chrome_smoke.png
```

On a simulator or phone with Mobile Safari available:

```bash
IOS_DEVICE_UDID="<udid>" IOS_BUNDLE_ID="com.apple.mobilesafari" \
python scripts/ios_safari_smoke.py \
  --url https://ghostinthedroid.com \
  --screenshot-out data/ios_browser_smoke.png
```

From MCP, use:

```text
list_devices()
launch_app("ios:<udid>", "com.google.chrome.ios")
get_screen_tree("ios:<udid>")
```

The demo skill is still named `safari` for compatibility, but it can launch any configured iOS browser bundle id:

```bash
IOS_BUNDLE_ID="com.google.chrome.ios" \
python -m gitd.skills._run_skill \
  --device "ios:<udid>" \
  --skill safari \
  --workflow open_ghost_site
```

## Supported First-Milestone Tools

Supported on iOS:

- `screenshot`, `screenshot_annotated`, `screenshot_cropped`
- `get_screen_tree`, `get_screen_xml`, `get_elements`
- `tap`, `tap_element`, `swipe`, `type_text`, `long_press`
- `press_key` for `HOME`, `ENTER`, and best-effort `BACK`
- `launch_app`
- `get_phone_state`, `classify_screen`, `find_on_screen`, OCR if RapidOCR is installed

Android-only for now:

- ADB shell commands and Android intents
- Portal overlay, Portal TTS, Android clipboard, notifications
- Play Store helpers and installed package search
- TikTok Android flows

## Troubleshooting

- `Could not create Appium iOS session`: confirm Appium is running and `IOS_APPIUM_URL` is correct.
- `xcodebuild failed`: fix WDA signing in Xcode.
- Session hangs on real device: unlock the iPhone and accept trust/automation prompts.
- Taps land in the wrong place: compare screenshot dimensions and WDA window rect in `get_phone_state`; Ghost scales WDA points to screenshot pixels and converts back for gestures.
- Stale session: restart Appium or call the smoke script with `--close`.
