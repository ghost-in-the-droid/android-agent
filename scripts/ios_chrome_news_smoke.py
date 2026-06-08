#!/usr/bin/env python3
"""Run an iOS Chrome news-reading smoke workflow through Appium/WDA.

The workflow intentionally uses Ghost's iOS device backend primitives rather
than private Appium client helpers so it validates the same path used by MCP,
REST, skills, and agent tools.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gitd.bots.common.device import get_device
from gitd.bots.common.ios import IOS_PREFIX
from gitd.services.browser import read_news
from gitd.services.device_context import device_health


def _device_ref(value: str) -> str:
    return value if value.startswith(IOS_PREFIX) else f"{IOS_PREFIX}{value}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Open Chrome on iOS, read NPR text headlines, and sample articles")
    parser.add_argument("--device", default=os.getenv("IOS_DEVICE_UDID", ""), help="iOS UDID or ios:<udid>")
    parser.add_argument(
        "--bundle-id",
        default=os.getenv("IOS_BUNDLE_ID", "com.google.chrome.ios"),
        help="iOS browser bundle id, default com.google.chrome.ios",
    )
    parser.add_argument("--url", default="https://text.npr.org/")
    parser.add_argument("--max-headlines", type=int, default=5)
    parser.add_argument("--max-articles", type=int, default=3)
    parser.add_argument("--wait", type=float, default=2.0)
    parser.add_argument("--out-dir", default="data/ios_chrome_news_smoke")
    parser.add_argument("--skip-health", action="store_true", help="Skip the Appium/WDA health preflight")
    parser.add_argument("--close", action="store_true", help="Delete the Appium session before exiting")
    args = parser.parse_args()

    if not args.device:
        print("IOS_DEVICE_UDID or --device is required", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    device = _device_ref(args.device)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        result_path = out_dir / "result.json"
        health_path = out_dir / "health.json"
        preflight_health = None
        if not args.skip_health:
            preflight_health = device_health(device)
            health_path.write_text(json.dumps(preflight_health, indent=2), encoding="utf-8")
            state = str(preflight_health.get("connection", {}).get("status") or "")
            if state != "available":
                result = {
                    "ok": False,
                    "platform": "ios",
                    "device": device,
                    "stage": "health",
                    "error": "iOS Appium/WDA health preflight is not available",
                    "health": preflight_health,
                    "health_json": str(health_path),
                    "result_json": str(result_path),
                }
                result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(json.dumps(result, indent=2))
                return 1
        result = read_news(
            device,
            args.url,
            max_headlines=args.max_headlines,
            max_articles=args.max_articles,
            bundle_id=args.bundle_id,
            wait_s=args.wait,
            save_screenshots=True,
            out_dir=str(out_dir),
        )
        if preflight_health is not None:
            result["health"] = preflight_health
            result["health_json"] = str(health_path)
        result["result_json"] = str(result_path)
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") and result.get("headlines") else 1
    finally:
        if args.close:
            get_device(device).close()


if __name__ == "__main__":
    raise SystemExit(main())
