"""tools/fetch_app_icons.py with a fake HTTP layer: no network, no real sleeping."""
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_test_fetch_app_icons", REPO / "tools" / "fetch_app_icons.py")
icons = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = icons            # @dataclass needs the module registered
_spec.loader.exec_module(icons)


def png(w=512, h=512, color=(200, 30, 30, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


PLAY_HTML = ('<html><meta property="og:image" content="https://play-lh.googleusercontent.com/AbC_dEf-123=s0-br30">'
             '<img src="https://play-lh.googleusercontent.com/OTHER=w240-h480" alt="Icon image"></html>')


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url):
        self.calls.append(url)
        return self.routes.get(url, (404, b""))


class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.t += s


def fetcher(tmp_path, routes, clock=None):
    clock = clock or Clock()
    http = FakeHttp(routes)
    return icons.Fetcher(http, cache_dir=tmp_path / "cache", interval=1.0, sleep=clock.sleep, clock=clock.now), http, clock


def make_hub(tmp_path, pkgs):
    hub = tmp_path / "skillhub"
    for slug, pkg in pkgs.items():
        d = hub / "ghost" / slug
        d.mkdir(parents=True)
        fp = {"os": "android", "app_package": pkg} if pkg is not None else {"os": "android"}
        (d / "skill.yaml").write_text(json.dumps({"name": slug, "fingerprint": fp}))
    (hub / "scoring").mkdir()
    return hub


def test_play_icon_url_parsing():
    assert icons.play_icon_url(PLAY_HTML) == "https://play-lh.googleusercontent.com/AbC_dEf-123=s192"
    img_only = '<img src="https://play-lh.googleusercontent.com/XYZ=w240-h480" srcset="x" class="T75of" alt="Icon image">'
    assert icons.play_icon_url(img_only) == "https://play-lh.googleusercontent.com/XYZ=s192"
    assert icons.play_icon_url("<html>no icon</html>") is None


def test_to_webp_is_96px_and_small():
    out = icons.to_webp(png(1024, 512))                 # non-square: kept aspect on a transparent canvas
    img = Image.open(io.BytesIO(out))
    assert img.format == "WEBP" and img.size == (96, 96)
    assert len(out) <= icons.TARGET_BYTES
    assert img.convert("RGBA").getpixel((48, 2))[3] == 0  # padding is transparent


def test_sources_in_order_and_none(tmp_path):
    pk = {"play.app": "play.app", "fd.app": "fd.app", "idx.app": "idx.app", "aosp": "com.android.settings"}
    routes = {
        icons.PLAY_URL.format(pkg="play.app"): (200, PLAY_HTML.encode()),
        "https://play-lh.googleusercontent.com/AbC_dEf-123=s192": (200, png()),
        icons.FDROID_ICON.format(pkg="fd.app"): (200, png(color=(0, 0, 255, 255))),
        icons.FDROID_INDEX: (200, json.dumps({"packages": {"idx.app": {"metadata": {
            "icon": {"en-US": {"name": "/idx.app/en-US/icon_abc.png"}}}}}}).encode()),
        "https://f-droid.org/repo/idx.app/en-US/icon_abc.png": (200, png(color=(0, 255, 0, 255))),
    }
    f, http, clock = fetcher(tmp_path, routes)
    hub = make_hub(tmp_path, {**pk, "nopkg": None})
    results = {r.skill: r for r in icons.run(hub, f)}
    assert results["ghost/play.app"].source == "play"
    assert results["ghost/fd.app"].source == "fdroid"
    assert results["ghost/idx.app"].source == "fdroid-index"
    assert results["ghost/aosp"].source == "none" and results["ghost/aosp"].note
    assert results["ghost/nopkg"].source == "none" and not (hub / "ghost" / "nopkg" / "icon.webp").exists()
    for slug in ("play.app", "fd.app", "idx.app"):
        data = (hub / "ghost" / slug / "icon.webp").read_bytes()
        assert results[f"ghost/{slug}"].bytes == len(data) <= icons.MAX_BYTES
    assert not (hub / "ghost" / "aosp" / "icon.webp").exists()
    assert "ghost/scoring" not in results
    # polite: never two requests within the interval
    assert clock.slept and all(s <= 1.0 for s in clock.slept)
    assert http.calls.count(icons.FDROID_INDEX) == 1           # index fetched once, then cached


def test_idempotent_cached_and_force(tmp_path):
    routes = {icons.PLAY_URL.format(pkg="a.b"): (200, PLAY_HTML.encode()),
              "https://play-lh.googleusercontent.com/AbC_dEf-123=s192": (200, png())}
    hub = make_hub(tmp_path, {"one": "a.b", "two": "a.b"})
    f, http, _ = fetcher(tmp_path, routes)
    first = icons.run(hub, f)
    assert [r.source for r in first] == ["play", "play"] and len(http.calls) == 2   # same package fetched once

    again = icons.run(hub, f)
    assert {r.source for r in again} == {"existing"} and len(http.calls) == 2       # skipped, no requests

    f2, http2, _ = fetcher(tmp_path, routes)                                         # fresh process, same disk cache
    forced = icons.run(hub, f2, force=True)
    assert {r.source for r in forced} == {"play"} and http2.calls == []             # served from cache


def test_transient_errors_are_not_cached(tmp_path):
    f, http, _ = fetcher(tmp_path, {icons.PLAY_URL.format(pkg="x.y"): (503, b"")})
    assert f.get(icons.PLAY_URL.format(pkg="x.y"))[0] == 503
    f.get(icons.PLAY_URL.format(pkg="x.y"))
    assert len(http.calls) == 2


def test_oversized_icon_is_rejected(monkeypatch):
    monkeypatch.setattr(icons, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="limit"):
        icons.to_webp(png())
