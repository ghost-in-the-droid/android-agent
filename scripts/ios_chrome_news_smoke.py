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
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gitd.bots.common.ios import IOSDevice, IOS_PREFIX


def _device_ref(value: str) -> str:
    return value if value.startswith(IOS_PREFIX) else f"{IOS_PREFIX}{value}"


def _save_screenshot(dev: IOSDevice, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dev.take_screenshot())
    return str(path)


def _snippet(text: str, max_chars: int = 1800) -> str:
    lines = []
    seen = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if sum(len(x) for x in lines) > max_chars:
            break
    return "\n".join(lines)[:max_chars]


def _tap_article(dev: IOSDevice, article: dict[str, Any]) -> None:
    center = article.get("center") or {}
    if center.get("x") is not None and center.get("y") is not None:
        dev.tap(int(center["x"]), int(center["y"]), delay=1.5)
        return
    bounds = article.get("bounds") or {}
    if {"x1", "y1", "x2", "y2"} <= set(bounds):
        x = (int(bounds["x1"]) + int(bounds["x2"])) // 2
        y = (int(bounds["y1"]) + int(bounds["y2"])) // 2
        dev.tap(x, y, delay=1.5)
        return
    raise RuntimeError(f"Article has no tappable geometry: {article}")


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
    parser.add_argument("--close", action="store_true", help="Delete the Appium session before exiting")
    args = parser.parse_args()

    if not args.device:
        print("IOS_DEVICE_UDID or --device is required", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    device = _device_ref(args.device)
    dev = IOSDevice(device, bundle_id=args.bundle_id)
    result: dict[str, Any] = {
        "device": device,
        "bundle_id": args.bundle_id,
        "url": args.url,
        "headlines": [],
        "articles": [],
        "screenshots": {},
        "errors": [],
    }

    try:
        dev.launch_app(args.bundle_id)
        dev.open_url(args.url)
        time.sleep(args.wait)

        result["screenshots"]["front_page"] = _save_screenshot(dev, out_dir / "front_page.png")
        result["current_url"] = dev.get_current_url()
        headlines = dev.extract_articles(max_items=max(1, args.max_headlines))
        result["headlines"] = headlines[: args.max_headlines]
        result["front_page_text"] = _snippet(dev.extract_visible_text(max_lines=120), max_chars=2400)

        for index, headline in enumerate(headlines[: args.max_articles], start=1):
            article_result: dict[str, Any] = {
                "index": index,
                "source_headline": headline.get("title", ""),
                "opened": False,
            }
            try:
                _tap_article(dev, headline)
                time.sleep(args.wait)
                screenshot_path = out_dir / f"article_{index}.png"
                article_result["screenshot"] = _save_screenshot(dev, screenshot_path)
                article_result["current_url"] = dev.get_current_url()
                visible_text = dev.extract_visible_text(max_lines=160)
                lines = [line.strip() for line in visible_text.splitlines() if line.strip()]
                article_result["page_title"] = lines[0] if lines else ""
                article_result["body_snippet"] = _snippet(visible_text, max_chars=2400)
                article_result["opened"] = True
            except Exception as exc:
                article_result["error"] = str(exc)
                result["errors"].append({"article": headline.get("title", ""), "error": str(exc)})
            finally:
                result["articles"].append(article_result)
                try:
                    dev.browser_back(delay=1.0)
                    time.sleep(0.5)
                except Exception as exc:
                    result["errors"].append({"article": headline.get("title", ""), "back_error": str(exc)})

        out_dir.mkdir(parents=True, exist_ok=True)
        result_path = out_dir / "result.json"
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        result["result_json"] = str(result_path)
        print(json.dumps(result, indent=2))
        return 0 if result["headlines"] else 1
    finally:
        if args.close:
            dev.close()


if __name__ == "__main__":
    raise SystemExit(main())
