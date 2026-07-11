---
title: "Verify the Connection"
description: Prove the whole iOS stack works — dry-run device resolution, health probes, smoke scripts, and MCP checks.
---

Verify in layers, cheapest first. Each step isolates a different failure point, so when something breaks you know *which* leg is broken instead of staring at a generic session error.

## 1. Dry-run: what does Ghost think is connected?

Before touching Appium/WDA, inspect the resolved device/config plan:

```bash
uv run python scripts/ios_chrome_news_smoke.py --list-devices

IOS_DEVICE_UDID="<udid>" IOS_BUNDLE_ID="com.google.chrome.ios" \
uv run python scripts/ios_chrome_news_smoke.py --dry-run --no-simulators
```

`--list-devices` and `--dry-run` print configured plus host-discovered iPhones and booted simulators, the selected `ios:<udid>` ref, Appium URL, bundle defaults, WDA URL, and MJPEG settings — **without creating a session**. Use `--no-simulators` when the run must target real hardware only.

## 2. Health probe

```bash
curl "http://localhost:5055/api/phone/devices?probe=deep" | python3 -m json.tool
curl "http://localhost:5055/api/phone/health/ios:<udid>" | python3 -m json.tool
```

The normal device list uses a lightweight Appium status probe; `probe=deep` additionally checks WDA session, screenshot, and source readiness. Health responses include `connection.status`, a `recommended_fix`, and a `recovery.steps` list — when Ghost can't fix something automatically, iOS RemoteXPC failures include copyable `recovery.commands`.

Apply an automatic fix:

```bash
curl -X POST "http://localhost:5055/api/phone/health/ios:<udid>/fix" \
  -H 'Content-Type: application/json' -d '{"issue":"reset_session"}'
```

The Phone Admin dashboard reads the same payload: Appium/WDA health dots, recovery steps, and a one-click fix button whenever the recovery is `auto_fixable` (`reset_session`, `appium_session`, `wda_session`, `start_appium`, `restart_remote_xpc_tunnel`).

## 3. Smoke test: a real browser workflow

The smoke script drives the same `read_news` service used by REST, MCP, and agent tools — it is a product-path test, not a synthetic ping.

```bash
IOS_DEVICE_UDID="<udid>" IOS_BUNDLE_ID="com.google.chrome.ios" \
uv run python scripts/ios_chrome_news_smoke.py \
  --url https://text.npr.org/ \
  --max-headlines 5 \
  --max-articles 3 \
  --fix-health \
  --out-dir data/ios_chrome_news_smoke
```

The script runs an Appium/WDA health preflight first and saves `health.json` plus `result.json` in the output directory. With `--fix-health` it applies the `recommended_fix` once, saves `health_fix.json`, and re-runs the preflight before opening the browser. If WDA is locked, unsigned, or unreachable, `result.json` contains the health recovery payload instead of a confusing failure deep in the workflow.

After a live run, check `result.json.extraction` to see which source produced the article text (WebView, native tree, or OCR fallback) and whether readiness waits hit their targets.

A single-screenshot variant, browser-configurable:

```bash
IOS_DEVICE_UDID="<udid>" IOS_BUNDLE_ID="com.apple.mobilesafari" \
uv run python scripts/ios_safari_smoke.py \
  --url https://ghostinthedroid.com \
  --screenshot-out data/ios_browser_smoke.png
```

## 4. From MCP

If you drive Ghost from an LLM agent, the same checks are tools:

```text
list_devices()
device_health("ios:<udid>")
fix_device_health("ios:<udid>", "reset_session")
launch_app("ios:<udid>", "com.google.chrome.ios")
open_url("ios:<udid>", "https://text.npr.org/", "com.google.chrome.ios")
get_screen_tree("ios:<udid>")
```

## 5. Live pytest (optional)

To run the Chrome/news acceptance path through pytest on a real device:

```bash
IOS_LIVE_NEWS_TEST=1 IOS_DEVICE_UDID="<udid>" IOS_APPIUM_URL="http://127.0.0.1:4723" \
IOS_BUNDLE_ID="com.google.chrome.ios" \
uv run --extra test python -m pytest tests/test_browser_news.py::test_live_ios_chrome_news_workflow
```

CI runs the non-live iOS parity suite on every PR (Appium/WDA mocked); live-device checks only run when these environment variables are set.

## What "healthy" actually means

Two independent legs must both be up, and they fail independently:

- **Appium reachable** (`appium_up`) — the control plane is listening.
- **RemoteXPC tunnel up** (`tunnel_up`) — the Mac can reach the physical device (iOS 17+).

`wda_up` means *a WDA session is live right now* — Appium launches WDA per-session, so an idle device correctly reports `wda_up: false`. The readiness signal for "can I start a session" is `tunnel_up && appium_up`, not `wda_up`.

If a step here fails, jump to [Troubleshooting](/ios/troubleshooting/) — it is organized by the same layers.
