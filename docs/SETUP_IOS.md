# iOS Setup

Ghost in the Droid supports iOS through Appium XCUITest and WebDriverAgent.
Android devices still use ADB. iOS devices are addressed with `ios:<udid>`.

## Requirements

- macOS with Xcode installed.
- A physical iPhone or an iOS simulator.
- For a real iPhone: trust the Mac, enable Developer Mode, enable UI Automation if prompted, and sign WebDriverAgent with an Apple developer team.
- Node.js and Appium 2.
- `ffmpeg` if you want iOS test-runner screen recordings from the WDA MJPEG stream.

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
export IOS_MJPEG_SERVER_PORT="9100"
export IOS_MJPEG_SERVER_FRAMERATE="12"
export IOS_MJPEG_SCALING_FACTOR="60"
export IOS_MJPEG_SERVER_SCREENSHOT_QUALITY="45"
export IOS_MJPEG_FIX_ORIENTATION="false"
export IOS_SCREENSHOT_QUALITY="2"
export IOS_MJPEG_SCREENSHOT_URL="" # optional explicit WDA MJPEG URL override
export IOS_KNOWN_APPS_JSON='{"Chrome":"com.google.chrome.ios","TikTok":"com.zhiliaoapp.musically"}'
```

`IOS_WDA_URL` lets Ghost/Appium attach to an already-running WebDriverAgent in a later setup. The default path lets Appium create and manage the WDA session.
`IOS_KNOWN_APPS_JSON` augments iOS app discovery. iOS does not expose Android-style full package enumeration, so Ghost combines configured bundle IDs and common bundle IDs, then verifies them through Appium when WDA is available.
On macOS hosts with Xcode tools, Ghost also discovers connected iPhones and
booted iOS simulators from `xcrun xctrace list devices`. Explicit env/JSON
config is still the place to set Appium URLs, WDA URLs, ports, and signing
capabilities; host discovery only supplies device refs and labels.

For multiple iPhones, use `IOS_DEVICE_UDIDS` plus a JSON config blob or file:

```bash
export IOS_DEVICE_UDIDS="00008110-0012345678901234,00008101-0098765432109876"
export IOS_DEVICES_JSON='{
  "00008110-0012345678901234": {
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
    "mjpeg_fix_orientation": false,
    "screenshot_quality": 2,
    "wda_launch_timeout": 180000
  },
  "00008101-0098765432109876": {
    "appium_url": "http://127.0.0.1:4725",
    "bundle_id": "com.apple.mobilesafari",
    "mjpeg_server_port": 9101
  }
}'
```

Equivalent file-based setup:

```bash
export IOS_CONFIG_FILE="$PWD/config/ios-devices.json"
```

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
The smoke scripts can also use the first discovered iOS device automatically
when `IOS_DEVICE_UDID` and `--device` are omitted.

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
device_health("ios:<udid>")
fix_device_health("ios:<udid>", "reset_session")
open_url("ios:<udid>", "https://text.npr.org/", "com.google.chrome.ios")
extract_articles("ios:<udid>", 5)
get_screen_tree("ios:<udid>")
```

For REST/dashboard readiness checks, the normal device list uses a lightweight
Appium status probe. Use a deep probe when you need WDA session, screenshot, and
source readiness:

```bash
curl "http://localhost:5055/api/phone/devices?probe=deep" | python3 -m json.tool
curl "http://localhost:5055/api/phone/health/ios:<udid>" | python3 -m json.tool
```

The Phone Admin dashboard reads the same health payload. For iOS devices it
shows Appium/WDA health dots, recovery steps, and an action button when
`recommended_fix` is one of `reset_session`, `appium_session`, `wda_session`,
`start_appium`, or `restart_remote_xpc_tunnel`. The button calls
`/api/phone/health/<device>/fix`; manual recovery states still show steps only.
`start_appium` is automatic only for local HTTP Appium URLs such as
`http://127.0.0.1:4723`; remote or HTTPS Appium URLs return manual steps.

Chrome/news workflow smoke:

```bash
IOS_DEVICE_UDID="<udid>" IOS_BUNDLE_ID="com.google.chrome.ios" \
python scripts/ios_chrome_news_smoke.py \
  --url https://text.npr.org/ \
  --max-headlines 5 \
  --max-articles 3 \
  --out-dir data/ios_chrome_news_smoke
```

The script runs `/api/phone/health`-equivalent Appium/WDA preflight first and saves `health.json` plus `result.json` in the output directory. If WDA is locked, unsigned, or unreachable, `result.json` contains the health recovery payload instead of failing later in the workflow. Use `--skip-health` only when you intentionally want to jump straight to the browser workflow. It is a product-path smoke: it calls the same `read_news` service used by REST, MCP, and agent tools, including navigation readiness checks and WebView/native/OCR extraction fallback. Inspect `result.json.extraction` after live runs to see which source produced headlines/article text and whether readiness waits hit their target counts before the deadline.

To run the same Chrome/news acceptance path through pytest on a real device:

```bash
IOS_LIVE_NEWS_TEST=1 IOS_DEVICE_UDID="<udid>" IOS_APPIUM_URL="http://127.0.0.1:4723" \
IOS_BUNDLE_ID="com.google.chrome.ios" \
uv run --extra test python -m pytest tests/test_browser_news.py::test_live_ios_chrome_news_workflow
```
```

CI runs the non-live iOS parity suite on PRs to `main`, `master`, `rc/**`, and
`ios`. Those tests mock Appium/WDA and skip live-device checks unless the live
environment variables above are set.

The demo skill is still named `safari` for compatibility, but it now defaults to Chrome and can launch any configured iOS browser bundle id:

```bash
IOS_BUNDLE_ID="com.google.chrome.ios" \
python -m gitd.skills._run_skill \
  --device "ios:<udid>" \
  --skill safari \
  --workflow open_ghost_site
```

It also exposes the scheduler-ready Chrome/news workflow:

```bash
IOS_BUNDLE_ID="com.google.chrome.ios" \
python -m gitd.skills._run_skill \
  --device "ios:<udid>" \
  --skill safari \
  --workflow read_news \
  --params '{"url":"https://text.npr.org/","max_headlines":5,"max_articles":3,"save_screenshots":true}'
```

The first TikTok iOS skill is intentionally smoke-level. It can launch TikTok,
run a search, or navigate to Profile and return visible-text evidence through
the scheduler-safe `profile_smoke` workflow:

```bash
python -m gitd.skills._run_skill \
  --device "ios:<udid>" \
  --skill tiktok_ios \
  --workflow profile_smoke \
  --params '{"max_lines": 40}'
```

External marketing agents can enqueue safe iOS TikTok smoke workflows without a
video file by calling the marketing-jobs seam with an explicit smoke action:

```bash
curl -X POST http://localhost:5055/api/marketing-jobs/enqueue \
  -H 'Content-Type: application/json' \
  -d '{"phone_serial":"ios:<udid>","action":"profile_smoke","max_lines":40}'

curl -X POST http://localhost:5055/api/marketing-jobs/enqueue \
  -H 'Content-Type: application/json' \
  -d '{"phone_serial":"ios:<udid>","action":"search_smoke","query":"#news"}'

curl -X POST http://localhost:5055/api/marketing-jobs/enqueue \
  -H 'Content-Type: application/json' \
  -d '{"phone_serial":"ios:<udid>","action":"open_app_smoke"}'
```

TikTok upload, draft creation, and draft publishing are still Android-only.
The iOS marketing path only verifies that the connected iPhone can launch
TikTok, run a search smoke, or navigate to Profile and return visible-text
evidence through the scheduler.

## Supported First-Milestone Tools

Supported on iOS:

- `screenshot`, `screenshot_annotated`, `screenshot_cropped`
- `get_screen_tree`, `get_screen_xml`, `get_elements`
- `tap`, `tap_element`, `swipe`, `type_text`, `long_press`
- `press_key` for `HOME`, `ENTER`, and best-effort `BACK`
- `launch_app`
- `open_camera` for Camera launch plus best-effort Photo/Video/Selfie/timer controls
- `search_apps`, `list_apps`, `list_packages` for configured/common iOS bundle IDs verified through Appium
- `clipboard_get`, `clipboard_set`, `paste_text`
- `open_notifications`, `get_notifications`, and best-effort `clear_notifications` through Notification Center UI automation
- `get_phone_state`, `classify_screen`, `find_on_screen`, OCR if RapidOCR is installed
- Browser primitives: `open_url`, `web_search`, `browser_back`, `get_current_url`, `wait_for_text`, `extract_visible_text`, `extract_articles`
- REST browser routes under `/api/phone/browser/*`
- `/api/phone/stream?device=ios:<udid>` with WDA MJPEG mode when requested and screenshot polling fallback
- iOS MJPEG tuning through `IOS_MJPEG_SERVER_FRAMERATE`,
  `IOS_MJPEG_SCALING_FACTOR`, `IOS_MJPEG_SERVER_SCREENSHOT_QUALITY`,
  `IOS_MJPEG_FIX_ORIENTATION`, and per-device JSON equivalents.
  `/api/phone/health/<device>` and stream headers expose the effective WDA
  MJPEG settings. By default Ghost builds the MJPEG stream URL from the
  `IOS_APPIUM_URL` host plus `IOS_MJPEG_SERVER_PORT`; set
  `IOS_MJPEG_SCREENSHOT_URL` only when the stream is exposed through a custom
  tunnel or proxy.
- `start_screen_recording`, `stop_screen_recording`, and
  `/api/phone/recording/*` routes using WDA MJPEG plus `ffmpeg`
- Portal/WebRTC signaling endpoints return a structured `stream_fallback`
  payload for iOS that points clients to `/api/phone/stream?mode=mjpeg`
- Skill Creator can target `ios:<udid>` devices, uses iOS/Appium prompt
  guidance, and saves recorded skills with `platforms: ["ios"]`,
  `ios_bundle_id`, and `elements_ios.yaml`
- Test-runner recordings through the same WDA MJPEG plus `ffmpeg` path

Android-only for now:

- ADB shell commands and Android intents
- Portal overlay, Portal TTS
- Play Store helpers and arbitrary full-device package enumeration
- TikTok Android flows

## Troubleshooting

- Health responses include `connection.status`, `recommended_fix`, and a
  `recovery.steps` list. The dashboard and `fix_device_health` can apply the
  supported automatic fixes; manual states should show the recovery steps.
- `Could not create Appium iOS session`: confirm Appium is running and `IOS_APPIUM_URL` is correct.
- `appium_down`: use `fix_device_health("ios:<udid>", "start_appium")` or the
  dashboard action to start local Appium; for remote Appium hosts, start it
  manually and verify `IOS_APPIUM_URL`.
- `configured_unreachable`: check `ios:<udid>`, `IOS_DEVICE_UDID`, `IOS_DEVICES_JSON`, Appium URL, WDA URL, and ports.
- `remote_xpc_tunnel_unavailable`: for physical iOS 18+ devices, stop stale
  XCUITest tunnel processes and start a fresh tunnel with
  `sudo appium driver run xcuitest tunnel-creation --udid <udid>`. Verify the
  registry entry at `http://127.0.0.1:42314/remotexpc/tunnels/<udid>` points
  to the same tunnel address reported by
  `xcrun devicectl device info details --device <udid>`. If the tunnel
  registry uses a non-default port, set `IOS_REMOTE_XPC_REGISTRY_PORT` or
  `IOS_REMOTE_XPC_REGISTRY_PORTS`. The health fix endpoint can attempt this
  with `{"issue":"restart_remote_xpc_tunnel"}` when the stale tunnel process is
  owned by the current user; root-owned tunnel processes still require sudo.
  `IOS_REMOTE_XPC_TUNNEL_START_TIMEOUT` controls how long that automatic fix
  waits for registry health before returning manual recovery steps.
- `xcodebuild failed` or `wda_signing_failed`: fix WDA signing/provisioning in Xcode; set `IOS_XCODE_ORG_ID`, `IOS_XCODE_SIGNING_ID`, and `IOS_UPDATED_WDA_BUNDLE_ID`; use `IOS_SHOW_XCODE_LOG=true` for detailed xcodebuild output.
- Session hangs on real device or `locked`: unlock the iPhone and accept trust/automation prompts.
- Taps land in the wrong place: compare screenshot dimensions and WDA window rect in `get_phone_state`; Ghost scales WDA points to screenshot pixels and converts back for gestures.
- Stale session: call `/api/phone/health/ios:<udid>/fix` with `{"issue":"reset_session"}`, restart Appium, or call the smoke script with `--close`.
