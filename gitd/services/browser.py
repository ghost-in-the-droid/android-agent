"""Platform-aware browser helpers."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

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


def _set_ios_bundle_override(dev, bundle_id: str | None) -> None:
    if not bundle_id:
        return
    if hasattr(dev, "set_target_app"):
        dev.set_target_app(bundle_id=bundle_id)
    else:
        dev.bundle_id = bundle_id


def open_url(device: str, url: str, bundle_id: str | None = None) -> dict[str, Any]:
    normalized_url = _normalize_url(url)
    if is_ios_ref(device):
        dev = get_device(device)
        _set_ios_bundle_override(dev, bundle_id)
        navigation = dev.open_url(normalized_url)
        current_url = ""
        current_url_error = ""
        try:
            current_url = dev.get_current_url() or ""
        except Exception as exc:
            current_url_error = str(exc)
        if not current_url and isinstance(navigation, dict):
            current_url = str(navigation.get("url") or "")
        result = {
            "ok": navigation.get("ok", True) if isinstance(navigation, dict) else True,
            "platform": "ios",
            "url": current_url or normalized_url,
            "navigation": navigation if isinstance(navigation, dict) else {},
        }
        if current_url_error:
            result["current_url_error"] = current_url_error
        return result

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
        try:
            current_url = dev.get_current_url() or ""
        except Exception as exc:
            return {"ok": False, "platform": "ios", "url": "", "error": str(exc)}
        if current_url:
            return {"ok": True, "platform": "ios", "url": current_url}
        return {
            "ok": False,
            "platform": "ios",
            "url": "",
            "error": "Current URL is not exposed by the active iOS browser context",
        }
    return {"ok": False, "platform": "android", "error": "Current URL is not implemented for Android yet"}


def wait_for_text(device: str, text: str, timeout: float = 12.0) -> dict[str, Any]:
    dev = get_device(device)
    if is_ios_ref(device) and hasattr(dev, "wait_for_text"):
        try:
            visible = dev.wait_for_text(text, timeout=timeout)
            return {"ok": True, "platform": "ios", "text": text, "found": True, "visible_text": visible}
        except Exception as exc:
            visible = ""
            try:
                visible = dev.extract_visible_text(max_lines=120)
            except Exception:
                pass
            return {
                "ok": False,
                "platform": "ios",
                "text": text,
                "found": False,
                "timeout": timeout,
                "visible_text": visible,
                "error": str(exc),
            }

    from gitd.services.device_context import find_on_screen

    timeout = max(0.0, float(timeout))
    interval = 0.5
    deadline = _retry_deadline(timeout)
    attempts = 0
    while True:
        attempts += 1
        found = find_on_screen(device, text)
        if found:
            return {
                "ok": True,
                "platform": "android",
                "text": text,
                "found": True,
                "match": found,
                "attempts": attempts,
                "timeout": timeout,
            }
        remaining = deadline - time.time()
        if remaining <= 0:
            return {
                "ok": False,
                "platform": "android",
                "text": text,
                "found": False,
                "match": None,
                "attempts": attempts,
                "timeout": timeout,
            }
        time.sleep(min(interval, remaining))


def extract_visible_text(device: str, max_lines: int = 200, include_controls: bool = False) -> dict[str, Any]:
    dev = get_device(device)
    if is_ios_ref(device) and hasattr(dev, "extract_visible_text"):
        text, source = _device_visible_text(dev, max_lines=max_lines, include_controls=include_controls)
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
        articles = _dedupe_article_candidates(dev.extract_articles(max_items=max_items * 2), max_items=max_items)
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


def _article_has_body(article: dict[str, Any]) -> bool:
    if not article.get("opened"):
        return False
    text = str(article.get("body_snippet") or "")
    return _article_text_has_body(text, source_headline=str(article.get("source_headline") or ""))


_NON_ARTICLE_BODY_LINES = {
    "advertisement",
    "back",
    "close",
    "home",
    "listen",
    "menu",
    "more",
    "next",
    "previous",
    "read more",
    "refresh",
    "search",
    "sections",
    "share",
    "sponsor message",
    "subscribe",
}


def _article_text_has_body(text: str, *, source_headline: str = "") -> bool:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    # Some iOS WebView/WDA contexts expose article pages as one paragraph rather
    # than separate title/body nodes. Count a substantial single paragraph as
    # body text, but keep title-only and toolbar-only extraction as partial.
    title_like: set[str] = set()
    if source_headline:
        title_like.add(re.sub(r"\s+", " ", source_headline).strip().lower())
    body_lines = [
        line
        for line in lines
        if line.lower() not in title_like and line.lower() not in _NON_ARTICLE_BODY_LINES
    ]
    if not body_lines:
        return False
    for line in body_lines:
        words = re.findall(r"[A-Za-z0-9]+", line)
        if len(line) >= 80 or len(words) >= 14:
            return True
        if len(line) >= 20 and len(words) >= 4:
            return True
    combined = " ".join(body_lines)
    return len(combined) >= 35 and len(re.findall(r"[A-Za-z0-9]+", combined)) >= 6


def _article_source(articles: list[dict[str, Any]]) -> str:
    sources = sorted(
        {str(article.get("provenance") or "").strip() for article in articles if article.get("provenance")}
    )
    if not sources:
        return ""
    return sources[0] if len(sources) == 1 else "mixed:" + ",".join(sources)


def _entry_source(entries: list[dict[str, Any]]) -> str:
    sources = sorted({str(entry.get("provenance") or "").strip() for entry in entries if entry.get("provenance")})
    if not sources:
        return "native_or_web"
    return sources[0] if len(sources) == 1 else "mixed:" + ",".join(sources)


def _device_visible_text(dev, *, max_lines: int, include_controls: bool = False) -> tuple[str, str]:
    if hasattr(dev, "visible_text_entries"):
        try:
            entries = dev.visible_text_entries(include_controls=include_controls, max_entries=max_lines)
            if entries:
                return "\n".join(str(entry.get("text") or "") for entry in entries[:max_lines]), _entry_source(entries)
        except Exception:
            pass
    text = dev.extract_visible_text(max_lines=max_lines)
    return text, "native_or_web"


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


def _article_title_key(article: dict[str, Any]) -> str:
    title = re.sub(
        r"\W+",
        "",
        str(article.get("title") or article.get("source_headline") or article.get("text") or "").lower(),
    )
    return f"text:{title}" if title else ""


def _article_candidate_keys(article: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    url = str(article.get("url") or "").strip()
    if url:
        try:
            parsed = urllib.parse.urlparse(url)
            keys.append(f"url:{parsed.netloc.lower()}{parsed.path.rstrip('/').lower()}")
        except Exception:
            keys.append(f"url:{url.lower()}")
    title_key = _article_title_key(article)
    if title_key:
        keys.append(title_key)
    return keys


def _article_candidate_quality(article: dict[str, Any]) -> int:
    score = 0
    if article.get("url"):
        score += 30
    if article.get("provenance") == "web_context":
        score += 20
    if article.get("center"):
        score += 8
    if article.get("bounds"):
        score += 5
    if str(article.get("class") or "").lower() in {"a", "h1", "h2", "h3"}:
        score += 5
    score += min(len(str(article.get("title") or "").split()), 10)
    return score


def _dedupe_article_candidates(articles: list[dict[str, Any]], *, max_items: int | None = None) -> list[dict[str, Any]]:
    ordered_keys: list[str] = []
    by_key: dict[str, dict[str, Any]] = {}
    quality: dict[str, int] = {}
    aliases: dict[str, str] = {}
    for index, article in enumerate(articles or []):
        keys = _article_candidate_keys(article) or [f"index:{index}"]
        key = next((aliases[item] for item in keys if item in aliases), keys[0])
        score = _article_candidate_quality(article)
        if key not in by_key:
            ordered_keys.append(key)
            by_key[key] = article
            quality[key] = score
        elif score > quality[key]:
            by_key[key] = article
            quality[key] = score
        for alias in keys:
            aliases[alias] = key
    deduped = [by_key[key] for key in ordered_keys]
    return deduped[:max_items] if max_items is not None else deduped


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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requested = int(min_items if min_items is not None else max_items)
    target_items = min(max(0, int(max_items)), max(0, requested))
    if target_items <= 0:
        return [], {
            "requested": max_items,
            "target": target_items,
            "returned": 0,
            "ready": True,
            "attempts": 0,
            "source": "",
        }
    deadline = _retry_deadline(timeout)
    best: list[dict[str, Any]] = []
    best_source = ""
    attempts = 0
    while True:
        attempts += 1
        try:
            articles = _dedupe_article_candidates(dev.extract_articles(max_items=max_items * 2), max_items=max_items)
            if len(articles or []) > len(best):
                best = articles or []
                best_source = _article_source(best) or "native_or_web"
            if len(articles or []) >= target_items:
                return articles, {
                    "requested": max_items,
                    "target": target_items,
                    "returned": len(articles or []),
                    "ready": True,
                    "attempts": attempts,
                    "source": _article_source(articles or []) or "native_or_web",
                }
        except Exception:
            pass
        if is_ios_ref(device):
            ocr_articles = _ocr_articles(device, max_items=max_items)
            if len(ocr_articles or []) > len(best):
                best = ocr_articles or []
                best_source = "ocr"
            if len(ocr_articles or []) >= target_items:
                return ocr_articles, {
                    "requested": max_items,
                    "target": target_items,
                    "returned": len(ocr_articles or []),
                    "ready": True,
                    "attempts": attempts,
                    "source": "ocr",
                }
        if time.time() >= deadline:
            return best, {
                "requested": max_items,
                "target": target_items,
                "returned": len(best),
                "ready": len(best) >= target_items,
                "attempts": attempts,
                "source": best_source,
            }
        time.sleep(interval)


def _extract_visible_text_with_retry(
    device: str,
    dev,
    *,
    max_lines: int,
    min_lines: int = 1,
    timeout: float,
    interval: float = 0.5,
    is_ready: Callable[[str], bool] | None = None,
) -> tuple[str, dict[str, Any]]:
    target_lines = max(1, int(min_lines))
    deadline = _retry_deadline(timeout)
    best = ""
    best_source = ""
    attempts = 0
    while True:
        attempts += 1
        try:
            text, source = _device_visible_text(dev, max_lines=max_lines)
            if _content_line_count(text) > _content_line_count(best):
                best = text
                best_source = source
            ready = _content_line_count(text) >= target_lines and (is_ready(text) if is_ready else True)
            if ready:
                return text, {
                    "requested_lines": max_lines,
                    "target_lines": target_lines,
                    "returned_lines": _content_line_count(text),
                    "ready": True,
                    "attempts": attempts,
                    "source": source,
                }
        except Exception:
            pass
        if is_ios_ref(device):
            ocr_text = _ocr_visible_text(device, max_lines=max_lines)
            if _content_line_count(ocr_text) > _content_line_count(best):
                best = ocr_text
                best_source = "ocr"
            ready = _content_line_count(ocr_text) >= target_lines and (is_ready(ocr_text) if is_ready else True)
            if ready:
                return ocr_text, {
                    "requested_lines": max_lines,
                    "target_lines": target_lines,
                    "returned_lines": _content_line_count(ocr_text),
                    "ready": True,
                    "attempts": attempts,
                    "source": "ocr",
                }
        if time.time() >= deadline:
            ready = _content_line_count(best) >= target_lines and (is_ready(best) if is_ready else True)
            return best, {
                "requested_lines": max_lines,
                "target_lines": target_lines,
                "returned_lines": _content_line_count(best),
                "ready": ready,
                "attempts": attempts,
                "source": best_source,
            }
        time.sleep(interval)


def _tap_article_candidate(dev, article: dict[str, Any], *, delay: float = 1.5) -> tuple[str, dict[str, Any]]:
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


def _open_article_candidate(dev, article: dict[str, Any], *, delay: float = 1.5) -> tuple[str, dict[str, Any]]:
    url = str(article.get("url") or "").strip()
    url_errors: list[dict[str, Any]] = []
    if url:
        try:
            navigation = dev.open_url(url, delay=delay)
            if not isinstance(navigation, dict) or navigation.get("ok", True):
                return "url", navigation if isinstance(navigation, dict) else {}
            url_errors.append({"method": "url", "navigation": navigation})
        except Exception as exc:
            url_errors.append({"method": "url", "error": str(exc)})

    try:
        method, navigation = _tap_article_candidate(dev, article, delay=delay)
        if url_errors:
            navigation = {**navigation, "fallback_from": "url", "fallback_errors": url_errors}
        return method, navigation
    except Exception:
        if url and url_errors:
            first = url_errors[0]
            if "navigation" in first:
                return "url", first["navigation"]
            raise RuntimeError(str(first.get("error") or "article URL navigation failed"))
        raise


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
    _set_ios_bundle_override(dev, bundle_id)

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
        "extraction": {
            "headlines": {},
            "front_page_text": {},
            "articles": [],
        },
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

        headlines, headline_evidence = _extract_articles_with_retry(
            device,
            dev,
            max_items=max_headlines,
            min_items=max_headlines,
            timeout=wait_s,
        )
        result["headlines"] = headlines[:max_headlines]
        result["extraction"]["headlines"] = headline_evidence
        front_page_text, front_page_evidence = _extract_visible_text_with_retry(
            device,
            dev,
            max_lines=120,
            min_lines=1,
            timeout=wait_s,
        )
        result["front_page_text"] = _snippet(front_page_text, max_chars=2400)
        result["extraction"]["front_page_text"] = front_page_evidence

        for index, headline in enumerate(headlines[:max_articles], start=1):
            article_result: dict[str, Any] = {
                "index": index,
                "source_headline": headline.get("title", ""),
                "headline_provenance": headline.get("provenance", ""),
                "opened": False,
            }
            article_evidence: dict[str, Any] = {
                "index": index,
                "headline_provenance": headline.get("provenance", ""),
                "headline_has_url": bool(headline.get("url")),
            }
            try:
                open_method, navigation = _open_article_candidate(dev, headline, delay=max(1.0, wait_s))
                article_result["open_method"] = open_method
                article_evidence["open_method"] = open_method
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
                visible_text, text_evidence = _extract_visible_text_with_retry(
                    device,
                    dev,
                    max_lines=160,
                    min_lines=1,
                    timeout=wait_s,
                    is_ready=lambda text, source_headline=headline.get("title", ""): _article_text_has_body(
                        text,
                        source_headline=str(source_headline or ""),
                    ),
                )
                text_evidence["body_ready"] = _article_text_has_body(
                    visible_text,
                    source_headline=str(headline.get("title", "") or ""),
                )
                article_evidence["text"] = text_evidence
                lines = [line.strip() for line in visible_text.splitlines() if line.strip()]
                article_result["page_title"] = lines[0] if lines else ""
                article_result["body_snippet"] = _snippet(visible_text, max_chars=2400)
                article_result["opened"] = True
            except Exception as exc:
                article_result["error"] = str(exc)
                article_evidence["error"] = str(exc)
                result["errors"].append({"article": headline.get("title", ""), "error": str(exc)})
            finally:
                result["articles"].append(article_result)
                result["extraction"]["articles"].append(article_evidence)
                try:
                    dev.browser_back(delay=1.0)
                except Exception as exc:
                    result["errors"].append({"article": headline.get("title", ""), "back_error": str(exc)})

        requested_articles = min(max_articles, len(result["headlines"]))
        opened_articles = [article for article in result["articles"] if article.get("opened")]
        articles_with_body = [article for article in opened_articles if _article_has_body(article)]
        completion = {
            "requested_headlines": max_headlines,
            "headlines_found": len(result["headlines"]),
            "headline_target_met": len(result["headlines"]) >= max_headlines,
            "requested_articles": requested_articles,
            "articles_opened": len(opened_articles),
            "articles_with_body": len(articles_with_body),
            "article_target_met": requested_articles == 0 or len(articles_with_body) >= requested_articles,
        }
        completion["workflow_complete"] = (
            bool(result["headlines"])
            and bool(completion["headline_target_met"])
            and bool(completion["article_target_met"])
        )
        result["completion"] = completion
        result["ok"] = bool(completion["workflow_complete"])
        if not result["ok"]:
            result["errors"].append(
                {
                    "stage": "success_criteria",
                    "error": "News workflow did not extract the requested article body text",
                    "completion": completion,
                }
            )
        return result
    except Exception as exc:
        result["error"] = str(exc)
        result["errors"].append({"stage": "workflow", "error": str(exc)})
        return result


def dumps(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2)
