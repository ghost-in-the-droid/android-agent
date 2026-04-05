#!/usr/bin/env python3
"""
discover_rids.py — Semi-automatic RID discovery for new TikTok versions.

Navigates to key screens, dumps XML, extracts RIDs, and outputs a JSON map.
Human reviews the output and saves as rid_maps/tiktok_<version>.json.

Usage:
    # Full discovery (navigates to each screen automatically):
    python3 -m gitd.bots.common.discover_rids --device <your-serial>

    # Dump RIDs from current screen only (no navigation):
    python3 -m gitd.bots.common.discover_rids --device <your-serial> --screen current

    # Save directly to rid_maps/:
    python3 -m gitd.bots.common.discover_rids --device <your-serial> --save
"""
import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path


from gitd.bots.common.adb import Device, TIKTOK_PKG

RID_MAPS_DIR = Path(__file__).parent / "rid_maps"
PKG_PREFIX = f"{TIKTOK_PKG}:id/"


def extract_rids(xml: str) -> list[dict]:
    """Extract all TikTok resource-id nodes with their attributes."""
    results = []
    for m in re.finditer(r'<node[^>]+/?>', xml):
        node = m.group()
        rid_m = re.search(r'resource-id="([^"]*)"', node)
        if not rid_m or TIKTOK_PKG not in rid_m.group(1):
            continue
        rid = rid_m.group(1)
        short = rid.replace(PKG_PREFIX, "")

        text_m = re.search(r'\btext="([^"]*)"', node)
        desc_m = re.search(r'content-desc="([^"]*)"', node)
        bounds_m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        click_m = re.search(r'clickable="(true|false)"', node)

        results.append({
            "rid": short,
            "text": text_m.group(1) if text_m else "",
            "desc": desc_m.group(1) if desc_m else "",
            "bounds": [int(bounds_m.group(i)) for i in range(1, 5)] if bounds_m else [],
            "clickable": click_m.group(1) == "true" if click_m else False,
        })
    return results


def heuristic_match(rids: list[dict], screen: str) -> dict[str, str]:
    """Try to match RIDs to known element names by heuristics."""
    guesses = {}

    for r in rids:
        short, text, desc = r["rid"], r["text"], r["desc"]
        b = r["bounds"]

        # Search icon: content-desc="Search", ImageView, top-right area
        if desc == "Search" and b and b[1] < 250 and b[0] > 800:
            guesses["search_icon"] = short

        # Search box: EditText-like, top area, has text or is focusable
        if screen in ("search_input", "search_results") and b and b[1] < 200:
            if "EditText" in str(r) or (text and len(text) > 1 and "#" in text):
                guesses.setdefault("search_box", short)

        # Profile handle: starts with @
        if text.startswith("@") and b and b[1] > 400 and b[1] < 700:
            guesses["profile_handle"] = short

        # Drafts banner: text starts with "Drafts:"
        if text.startswith("Drafts:"):
            guesses["drafts_banner"] = short

        # User handle in Users tab: text looks like a username, repeated RID
        # (will be caught by frequency analysis below)

    return guesses


def frequency_analysis(rids: list[dict]) -> dict[str, int]:
    """Count how many times each RID appears — repeated RIDs are usually list items."""
    return Counter(r["rid"] for r in rids)


def discover(dev: Device, navigate: bool = True) -> dict:
    """Run full discovery flow. Returns a RID map dict."""
    version = dev.get_app_version(TIKTOK_PKG)
    print(f"[discover] Device: {dev.serial}")
    print(f"[discover] TikTok version: {version}")

    all_rids = {}
    screens = {}

    if navigate:
        # ── Home screen ──────────────────────────────────────────────────
        print("\n[discover] Screen: HOME")
        dev.adb("shell", "am", "force-stop", TIKTOK_PKG)
        time.sleep(1)
        dev.adb("shell", "am", "start", "-n",
                f"{TIKTOK_PKG}/com.ss.android.ugc.aweme.splash.SplashActivity")
        time.sleep(5)
        xml = dev.dump_xml()
        rids = extract_rids(xml)
        screens["home"] = rids
        guesses = heuristic_match(rids, "home")
        all_rids.update(guesses)
        print(f"  Found {len(rids)} TikTok nodes, guessed: {guesses}")

        # ── Search input ─────────────────────────────────────────────────
        print("\n[discover] Screen: SEARCH INPUT")
        # Tap search icon (use guess or content-desc)
        search_node = None
        for node_str in re.findall(r'<node[^>]+/?>', xml):
            if 'content-desc="Search"' in node_str:
                bounds_m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                if bounds_m:
                    cx = (int(bounds_m.group(1)) + int(bounds_m.group(3))) // 2
                    cy = (int(bounds_m.group(2)) + int(bounds_m.group(4))) // 2
                    dev.tap(cx, cy, delay=2.0)
                    search_node = True
                    break
        if not search_node:
            dev.tap(1011, 129, delay=2.0)

        xml = dev.dump_xml()
        rids = extract_rids(xml)
        screens["search_input"] = rids
        guesses = heuristic_match(rids, "search_input")
        all_rids.update(guesses)
        print(f"  Found {len(rids)} TikTok nodes, guessed: {guesses}")

        # ── Search results (Top tab) ─────────────────────────────────────
        print("\n[discover] Screen: SEARCH RESULTS (Top tab)")
        # Type #cat and search
        dev.adb("shell", "input", "keyevent", "KEYCODE_POUND")
        time.sleep(0.2)
        dev.adb("shell", "input", "text", "cat")
        time.sleep(0.5)
        # Tap Search button
        xml = dev.dump_xml()
        for node_str in re.findall(r'<node[^>]+/?>', xml):
            text_m = re.search(r'\btext="Search"', node_str)
            click_m = re.search(r'clickable="true"', node_str)
            if text_m and click_m:
                bounds_m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                if bounds_m and int(bounds_m.group(2)) < 200:
                    cx = (int(bounds_m.group(1)) + int(bounds_m.group(3))) // 2
                    cy = (int(bounds_m.group(2)) + int(bounds_m.group(4))) // 2
                    dev.tap(cx, cy, delay=3.0)
                    break
        xml = dev.dump_xml()
        rids = extract_rids(xml)
        screens["search_results"] = rids
        freq = frequency_analysis(rids)
        # Tile RIDs appear in pairs (2-column grid)
        tile_candidates = {rid: cnt for rid, cnt in freq.items() if cnt >= 2 and cnt <= 8}
        print(f"  Found {len(rids)} TikTok nodes")
        print(f"  Repeated RIDs (likely tile elements): {tile_candidates}")
        guesses = heuristic_match(rids, "search_results")
        all_rids.update(guesses)

        # ── Users tab ────────────────────────────────────────────────────
        print("\n[discover] Screen: USERS TAB")
        for node_str in re.findall(r'<node[^>]+/?>', xml):
            if 'text="Users"' in node_str:
                bounds_m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                if bounds_m and int(bounds_m.group(4)) < 350:
                    cx = (int(bounds_m.group(1)) + int(bounds_m.group(3))) // 2
                    cy = (int(bounds_m.group(2)) + int(bounds_m.group(4))) // 2
                    dev.tap(cx, cy, delay=2.0)
                    break
        xml = dev.dump_xml()
        rids = extract_rids(xml)
        screens["users_tab"] = rids
        freq = frequency_analysis(rids)
        # User rows: RIDs that repeat 5+ times
        user_candidates = {rid: cnt for rid, cnt in freq.items() if cnt >= 3}
        print(f"  Found {len(rids)} TikTok nodes")
        print(f"  Repeated RIDs (likely user row elements): {user_candidates}")

        # ── Profile page ─────────────────────────────────────────────────
        print("\n[discover] Screen: PROFILE")
        dev.adb("shell", "am", "force-stop", TIKTOK_PKG)
        time.sleep(1)
        dev.adb("shell", "am", "start", "-n",
                f"{TIKTOK_PKG}/com.ss.android.ugc.aweme.splash.SplashActivity")
        time.sleep(5)
        # Tap Profile tab
        xml = dev.dump_xml()
        for node_str in re.findall(r'<node[^>]+/?>', xml):
            if 'text="Profile"' in node_str:
                bounds_m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node_str)
                if bounds_m and int(bounds_m.group(2)) > 2000:
                    cx = (int(bounds_m.group(1)) + int(bounds_m.group(3))) // 2
                    cy = (int(bounds_m.group(2)) + int(bounds_m.group(4))) // 2
                    dev.tap(cx, cy, delay=3.0)
                    break
        xml = dev.dump_xml()
        rids = extract_rids(xml)
        screens["profile"] = rids
        guesses = heuristic_match(rids, "profile")
        all_rids.update(guesses)
        print(f"  Found {len(rids)} TikTok nodes, guessed: {guesses}")

    else:
        # Just dump current screen
        xml = dev.dump_xml()
        rids = extract_rids(xml)
        screens["current"] = rids
        freq = frequency_analysis(rids)
        print(f"Found {len(rids)} TikTok nodes")
        print(f"Frequency: {dict(freq.most_common(20))}")

    # ── Build output ─────────────────────────────────────────────────────
    output = {
        "version": version,
        "package": TIKTOK_PKG,
        "verified_device": dev.serial,
        "auto_guesses": all_rids,
        "screens": {
            screen: {
                "node_count": len(nodes),
                "unique_rids": list(set(r["rid"] for r in nodes)),
                "nodes_with_text": [
                    {"rid": r["rid"], "text": r["text"], "desc": r["desc"],
                     "bounds": r["bounds"]}
                    for r in nodes if r["text"] or r["desc"]
                ],
            }
            for screen, nodes in screens.items()
        },
    }

    # Stop TikTok
    dev.adb("shell", "am", "force-stop", TIKTOK_PKG)

    return output


def main():
    ap = argparse.ArgumentParser(description="Discover TikTok RIDs for a new version")
    ap.add_argument("--device", required=True, help="ADB device serial")
    ap.add_argument("--screen", default=None,
                    help="'current' to dump current screen only (no navigation)")
    ap.add_argument("--save", action="store_true",
                    help="Save directly to rid_maps/ (still needs human review)")
    ap.add_argument("--json", action="store_true", help="Output raw JSON")
    args = ap.parse_args()

    dev = Device(args.device)
    navigate = args.screen != "current"
    result = discover(dev, navigate=navigate)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Pretty print summary
        print("\n" + "=" * 60)
        print(f"TikTok v{result['version']} — RID Discovery Summary")
        print("=" * 60)

        if result["auto_guesses"]:
            print("\nAuto-detected elements:")
            for name, rid in sorted(result["auto_guesses"].items()):
                print(f"  {name:30s} → {rid}")

        for screen, data in result["screens"].items():
            print(f"\n[{screen}] {data['node_count']} nodes, "
                  f"{len(data['unique_rids'])} unique RIDs")
            if data["nodes_with_text"]:
                print("  Nodes with text/desc:")
                for n in data["nodes_with_text"][:15]:
                    label = n["text"] or n["desc"]
                    print(f"    {n['rid']:12s}  {label[:50]:50s}  {n['bounds']}")

    if args.save:
        version = result["version"]
        out_path = RID_MAPS_DIR / f"tiktok_{version}.json"
        # Build a template JSON with guesses filled in, rest as TODO
        template = {
            "version": version,
            "package": TIKTOK_PKG,
            "verified_device": args.device,
            "rids": {**{k: "TODO" for k in [
                "search_icon", "search_box", "suggestion_row", "more_btn",
                "filter_chip", "profile_tab", "profile_handle",
                "profile_display_name", "profile_stat_value",
                "profile_stat_label", "profile_video_views",
                "drafts_banner", "drafts_grid_tile",
                "user_handle", "user_stats", "user_display_name",
                "tile_handle", "tile_caption", "tile_likes", "tile_time",
                "tile_ad_label", "video_handle", "video_avatar",
                "video_likes", "video_comments", "video_favorites",
                "video_shares",
            ]}, **result["auto_guesses"]},
        }
        out_path.write_text(json.dumps(template, indent=2) + "\n")
        print(f"\nSaved template → {out_path}")
        print("Review and fill in TODO entries, then you're good to go.")


if __name__ == "__main__":
    main()
