#!/usr/bin/env python3
"""Smoke test an iOS browser/app through Appium/WebDriverAgent.

Usage:
  IOS_DEVICE_UDID=<udid> IOS_APPIUM_URL=http://127.0.0.1:4723 \
    IOS_BUNDLE_ID=com.google.chrome.ios python scripts/ios_safari_smoke.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gitd.bots.common.ios import IOSDevice, IOS_PREFIX
from gitd.services.device_context import get_screen_tree


def _device_ref(value: str) -> str:
    return value if value.startswith(IOS_PREFIX) else f"{IOS_PREFIX}{value}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch an iOS browser/app using the iOS backend")
    parser.add_argument("--device", default=os.getenv("IOS_DEVICE_UDID", ""), help="iOS UDID or ios:<udid>")
    parser.add_argument(
        "--bundle-id",
        default=os.getenv("IOS_BUNDLE_ID", "com.apple.mobilesafari"),
        help="iOS bundle id to launch, for example com.google.chrome.ios",
    )
    parser.add_argument(
        "--browser-name",
        default=os.getenv("IOS_BROWSER_NAME", ""),
        help="Optional Appium browserName. Leave empty for native bundle-id automation.",
    )
    parser.add_argument("--url", default="https://ghostinthedroid.com")
    parser.add_argument("--no-open-url", action="store_true", help="Only launch the app; do not call WebDriver /url")
    parser.add_argument("--screenshot-out", default="", help="Optional path to write the final PNG screenshot")
    parser.add_argument("--close", action="store_true", help="Delete the Appium session before exiting")
    args = parser.parse_args()

    if not args.device:
        print("IOS_DEVICE_UDID or --device is required", file=sys.stderr)
        return 2

    device = _device_ref(args.device)
    dev = IOSDevice(device, bundle_id=args.bundle_id, browser_name=args.browser_name)
    try:
        dev.launch_app(args.bundle_id)
        if not args.no_open_url:
            dev.open_url(args.url)
            time.sleep(2)

        state = dev.get_phone_state()
        print(json.dumps(state, indent=2))
        print("\n[Screen tree]")
        print(get_screen_tree(device, max_nodes=40))

        if args.screenshot_out:
            out = Path(args.screenshot_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(dev.take_screenshot())
            print(f"\nScreenshot: {out}")
    finally:
        if args.close:
            dev.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
