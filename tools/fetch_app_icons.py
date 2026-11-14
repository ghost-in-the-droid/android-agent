#!/usr/bin/env python3
"""Fetch a real app icon for every hub skill and store it as ``icon.webp`` in the skill dir.

Usage:
    python3 tools/fetch_app_icons.py [skillhub/] [--force] [--only <author>/<slug> ...]

For each ``skillhub/<author>/<slug>/skill.yaml`` the package is
``fingerprint.app_package``. Sources, in order:

1. Google Play: ``https://play.google.com/store/apps/details?id=<pkg>&hl=en``, the
   ``og:image`` icon URL (else the first ``play-lh.googleusercontent.com`` URL of an
   ``alt="Icon image"`` img), requested at ``=s192``.
2. F-Droid: ``https://f-droid.org/repo/<pkg>/en-US/icon.png``.
3. F-Droid index-v2: ``packages.<pkg>.metadata.icon.<locale>.name`` from
   ``https://f-droid.org/repo/index-v2.json`` (downloaded once, cached).

The image is resized with Pillow to 96x96 (aspect kept, transparent padding) and
written as WebP, aiming for 8 KB or less; anything over 16 KB is rejected. Polite:
at most one request per second, every response cached under ``~/.cache/ghost-icons``
(``GHOST_ICON_CACHE`` overrides). Idempotent: a skill that already has
``icon.webp`` is skipped unless ``--force``.

Icons are the app owners' trademarks, shown nominatively to identify which app a
skill automates; they are removed on request.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

ICON_NAME = "icon.webp"
SIZE = 96
TARGET_BYTES = 8 * 1024
MAX_BYTES = 16 * 1024
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) ghost-skillhub-icons/1.0 (+https://github.com/ghost-in-the-droid)"
PLAY_URL = "https://play.google.com/store/apps/details?id={pkg}&hl=en"
FDROID_ICON = "https://f-droid.org/repo/{pkg}/en-US/icon.png"
FDROID_INDEX = "https://f-droid.org/repo/index-v2.json"
FDROID_REPO = "https://f-droid.org/repo"
_OG = re.compile(r'<meta property="og:image" content="(https://play-lh\.googleusercontent\.com/[^"=]+)[^"]*"')
_IMG = re.compile(r'<img[^>]*src="(https://play-lh\.googleusercontent\.com/[^"=]+)[^"]*"[^>]*alt="Icon image"')

HttpGet = Callable[[str], "tuple[int, bytes]"]


@dataclass
class IconResult:
    skill: str
    package: str
    source: str            # play | fdroid | fdroid-index | existing | none
    bytes: int = 0
    note: str = ""


class Fetcher:
    """Polite cached HTTP: one request per ``interval`` seconds, responses cached on disk."""

    def __init__(self, http_get: HttpGet | None = None, cache_dir: Path | None = None,
                 interval: float = 1.0, sleep=time.sleep, clock=time.monotonic):
        self.http_get = http_get or _urllib_get
        self.cache = Path(cache_dir or os.environ.get("GHOST_ICON_CACHE") or Path.home() / ".cache" / "ghost-icons")
        self.interval, self.sleep, self.clock = interval, sleep, clock
        self._last = None
        self.requests = 0

    def get(self, url: str) -> tuple[int, bytes]:
        key = hashlib.sha256(url.encode()).hexdigest()
        body, meta = self.cache / f"{key}.bin", self.cache / f"{key}.status"
        if meta.is_file():
            status = int(meta.read_text())
            return status, body.read_bytes() if body.is_file() else b""
        if self._last is not None:
            wait = self.interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()
        self.requests += 1
        status, data = self.http_get(url)
        self.cache.mkdir(parents=True, exist_ok=True)
        if status == 200 or status == 404:          # cache definitive answers only
            body.write_bytes(data)
            meta.write_text(str(status))
        return status, data


def _urllib_get(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed https hosts)
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, OSError):
        return 0, b""


def play_icon_url(html: str) -> str | None:
    m = _OG.search(html) or _IMG.search(html)
    return f"{m.group(1)}=s192" if m else None


def to_webp(raw: bytes) -> bytes:
    """96x96 WebP, aspect kept on a transparent canvas; smallest quality that fits TARGET_BYTES."""
    try:
        from PIL import Image
    except ImportError as e:  # pragma: no cover
        raise SystemExit("Pillow is required: pip install pillow") from e
    img = Image.open(io.BytesIO(raw))
    img.load()
    img = img.convert("RGBA")
    img.thumbnail((SIZE, SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2), img)
    best = None
    for quality in (90, 80, 70, 60, 50, 40):
        buf = io.BytesIO()
        canvas.save(buf, "WEBP", quality=quality, method=6)
        best = buf.getvalue()
        if len(best) <= TARGET_BYTES:
            break
    if best is None or len(best) > MAX_BYTES:
        raise ValueError(f"icon is {len(best or b'')} bytes after compression, over the {MAX_BYTES} byte limit")
    return best


def _fdroid_index_name(fetcher: Fetcher, pkg: str) -> str | None:
    status, data = fetcher.get(FDROID_INDEX)
    if status != 200 or not data:
        return None
    try:
        meta = json.loads(data)["packages"][pkg]["metadata"]
    except (ValueError, KeyError, TypeError):
        return None
    icons = meta.get("icon") or {}
    for loc in ("en-US", "en", *icons.keys()):
        name = (icons.get(loc) or {}).get("name")
        if name:
            return name
    return None


def fetch_icon(fetcher: Fetcher, pkg: str) -> tuple[str, bytes | None, str]:
    """(source, image bytes or None, note) for one package."""
    status, html = fetcher.get(PLAY_URL.format(pkg=pkg))
    if status == 200:
        url = play_icon_url(html.decode("utf-8", "replace"))
        if url:
            s2, img = fetcher.get(url)
            if s2 == 200 and img:
                return "play", img, ""
    status, img = fetcher.get(FDROID_ICON.format(pkg=pkg))
    if status == 200 and img:
        return "fdroid", img, ""
    name = _fdroid_index_name(fetcher, pkg)
    if name:
        status, img = fetcher.get(FDROID_REPO + (name if name.startswith("/") else "/" + name))
        if status == 200 and img:
            return "fdroid-index", img, ""
    return "none", None, "not on Google Play or F-Droid"


def skills(hub: Path) -> list[tuple[str, Path, str]]:
    out = []
    for f in sorted(hub.glob("*/*/skill.yaml")):
        if f.parent.parent.name in ("registry", "scoring"):
            continue
        raw = yaml.safe_load(f.read_text()) or {}
        pkg = str((raw.get("fingerprint") or {}).get("app_package") or "")
        out.append((f"{f.parent.parent.name}/{f.parent.name}", f.parent, pkg))
    return out


def run(hub: Path, fetcher: Fetcher, *, force: bool = False, only: set[str] | None = None) -> list[IconResult]:
    results, by_pkg = [], {}
    for key, d, pkg in skills(hub):
        if only and key not in only:
            continue
        target = d / ICON_NAME
        if target.is_file() and not force:
            results.append(IconResult(key, pkg, "existing", target.stat().st_size))
            continue
        if not pkg:
            results.append(IconResult(key, pkg, "none", 0, "no fingerprint.app_package"))
            continue
        if pkg not in by_pkg:
            source, raw, note = fetch_icon(fetcher, pkg)
            webp = None
            if raw:
                try:
                    webp = to_webp(raw)
                except (ValueError, OSError) as e:
                    source, note = "none", f"unusable image: {e}"
            by_pkg[pkg] = (source if webp else "none", webp, note)
        source, webp, note = by_pkg[pkg]
        if webp:
            target.write_bytes(webp)
        results.append(IconResult(key, pkg, source, len(webp or b""), note))
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("hub", nargs="?", default="skillhub", type=Path)
    p.add_argument("--force", action="store_true", help="Re-fetch even when icon.webp exists")
    p.add_argument("--only", nargs="*", default=None, help="Limit to <author>/<slug> refs")
    args = p.parse_args(argv)
    results = run(args.hub, Fetcher(), force=args.force, only=set(args.only) if args.only else None)
    w = max([len(r.package) for r in results] + [7])
    print(f"{'skill':<40} {'package':<{w}} {'source':<13} bytes")
    for r in results:
        print(f"{r.skill:<40} {r.package or '-':<{w}} {r.source:<13} {r.bytes}")
    missing = sorted({r.package or f'({r.skill})' for r in results if r.source == "none"})
    print(f"\n{sum(r.source != 'none' for r in results)} of {len(results)} skills have an icon.")
    if missing:
        print("No icon: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
