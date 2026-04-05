"""
elements.py — Version-resilient UI element resolution for ADB automation.

Instead of hardcoding resource-IDs that break on every TikTok update,
elements are resolved through a fallback chain:

    content-desc → text → RID (version-specific) → pixel fallback

Usage:
    from gitd.bots.common.elements import ElementResolver

    resolver = ElementResolver.for_device(dev)
    node = resolver.find("search_icon", xml, dev)     # find node string
    resolver.tap_element("search_icon", xml, dev)      # find and tap
    rid = resolver.rid("tile_handle")                  # raw RID for hot loops

RID maps live in rid_maps/*.json, one per known TikTok version.
Unknown versions fall back to the latest known map + print a warning.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

RID_MAPS_DIR = Path(__file__).parent / "rid_maps"

PACKAGES = {
    "tiktok": "com.zhiliaoapp.musically",
    "instagram": "com.instagram.android",
}


@dataclass
class Element:
    """A UI element with a prioritized resolution chain."""
    name: str
    desc: str | None = None          # content-desc (most stable)
    text: str | None = None          # visible text
    rid_key: str | None = None       # key into version JSON
    fallback_xy: tuple | None = None # last-resort pixel coords
    bounds_check: Callable | None = None  # e.g. lambda b: b[1] < 200


# ── TikTok element definitions ──────────────────────────────────────────────
# Elements that CAN be found by content-desc or text (survives updates):
# Elements that MUST use RID (no stable text/desc alternative):

TIKTOK = {
    # ── Home / Navigation ────────────────────────────────────────────────
    "search_icon":    Element("search_icon",    desc="Search", rid_key="search_icon",
                              fallback_xy=(1011, 129), bounds_check=lambda b: b[1] < 250),
    "search_box":     Element("search_box",     rid_key="search_box"),
    "search_button":  Element("search_button",  text="Search",
                              bounds_check=lambda b: b[1] < 200),
    "suggestion_row": Element("suggestion_row", rid_key="suggestion_row"),
    "profile_tab":    Element("profile_tab",    text="Profile",
                              fallback_xy=(972, 2244)),
    "more_btn":       Element("more_btn",       rid_key="more_btn"),
    "filter_chip":    Element("filter_chip",    rid_key="filter_chip"),

    # ── Profile page ─────────────────────────────────────────────────────
    "profile_handle":       Element("profile_handle",       rid_key="profile_handle"),
    "profile_display_name": Element("profile_display_name", rid_key="profile_display_name"),
    "profile_stat_value":   Element("profile_stat_value",   rid_key="profile_stat_value"),
    "profile_stat_label":   Element("profile_stat_label",   rid_key="profile_stat_label"),
    "profile_video_views":  Element("profile_video_views",  rid_key="profile_video_views"),
    "drafts_banner":        Element("drafts_banner",        text="Drafts:",
                                    rid_key="drafts_banner"),
    "drafts_grid_tile":     Element("drafts_grid_tile",     rid_key="drafts_grid_tile"),

    # ── Users tab ────────────────────────────────────────────────────────
    "user_handle":       Element("user_handle",       rid_key="user_handle"),
    "user_stats":        Element("user_stats",        rid_key="user_stats"),
    "user_display_name": Element("user_display_name", rid_key="user_display_name"),

    # ── Top tab tiles ────────────────────────────────────────────────────
    "tile_handle":   Element("tile_handle",   rid_key="tile_handle"),
    "tile_caption":  Element("tile_caption",  rid_key="tile_caption"),
    "tile_likes":    Element("tile_likes",    rid_key="tile_likes"),
    "tile_time":     Element("tile_time",     rid_key="tile_time"),
    "tile_ad_label": Element("tile_ad_label", rid_key="tile_ad_label"),

    # ── Full-screen video ────────────────────────────────────────────────
    "video_handle":    Element("video_handle",    rid_key="video_handle"),
    "video_avatar":    Element("video_avatar",    rid_key="video_avatar"),
    "video_likes":     Element("video_likes",     rid_key="video_likes"),
    "video_comments":  Element("video_comments",  rid_key="video_comments"),
    "video_favorites": Element("video_favorites", rid_key="video_favorites"),
    "video_shares":    Element("video_shares",    rid_key="video_shares"),
}


class ElementResolver:
    """Per-device element resolution with version-aware RID caching.

    Usage:
        resolver = ElementResolver.for_device(dev)

        # Find a node string in XML:
        node = resolver.find("search_icon", xml, dev)

        # Get raw full RID for hot-loop usage:
        rid = resolver.rid("tile_handle")
        # → "com.zhiliaoapp.musically:id/b2l"

        # Tap an element (find + tap in one call):
        resolver.tap_element("search_icon", xml, dev, delay=1.0)
    """

    _cache: dict[str, 'ElementResolver'] = {}

    @classmethod
    def for_device(cls, dev, app: str = "tiktok") -> 'ElementResolver':
        """Get or create a resolver for this device + app combo."""
        pkg = PACKAGES[app]
        ver = dev.get_app_version(pkg)
        cache_key = f"{dev.serial}:{app}:{ver}"
        if cache_key not in cls._cache:
            cls._cache[cache_key] = cls(app, ver)
        return cls._cache[cache_key]

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()

    def __init__(self, app: str = "tiktok", version: str = "unknown"):
        self.app = app
        self.version = version
        self.pkg = PACKAGES[app]
        self._rids = self._load_rid_map(app, version)
        self._elements = TIKTOK if app == "tiktok" else {}

    def _load_rid_map(self, app: str, version: str) -> dict:
        """Load RID map for this version. Falls back to latest known."""
        exact = RID_MAPS_DIR / f"{app}_{version}.json"
        if exact.exists():
            data = json.loads(exact.read_text())
            return data.get("rids", {})

        # Fall back to latest known version
        candidates = sorted(RID_MAPS_DIR.glob(f"{app}_*.json"))
        if candidates:
            latest = candidates[-1]
            print(f"[elements] No RID map for {app} v{version}, falling back to {latest.name}")
            data = json.loads(latest.read_text())
            return data.get("rids", {})

        print(f"[elements] WARNING: No RID maps found for {app}")
        return {}

    def rid(self, key: str) -> str:
        """Get full resource-id string. E.g. rid("search_icon") → "com...musically:id/j4d"

        Use this in hot loops where you pre-resolve to a local variable.
        """
        short = self._rids.get(key)
        if not short:
            raise KeyError(f"Unknown RID key: {key!r} (version={self.version})")
        return f"{self.pkg}:id/{short}"

    def rid_short(self, key: str) -> str:
        """Get just the short RID code. E.g. rid_short("search_icon") → "j4d" """
        short = self._rids.get(key)
        if not short:
            raise KeyError(f"Unknown RID key: {key!r}")
        return short

    def find(self, name: str, xml: str, dev) -> str | None:
        """Find a UI element node in XML using the resolution chain.

        Returns the node string, or None if not found.
        Resolution order: content-desc → text → RID → None
        """
        elem = self._elements.get(name)
        if not elem:
            raise KeyError(f"Unknown element: {name!r}")

        # 1. Try content-desc
        if elem.desc:
            for node in dev.nodes(xml):
                if dev.node_content_desc(node) == elem.desc:
                    if elem.bounds_check:
                        b = dev.node_bounds(node)
                        if b and not elem.bounds_check(b):
                            continue
                    return node

        # 2. Try text
        if elem.text:
            for node in dev.nodes(xml):
                if elem.text in dev.node_text(node):
                    if elem.bounds_check:
                        b = dev.node_bounds(node)
                        if b and not elem.bounds_check(b):
                            continue
                    return node

        # 3. Try RID
        if elem.rid_key:
            try:
                full_rid = self.rid(elem.rid_key)
            except KeyError:
                full_rid = None
            if full_rid:
                nodes = dev.find_nodes(xml, rid=full_rid)
                if nodes:
                    return nodes[0]

        return None

    def find_all(self, name: str, xml: str, dev) -> list[str]:
        """Find ALL matching nodes for an element (e.g. all user rows)."""
        elem = self._elements.get(name)
        if not elem:
            raise KeyError(f"Unknown element: {name!r}")

        # For multi-match, RID is most reliable (desc/text can match unrelated nodes)
        if elem.rid_key:
            try:
                full_rid = self.rid(elem.rid_key)
                return dev.find_nodes(xml, rid=full_rid)
            except KeyError:
                pass

        # Fallback to text/desc matching
        results = []
        for node in dev.nodes(xml):
            if elem.desc and dev.node_content_desc(node) == elem.desc:
                results.append(node)
            elif elem.text and elem.text in dev.node_text(node):
                results.append(node)
        return results

    def tap_element(self, name: str, xml: str, dev, delay: float = 0.8) -> bool:
        """Find and tap an element. Returns True if tapped, False if not found.

        Falls back to pixel coordinates if element not found in XML.
        """
        node = self.find(name, xml, dev)
        if node:
            return dev.tap_node(node, delay=delay)

        # Pixel fallback
        elem = self._elements.get(name)
        if elem and elem.fallback_xy:
            dev.tap(*elem.fallback_xy, delay=delay)
            return True

        return False

    def screen_type(self, xml: str, dev) -> str:
        """Classify TikTok screen using resolver (version-agnostic).

        Returns: home | search_input | search_results | users_tab | filters_panel | unknown
        """
        # Users tab: user_handle RID present
        if self.find("user_handle", xml, dev):
            return "users_tab"

        # Filters panel: filter_chip RID present
        if self.find("filter_chip", xml, dev):
            return "filters_panel"

        # Search results: "Users" text visible in tab bar (y < 350)
        for node in dev.nodes(xml):
            if dev.node_text(node) == "Users":
                b = dev.node_bounds(node)
                if b and b[3] < 350:
                    return "search_results"

        # Search input: search_box RID present but no results tabs
        if self.find("search_box", xml, dev):
            return "search_input"

        # Home: search_icon present (content-desc="Search" or RID)
        if self.find("search_icon", xml, dev):
            return "home"

        return "unknown"

    @property
    def rids(self) -> dict:
        """Raw RID map dict for inspection."""
        return dict(self._rids)

    def __repr__(self):
        return f"ElementResolver(app={self.app!r}, version={self.version!r}, rids={len(self._rids)})"
