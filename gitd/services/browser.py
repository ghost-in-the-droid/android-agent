"""Platform-aware browser helpers."""
from __future__ import annotations

import json
import urllib.parse
from typing import Any

from gitd.bots.common.device import get_device, is_ios_ref


_ENGINE_URLS = {
    "google": "https://www.google.com/search?q={query}",
    "ddg": "https://duckduckgo.com/?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "brave": "https://search.brave.com/search?q={query}",
}


def _normalize_url(url: str) -> str:
    cleaned = url.strip()
    if cleaned and "://" not in cleaned:
        cleaned = "https://" + cleaned
    return cleaned


def _search_url(query: str, engine: str = "google") -> str:
    template = _ENGINE_URLS.get(engine.lower(), _ENGINE_URLS["google"])
    return template.format(query=urllib.parse.quote_plus(query))


def open_url(device: str, url: str, bundle_id: str | None = None) -> dict[str, Any]:
    normalized_url = _normalize_url(url)
    if is_ios_ref(device):
        dev = get_device(device)
        if bundle_id:
            dev.bundle_id = bundle_id
        dev.open_url(normalized_url)
        return {"ok": True, "platform": "ios", "url": dev.get_current_url() or normalized_url}

    from gitd.services.device_context import launch_intent

    out = launch_intent(device, action="android.intent.action.VIEW", data=normalized_url)
    return {"ok": not out.lower().startswith("error"), "platform": "android", "result": out, "url": normalized_url}


def web_search(device: str, query: str, engine: str = "google", bundle_id: str | None = None) -> dict[str, Any]:
    url = _search_url(query, engine)
    result = open_url(device, url, bundle_id=bundle_id)
    result["query"] = query
    result["engine"] = engine
    return result


def browser_back(device: str) -> dict[str, Any]:
    dev = get_device(device)
    if is_ios_ref(device) and hasattr(dev, "browser_back"):
        dev.browser_back()
    else:
        dev.back()
    return {"ok": True, "platform": "ios" if is_ios_ref(device) else "android"}


def get_current_url(device: str) -> dict[str, Any]:
    dev = get_device(device)
    if is_ios_ref(device) and hasattr(dev, "get_current_url"):
        return {"ok": True, "platform": "ios", "url": dev.get_current_url()}
    return {"ok": False, "platform": "android", "error": "Current URL is not implemented for Android yet"}


def wait_for_text(device: str, text: str, timeout: float = 12.0) -> dict[str, Any]:
    dev = get_device(device)
    if is_ios_ref(device) and hasattr(dev, "wait_for_text"):
        visible = dev.wait_for_text(text, timeout=timeout)
        return {"ok": True, "platform": "ios", "text": text, "visible_text": visible}

    from gitd.services.device_context import find_on_screen

    found = find_on_screen(device, text)
    return {"ok": bool(found), "platform": "android", "text": text, "match": found}


def extract_visible_text(device: str, max_lines: int = 200, include_controls: bool = False) -> dict[str, Any]:
    dev = get_device(device)
    if is_ios_ref(device) and hasattr(dev, "extract_visible_text"):
        text = dev.extract_visible_text(include_controls=include_controls, max_lines=max_lines)
        return {"ok": True, "platform": "ios", "text": text, "lines": text.splitlines()}

    from gitd.services.device_context import get_interactive_elements

    lines = []
    for element in get_interactive_elements(device, interactive_only=False):
        label = element.get("text") or element.get("content_desc") or ""
        if label and label not in lines:
            lines.append(label)
        if len(lines) >= max_lines:
            break
    return {"ok": True, "platform": "android", "text": "\n".join(lines), "lines": lines}


def extract_articles(device: str, max_items: int = 5) -> dict[str, Any]:
    dev = get_device(device)
    if is_ios_ref(device) and hasattr(dev, "extract_articles"):
        return {"ok": True, "platform": "ios", "articles": dev.extract_articles(max_items=max_items)}

    visible = extract_visible_text(device, max_lines=200)
    articles = [{"title": line} for line in visible.get("lines", []) if len(line) > 18][:max_items]
    return {"ok": True, "platform": "android", "articles": articles}


def dumps(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2)
