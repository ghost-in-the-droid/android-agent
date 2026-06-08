"""Platform-aware browser helpers."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path
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
        navigation = dev.open_url(normalized_url)
        current_url = dev.get_current_url() or normalized_url
        return {
            "ok": navigation.get("ok", True) if isinstance(navigation, dict) else True,
            "platform": "ios",
            "url": current_url,
            "navigation": navigation if isinstance(navigation, dict) else {},
        }

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
        source = "native_or_web"
        if not text.strip() and not include_controls:
            text = _ocr_visible_text(device, max_lines=max_lines)
            source = "ocr" if text.strip() else source
        return {"ok": True, "platform": "ios", "text": text, "lines": text.splitlines(), "source": source}

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
        articles = dev.extract_articles(max_items=max_items)
        source = "native_or_web"
        if not articles:
            articles = _ocr_articles(device, max_items=max_items)
            source = "ocr" if articles else source
        return {"ok": True, "platform": "ios", "articles": articles, "source": source}

    visible = extract_visible_text(device, max_lines=200)
    articles = [{"title": line} for line in visible.get("lines", []) if len(line) > 18][:max_items]
    return {"ok": True, "platform": "android", "articles": articles}


def _snippet(text: str, max_chars: int = 1800) -> str:
    lines = []
    seen = set()
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if sum(len(item) for item in lines) > max_chars:
            break
    return "\n".join(lines)[:max_chars]


def _content_line_count(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip()])


def _looks_like_article_title(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) < 18:
        return False
    lower = cleaned.lower()
    if lower.startswith(("http://", "https://", "www.")):
        return False
    if lower in {"home", "menu", "sections", "search", "sponsor message", "advertisement"}:
        return False
    words = re.findall(r"[A-Za-z0-9]+", cleaned)
    return len(words) >= 4


def _ocr_entries(device: str, *, max_items: int = 200) -> list[dict[str, Any]]:
    try:
        from gitd.services.device_context import ocr_screen

        raw_entries = ocr_screen(device)
    except Exception:
        return []

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_entries:
        text = re.sub(r"\s+", " ", str(raw.get("text") or "")).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        x = int(raw.get("x") or 0)
        y = int(raw.get("y") or 0)
        w = int(raw.get("w") or 0)
        h = int(raw.get("h") or 0)
        entries.append(
            {
                "text": text,
                "bounds": {"x1": x, "y1": y, "x2": x + w, "y2": y + h},
                "center": {"x": x + w // 2, "y": y + h // 2},
                "class": "ocr",
                "resource_id": "",
                "content_desc": "",
                "url": "",
                "provenance": "ocr",
                "confidence": raw.get("conf"),
            }
        )
        if len(entries) >= max_items:
            break
    return entries


def _ocr_visible_text(device: str, *, max_lines: int = 200) -> str:
    return "\n".join(entry["text"] for entry in _ocr_entries(device, max_items=max_lines))


def _ocr_articles(device: str, *, max_items: int = 5) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in _ocr_entries(device, max_items=200):
        title = entry["text"].strip()
        if not _looks_like_article_title(title):
            continue
        key = re.sub(r"\W+", "", title.lower())
        if key in seen:
            continue
        seen.add(key)
        articles.append(
            {
                "title": title,
                "url": "",
                "bounds": entry["bounds"],
                "center": entry["center"],
                "class": "ocr",
                "provenance": "ocr",
                "confidence": entry.get("confidence"),
            }
        )
        if len(articles) >= max_items:
            break
    return articles


def _save_device_screenshot(dev, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dev.take_screenshot())
    return str(path)


def _retry_deadline(timeout: float) -> float:
    return time.time() + max(0.0, float(timeout))


def _extract_articles_with_retry(
    device: str,
    dev,
    *,
    max_items: int,
    min_items: int | None = None,
    timeout: float,
    interval: float = 0.5,
) -> list[dict[str, Any]]:
    requested = int(min_items if min_items is not None else max_items)
    target_items = min(max(0, int(max_items)), max(0, requested))
    if target_items <= 0:
        return []
    deadline = _retry_deadline(timeout)
    best: list[dict[str, Any]] = []
    while True:
        try:
            articles = dev.extract_articles(max_items=max_items)
            if len(articles or []) > len(best):
                best = articles or []
            if len(articles or []) >= target_items:
                return articles
        except Exception:
            pass
        if is_ios_ref(device):
            ocr_articles = _ocr_articles(device, max_items=max_items)
            if len(ocr_articles or []) > len(best):
                best = ocr_articles or []
            if len(ocr_articles or []) >= target_items:
                return ocr_articles
        if time.time() >= deadline:
            return best
        time.sleep(interval)


def _extract_visible_text_with_retry(
    device: str,
    dev,
    *,
    max_lines: int,
    min_lines: int = 1,
    timeout: float,
    interval: float = 0.5,
) -> str:
    target_lines = max(1, int(min_lines))
    deadline = _retry_deadline(timeout)
    best = ""
    while True:
        try:
            text = dev.extract_visible_text(max_lines=max_lines)
            if _content_line_count(text) > _content_line_count(best):
                best = text
            if _content_line_count(text) >= target_lines:
                return text
        except Exception:
            pass
        if is_ios_ref(device):
            ocr_text = _ocr_visible_text(device, max_lines=max_lines)
            if _content_line_count(ocr_text) > _content_line_count(best):
                best = ocr_text
            if _content_line_count(ocr_text) >= target_lines:
                return ocr_text
        if time.time() >= deadline:
            return best
        time.sleep(interval)


def _open_article_candidate(dev, article: dict[str, Any], *, delay: float = 1.5) -> tuple[str, dict[str, Any]]:
    url = str(article.get("url") or "").strip()
    if url:
        navigation = dev.open_url(url, delay=delay)
        return "url", navigation if isinstance(navigation, dict) else {}

    center = article.get("center") if isinstance(article.get("center"), dict) else {}
    if center.get("x") is not None and center.get("y") is not None:
        dev.tap(int(center["x"]), int(center["y"]), delay=delay)
        return "center", {}

    bounds = article.get("bounds") if isinstance(article.get("bounds"), dict) else {}
    if {"x1", "y1", "x2", "y2"} <= set(bounds):
        x = (int(bounds["x1"]) + int(bounds["x2"])) // 2
        y = (int(bounds["y1"]) + int(bounds["y2"])) // 2
        dev.tap(x, y, delay=delay)
        return "bounds", {}

    raise RuntimeError("article candidate has no URL or tappable geometry")


def read_news(
    device: str,
    url: str = "https://text.npr.org/",
    *,
    max_headlines: int = 5,
    max_articles: int = 3,
    bundle_id: str | None = None,
    wait_s: float = 2.0,
    save_screenshots: bool = False,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Open a news page and return headlines plus article snippets.

    This is currently an iOS-first workflow because WDA/WebView extraction can
    expose article URLs and text. Android agents can still compose the primitive
    browser tools directly.
    """
    if not is_ios_ref(device):
        return {
            "ok": False,
            "platform": "android",
            "error": "read_news is currently implemented for iOS browser/WebDriver sessions",
        }

    dev = get_device(device)
    if bundle_id:
        dev.bundle_id = bundle_id

    max_headlines = max(1, int(max_headlines))
    max_articles = max(0, int(max_articles))
    wait_s = max(0.0, float(wait_s))
    out_path = Path(out_dir or "data/ios_chrome_news_smoke")
    normalized_url = _normalize_url(url)
    result: dict[str, Any] = {
        "ok": False,
        "platform": "ios",
        "device": device,
        "bundle_id": getattr(dev, "bundle_id", bundle_id or ""),
        "url": normalized_url,
        "headlines": [],
        "articles": [],
        "screenshots": {},
        "errors": [],
    }

    try:
        launch_bundle = getattr(dev, "bundle_id", "") or bundle_id or ""
        if launch_bundle:
            try:
                dev.launch_app(launch_bundle)
            except Exception as exc:
                result["errors"].append({"stage": "launch", "error": str(exc)})

        navigation = dev.open_url(normalized_url, delay=wait_s)
        if isinstance(navigation, dict):
            result["navigation"] = navigation
        elif wait_s:
            time.sleep(wait_s)

        if save_screenshots:
            result["screenshots"]["front_page"] = _save_device_screenshot(dev, out_path / "front_page.png")

        try:
            result["current_url"] = dev.get_current_url()
        except Exception as exc:
            result["errors"].append({"stage": "current_url", "error": str(exc)})

        headlines = _extract_articles_with_retry(
            device,
            dev,
            max_items=max_headlines,
            min_items=max_headlines,
            timeout=wait_s,
        )
        result["headlines"] = headlines[:max_headlines]
        front_page_text = _extract_visible_text_with_retry(device, dev, max_lines=120, min_lines=1, timeout=wait_s)
        result["front_page_text"] = _snippet(front_page_text, max_chars=2400)

        for index, headline in enumerate(headlines[:max_articles], start=1):
            article_result: dict[str, Any] = {
                "index": index,
                "source_headline": headline.get("title", ""),
                "opened": False,
            }
            try:
                open_method, navigation = _open_article_candidate(dev, headline, delay=max(1.0, wait_s))
                article_result["open_method"] = open_method
                if navigation:
                    article_result["navigation"] = navigation
                elif wait_s:
                    time.sleep(wait_s)
                if save_screenshots:
                    article_result["screenshot"] = _save_device_screenshot(dev, out_path / f"article_{index}.png")
                try:
                    article_result["current_url"] = dev.get_current_url()
                except Exception as exc:
                    article_result["current_url_error"] = str(exc)
                visible_text = _extract_visible_text_with_retry(
                    device,
                    dev,
                    max_lines=160,
                    min_lines=2,
                    timeout=wait_s,
                )
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
                except Exception as exc:
                    result["errors"].append({"article": headline.get("title", ""), "back_error": str(exc)})

        result["ok"] = bool(result["headlines"])
        return result
    except Exception as exc:
        result["error"] = str(exc)
        result["errors"].append({"stage": "workflow", "error": str(exc)})
        return result


def dumps(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2)
