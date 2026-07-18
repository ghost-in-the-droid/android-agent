"""Tests for the direct-WDA transport (IOS_WDA_DIRECT=1).

When enabled, IOSDevice talks straight to WebDriverAgent's HTTP API — resolving
the tunnel address from the RemoteXPC registry — and never touches Appium (whose
CoreDevice device-lookup wedges as "Could not find the expected device"). These
tests mock the WDA HTTP surface and assert every request lands on a WDA-native
endpoint, and that the Appium path is left untouched when the flag is off.
"""

import pytest

from gitd.bots.common import ios as ios_mod
from gitd.bots.common.ios import (
    IOSDevice,
    _looks_like_ios_identifier,
    normalize_wda_xml,
    visible_text_entries_from_xml,
)


class FakeResponse:
    def __init__(self, data, status_code=200, text=""):
        self._data = data
        self.status_code = status_code
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._data


class FakeWDA:
    """Records requests and answers WDA-native endpoints; unknown paths 404."""

    def __init__(self, address="fdaa::1"):
        self.address = address
        self.calls = []  # (method, url, payload)

    # `requests.get` — used only by the registry resolver
    def get(self, url, timeout=None, **kwargs):
        self.calls.append(("GET", url, None))
        if "/remotexpc/tunnels/" in url:
            return FakeResponse({"address": self.address})
        return self._route("GET", url, None)

    # `requests.request` — session create, settings, all session ops
    def request(self, method, url, json=None, timeout=None, **kwargs):
        self.calls.append((method.upper(), url, json))
        return self._route(method.upper(), url, json)

    def _route(self, method, url, payload):
        if method == "POST" and url.endswith("/session"):
            return FakeResponse({"value": {"sessionId": "sess-direct-1"}, "sessionId": "sess-direct-1"})
        if url.endswith("/appium/settings"):
            return FakeResponse({"value": {}})
        if url.endswith("/wda/apps/launch"):
            return FakeResponse({"value": None})
        if url.endswith("/wda/apps/terminate"):
            return FakeResponse({"value": None})
        if url.endswith("/wda/apps/state"):
            return FakeResponse({"value": 4})
        if url.endswith("/wda/pressButton"):
            return FakeResponse({"value": {}})
        if url.endswith("/wda/activeAppInfo"):
            return FakeResponse({"value": {"bundleId": "com.foo.bar", "name": "Foo"}})
        if url.endswith("/window/size"):
            return FakeResponse({"value": {"width": 390, "height": 844}})
        return FakeResponse({"value": {"error": "unknown command"}}, status_code=404, text=url)

    def paths(self):
        """URL path suffixes (drops the scheme://host base) for easy asserts."""
        out = []
        for _method, url, _payload in self.calls:
            # keep everything from the first '/session' or '/remotexpc' onward
            for marker in ("/session", "/remotexpc"):
                if marker in url:
                    out.append(url[url.index(marker):])
                    break
        return out


@pytest.fixture()
def wda(monkeypatch):
    fake = FakeWDA()
    monkeypatch.setattr(ios_mod.requests, "get", fake.get)
    monkeypatch.setattr(ios_mod.requests, "request", fake.request)
    monkeypatch.setattr(ios_mod.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setenv("IOS_WDA_DIRECT", "1")
    monkeypatch.setenv("IOS_REMOTEXPC_REGISTRY", "http://127.0.0.1:42314")
    # Class-level session cache leaks across tests otherwise.
    IOSDevice._sessions.clear()
    return fake


def _device():
    return IOSDevice("ios:abc123", appium_url="http://appium.local:4723")


def test_registry_resolves_bracketed_ipv6_base(wda):
    dev = _device()
    assert dev._wda_base() == "http://[fdaa::1]:8100"
    # Resolution is cached per instance (address must not be refetched mid-session).
    dev._wda_base()
    registry_hits = [u for _m, u, _p in wda.calls if "/remotexpc/tunnels/" in u]
    assert len(registry_hits) == 1
    assert registry_hits[0].endswith("/remotexpc/tunnels/abc123")


def test_ipv4_base_is_not_bracketed(monkeypatch, wda):
    wda.address = "192.168.1.9"
    dev = _device()
    assert dev._wda_base() == "http://192.168.1.9:8100"


def test_fixed_wda_url_bypasses_registry(wda):
    dev = _device()
    dev.wda_url = "http://[fe80::2]:8100/"  # normally from IOS_WDA_URL
    assert dev._wda_base() == "http://[fe80::2]:8100"
    assert not [u for _m, u, _p in wda.calls if "/remotexpc/tunnels/" in u]


def test_session_uses_minimal_caps_and_applies_settings(wda):
    dev = _device()
    sid = dev._ensure_session()
    assert sid == "sess-direct-1"

    # session POST carries NO appium:udid (that is what triggers the CoreDevice wedge)
    create = next(p for m, u, p in wda.calls if m == "POST" and u.endswith("/session"))
    always = create["capabilities"]["alwaysMatch"]
    assert always == {"platformName": "iOS"}
    assert not any(k.startswith("appium:") for k in always)

    # snappy settings applied right after create
    settings = next(p for m, u, p in wda.calls if u.endswith("/appium/settings"))
    assert settings["settings"]["animationCoolOffTimeout"] == 0
    assert settings["settings"]["waitForIdleTimeout"] == 0

    # every request went to the WDA base, never to Appium
    assert all("appium.local:4723" not in u for _m, u, _p in wda.calls)
    assert any("[fdaa::1]:8100" in u for _m, u, _p in wda.calls)


def test_launch_app_maps_to_wda_endpoint(wda):
    dev = _device()
    dev.launch_app("com.foo.bar")
    launch = next((m, u, p) for m, u, p in wda.calls if u.endswith("/wda/apps/launch"))
    assert launch[0] == "POST"
    assert launch[2] == {"bundleId": "com.foo.bar"}
    # /session/<sid>/wda/apps/launch, not /execute/sync
    assert "/execute/sync" not in " ".join(wda.paths())


def test_app_state_maps_to_wda_state(wda):
    dev = _device()
    assert dev.app_state("com.foo.bar") == 4
    state = next((m, u, p) for m, u, p in wda.calls if u.endswith("/wda/apps/state"))
    assert state[0] == "POST"
    assert state[2] == {"bundleId": "com.foo.bar"}


def test_press_home_maps_to_pressbutton(wda):
    dev = _device()
    dev.press_key("HOME")
    press = next((m, u, p) for m, u, p in wda.calls if u.endswith("/wda/pressButton"))
    assert press[0] == "POST"
    assert press[2] == {"name": "home"}


def test_terminate_app_maps_to_wda_terminate(wda):
    dev = _device()
    dev.terminate_app("com.foo.bar")
    term = next((m, u, p) for m, u, p in wda.calls if u.endswith("/wda/apps/terminate"))
    assert term[0] == "POST"
    assert term[2] == {"bundleId": "com.foo.bar"}


def test_unmapped_mobile_command_raises_clear_error(wda):
    dev = _device()
    with pytest.raises(ios_mod.IOSBackendError, match="no WDA-native equivalent"):
        dev._execute_mobile("mobile: siriCommand", {"text": "hi"})


def test_mjpeg_url_uses_wda_host(wda):
    dev = _device()
    assert dev.mjpeg_url == "http://[fdaa::1]:9100"


def test_contexts_native_only_in_direct_mode(wda):
    # WDA has no /contexts endpoint; direct mode must report native-only without
    # ever issuing the Appium request (which 404s "Unhandled endpoint").
    dev = _device()
    assert dev.get_contexts() == ["NATIVE_APP"]
    assert dev.get_web_contexts() == []
    assert not [u for _m, u, _p in wda.calls if u.endswith("/contexts")]


def test_set_context_is_noop_in_direct_mode(wda):
    dev = _device()
    dev._set_context("NATIVE_APP")  # must not raise or hit /context
    assert not [u for _m, u, _p in wda.calls if u.endswith("/context")]


def test_web_text_snapshot_empty_in_direct_mode(wda):
    # No web contexts → snapshot is empty → extractors fall back to native /source.
    dev = _device()
    assert dev.web_text_snapshot() == {}
    assert dev.web_text_entries() == []
    # never touched the Appium context/execute endpoints
    assert not [u for _m, u, _p in wda.calls if u.endswith(("/contexts", "/context", "/execute/sync"))]


@pytest.mark.parametrize(
    "identifier",
    [
        "BaseCell<FeedStackSliceViewModel>",
        "_TtGC8SliceKit20BaseListViewModel",
        "reddit_feed__content_view_home_loaded",
        "Home_Impl.HomeScreenView",
        "HomeScreenView",
    ],
)
def test_identifier_strings_are_detected(identifier):
    assert _looks_like_ios_identifier(identifier) is True


@pytest.mark.parametrize(
    "human",
    [
        "Best moments from the game last night",
        "Settings",
        "Reddit",
        "www.reddit.com",
        "12 comments",
        "",
        "U.S. Open results",
    ],
)
def test_human_text_is_not_treated_as_identifier(human):
    assert _looks_like_ios_identifier(human) is False


def test_native_extraction_prefers_labels_over_identifiers():
    # A Reddit-style tree: container views carry accessibility IDENTIFIERS in
    # `name` (no label); the real post title is a leaf StaticText with `label`.
    raw = """<?xml version="1.0" encoding="UTF-8"?>
    <AppiumAUT>
      <XCUIElementTypeApplication type="XCUIElementTypeApplication" name="Reddit" x="0" y="0" width="390" height="844" visible="true">
        <XCUIElementTypeOther type="XCUIElementTypeOther" name="reddit_feed__content_view_home_loaded" x="0" y="0" width="390" height="800" visible="true">
          <XCUIElementTypeCell type="XCUIElementTypeCell" name="BaseCell&lt;FeedStackSliceViewModel&gt;" x="0" y="100" width="390" height="200" visible="true">
            <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" label="Best moments from the game last night" x="10" y="120" width="360" height="40" visible="true"/>
          </XCUIElementTypeCell>
        </XCUIElementTypeOther>
      </XCUIElementTypeApplication>
    </AppiumAUT>
    """
    xml = normalize_wda_xml(raw)
    texts = [e["text"] for e in visible_text_entries_from_xml(xml, screen_size=(390, 844))]
    assert "Best moments from the game last night" in texts
    # none of the developer identifiers leak into extracted page text
    assert not any("BaseCell" in t or "reddit_feed__" in t or "HomeScreenView" in t for t in texts)


def test_appium_path_untouched_when_flag_off(monkeypatch):
    monkeypatch.delenv("IOS_WDA_DIRECT", raising=False)
    fake = FakeWDA()
    monkeypatch.setattr(ios_mod.requests, "request", fake.request)
    monkeypatch.setattr(ios_mod.time, "sleep", lambda *_a, **_k: None)
    IOSDevice._sessions.clear()

    dev = IOSDevice("ios:abc123", appium_url="http://appium.local:4723")
    assert dev._direct is False
    assert dev._url("/session") == "http://appium.local:4723/session"
    # session creation still carries appium:udid (the Appium contract)
    dev._ensure_session()
    create = next(p for m, u, p in fake.calls if m == "POST" and u.endswith("/session"))
    assert create["capabilities"]["alwaysMatch"]["appium:udid"] == "abc123"
    # no registry lookup happens on the Appium path
    assert not [u for _m, u, _p in fake.calls if "/remotexpc/tunnels/" in u]
