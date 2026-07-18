"""Robust web search: pick a browser, fire a VIEW intent, fall back gracefully.

Used by both `mcp_server.web_search` (claude-code MCP) and `agent_tools.web_search`
(on-device Gemma) so the behavior is identical regardless of which agent stack
is driving.

Strategy:
1. Build a search URL for the chosen engine.
2. Probe `pm list packages` once to find which browsers are installed.
3. Try each candidate in priority order via `am start ... -p <pkg>`.
4. If all known browsers fail (or none are installed), fall back to a bare
   VIEW intent and let Android resolve it.
5. As a last resort (e.g. on devices with NO browser at all — possible on
   stripped-down vendor builds), open the Play Store search for "browser".
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

from gitd.bots.common.adb import Device

# Priority order. Chrome is overwhelmingly the default on Android, but plenty
# of devices ship Samsung Internet (Galaxy) or Vivo's stripped builds. Keeping
# this list explicit lets us announce in the result string which one we used.
_BROWSER_CANDIDATES: list[tuple[str, str]] = [
    ("Chrome", "com.android.chrome"),
    ("Firefox", "org.mozilla.firefox"),
    ("Samsung Internet", "com.sec.android.app.sbrowser"),
    ("Edge", "com.microsoft.emmx"),
    ("Brave", "com.brave.browser"),
    ("Opera", "com.opera.browser"),
    ("Opera GX", "com.opera.gx"),
    ("Vivaldi", "com.vivaldi.browser"),
    ("DuckDuckGo Browser", "com.duckduckgo.mobile.android"),
]

_ENGINE_URLS = {
    "google": "https://www.google.com/search?q=",
    "ddg": "https://duckduckgo.com/?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "bing": "https://www.bing.com/search?q=",
    "brave": "https://search.brave.com/search?q=",
}


def _installed_packages(dev: Device) -> set[str]:
    """One ADB call → set of all installed package names."""
    try:
        out = dev.adb("shell", "pm", "list", "packages", timeout=10)
    except Exception:
        return set()
    return {ln.removeprefix("package:").strip() for ln in out.splitlines() if ln.startswith("package:")}


def _try_open(dev: Device, url: str, package: Optional[str]) -> bool:
    """Run `am start ... -d <url>` (optionally scoped to a package). Return True on success."""
    cmd = ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url]
    if package:
        cmd += ["-p", package]
    try:
        out = dev.adb(*cmd, timeout=8)
    except Exception:
        return False
    # `am start` exits 0 even when the intent is unresolved, so we have to
    # parse stdout. The strings below are stable across Android 8+.
    bad = ("Error:", "java.lang.SecurityException", "no activities found")
    return not any(s in (out or "") for s in bad)


def open_search(device: str, query: str, engine: str = "google") -> str:
    """Open a search results page in the best available browser. Returns a
    human-readable status string the LLM (and the user) sees.
    """
    if not query.strip():
        return "web_search error: empty query"

    base = _ENGINE_URLS.get(engine.lower(), _ENGINE_URLS["google"])
    url = base + urllib.parse.quote(query)
    dev = Device(device)
    installed = _installed_packages(dev)

    # 1. Walk the priority list, skipping browsers that aren't installed.
    for friendly, pkg in _BROWSER_CANDIDATES:
        if pkg not in installed:
            continue
        if _try_open(dev, url, pkg):
            return f"Opened {friendly} → {engine} search for: {query}"

    # 2. No known browser worked (or none installed) — let Android resolve it.
    if _try_open(dev, url, package=None):
        return f"Opened default browser → {engine} search for: {query}"

    # 3. Last resort: nudge the user to install one. Open the Play Store
    # search for "browser" so they're one tap from a fix.
    store_url = "market://search?q=browser&c=apps"
    _try_open(dev, store_url, package=None)
    return (
        "web_search failed: no browser handled the VIEW intent. "
        "Opened Play Store to install one. (Tried: " + ", ".join(p for _, p in _BROWSER_CANDIDATES) + ")"
    )
