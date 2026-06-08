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
from gitd.bots.common.ios import (
    IOS_PREFIX,
    IOSDevice,
    configured_ios_udids,
    discover_host_ios_devices,
    ios_config_for_udid,
    known_ios_udids,
    strip_ios_prefix,
)
from gitd.services.browser import read_news
from gitd.services.device_context import fix_device_health, ios_device_health


def _device_ref(value: str) -> str:
    return value if value.startswith(IOS_PREFIX) else f"{IOS_PREFIX}{value}"


def _default_device(value: str, *, include_simulators: bool = True) -> str:
    if value:
        return value
    known = known_ios_udids(include_simulators=include_simulators)
    return known[0] if known else ""


def _discovery_plan(selected_device: str = "", *, include_simulators: bool = True) -> dict:
    selected_udid = strip_ios_prefix(selected_device) if selected_device else ""
    configured = configured_ios_udids()
    host_devices = discover_host_ios_devices(include_simulators=include_simulators)
    host_by_udid = {item["udid"]: item for item in host_devices}
    udids: list[str] = []
    for value in [selected_udid, *configured, *(item["udid"] for item in host_devices)]:
        udid = strip_ios_prefix(str(value or ""))
        if udid and udid not in udids:
            udids.append(udid)

    devices = []
    for udid in udids:
        cfg = ios_config_for_udid(udid)
        host = host_by_udid.get(udid, {})
        source = host.get("source") or ("configured" if udid in configured else "explicit")
        devices.append(
            {
                "device": _device_ref(udid),
                "udid": udid,
                "selected": udid == selected_udid if selected_udid else udid == (udids[0] if udids else ""),
                "source": source,
                "host_state": host.get("state", ""),
                "device_name": host.get("name") or cfg.device_name,
                "platform_version": cfg.platform_version or host.get("platform_version", ""),
                "appium_url": cfg.appium_url,
                "bundle_id": cfg.bundle_id,
                "browser_name": cfg.browser_name,
                "wda_url": cfg.wda_url,
                "mjpeg_server_port": cfg.mjpeg_server_port,
                "mjpeg_screenshot_url": cfg.mjpeg_screenshot_url,
                "mjpeg_settings": cfg.mjpeg_settings(),
                "capabilities": cfg.capabilities(),
            }
        )
    selected = next((item for item in devices if item["selected"]), None)
    return {
        "ok": bool(devices),
        "selected_device": selected["device"] if selected else "",
        "devices": devices,
        "include_simulators": include_simulators,
    }


def _preflight_health(device: str, bundle_id: str) -> dict:
    ios_dev = IOSDevice(device, bundle_id=bundle_id or None)
    return ios_device_health(device, ios_dev)


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved device/config plan without creating an Appium/WDA session",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print configured and host-discovered iOS devices without running the smoke workflow",
    )
    parser.add_argument(
        "--no-simulators",
        action="store_true",
        help="Exclude booted simulators from dry-run/list discovery",
    )
    parser.add_argument("--skip-health", action="store_true", help="Skip the Appium/WDA health preflight")
    parser.add_argument(
        "--fix-health",
        action="store_true",
        help="Apply device_health.recommended_fix once, then re-run the health preflight before reading news",
    )
    parser.add_argument("--close", action="store_true", help="Delete the Appium session before exiting")
    args = parser.parse_args()

    if args.dry_run or args.list_devices:
        args.device = _default_device(args.device, include_simulators=not args.no_simulators)
        plan = _discovery_plan(args.device, include_simulators=not args.no_simulators)
        plan.update(
            {
                "workflow": "read_news",
                "url": args.url,
                "requested_bundle_id": args.bundle_id,
                "max_headlines": args.max_headlines,
                "max_articles": args.max_articles,
                "wait_s": args.wait,
                "out_dir": args.out_dir,
            }
        )
        print(json.dumps(plan, indent=2))
        return 0 if plan.get("ok") else 2

    args.device = _default_device(args.device)
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
        health_fix = None
        if not args.skip_health:
            preflight_health = _preflight_health(device, args.bundle_id)
            health_path.write_text(json.dumps(preflight_health, indent=2), encoding="utf-8")
            state = str(preflight_health.get("connection", {}).get("status") or "")
            if state != "available" and args.fix_health:
                fix_issue = str(preflight_health.get("recommended_fix") or "")
                if fix_issue:
                    health_fix = fix_device_health(device, fix_issue)
                    (out_dir / "health_fix.json").write_text(json.dumps(health_fix, indent=2), encoding="utf-8")
                    preflight_health = _preflight_health(device, args.bundle_id)
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
                    "health_fix": health_fix,
                    "health_json": str(health_path),
                    "health_fix_json": str(out_dir / "health_fix.json") if health_fix is not None else "",
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
        if health_fix is not None:
            result["health_fix"] = health_fix
            result["health_fix_json"] = str(out_dir / "health_fix.json")
        result["result_json"] = str(result_path)
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") and result.get("headlines") else 1
    finally:
        if args.close:
            get_device(device).close()


if __name__ == "__main__":
    raise SystemExit(main())
