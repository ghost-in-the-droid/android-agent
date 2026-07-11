import json

from fastapi.testclient import TestClient

from gitd.app import app


class FakeTreeDevice:
    def dump_xml(self):
        return """
        <hierarchy>
          <node class="XCUIElementTypeApplication" bounds="[0,0][393,852]">
            <node class="XCUIElementTypeTextField" text="Search" clickable="true" bounds="[10,20][300,64]" />
          </node>
        </hierarchy>
        """


def test_phone_context_routes_include_device_and_platform(monkeypatch):
    from gitd.services import device_context

    monkeypatch.setattr(
        device_context,
        "screenshot",
        lambda device: {"device": device, "platform": "ios", "image": "image", "width": 393, "height": 852},
    )
    monkeypatch.setattr(device_context, "get_device", lambda device: FakeTreeDevice())
    monkeypatch.setattr(device_context, "ocr_screen", lambda device: [{"text": "Search", "x": 10, "y": 20}])
    client = TestClient(app)

    screenshot = client.get("/api/phone/screenshot/ios:abc123")
    xml = client.get("/api/phone/xml/ios:abc123")
    tree = client.get("/api/phone/screen-tree/ios:abc123")
    ocr = client.get("/api/phone/ocr/ios:abc123")

    for response in (screenshot, xml, tree, ocr):
        assert response.status_code == 200
        body = response.json()
        assert body["device"] == "ios:abc123"
        assert body["platform"] == "ios"

    assert screenshot.json()["width"] == 393
    assert "Search" in xml.json()["xml"]
    assert "Search" in tree.json()["tree"]
    assert ocr.json()["texts"][0]["text"] == "Search"


def test_device_context_classify_and_fingerprint_include_platform(monkeypatch):
    from gitd.services import device_context

    monkeypatch.setattr(
        device_context,
        "get_phone_state",
        lambda device: {
            "packageName": "com.google.chrome.ios",
            "activityName": "com.google.chrome.ios",
            "currentApp": "Chrome",
            "keyboardVisible": True,
        },
    )
    monkeypatch.setattr(device_context, "get_device", lambda device: FakeTreeDevice())
    monkeypatch.setattr(
        device_context,
        "get_interactive_elements",
        lambda device: [{"class": "TextField", "resource_id": "Search"}],
    )

    classified = device_context.classify_screen("ios:abc123")
    fingerprint = device_context.fingerprint_screen("ios:abc123")
    validated = device_context.validate_fingerprint("ios:abc123", {"package": "com.google.chrome.ios"})

    assert classified["device"] == "ios:abc123"
    assert classified["platform"] == "ios"
    assert classified["screen_type"] == "search"
    assert fingerprint["device"] == "ios:abc123"
    assert fingerprint["platform"] == "ios"
    assert validated["device"] == "ios:abc123"
    assert validated["platform"] == "ios"
    assert validated["valid"] is True


def test_agent_screenshot_tools_preserve_platform_metadata(monkeypatch):
    from gitd.services.agent_tools import execute_tool

    monkeypatch.setattr(
        "gitd.services.agent_tools.ctx.screenshot",
        lambda device: {
            "device": device,
            "platform": "ios",
            "image": "a" * 200,
            "width": 393,
            "height": 852,
        },
    )

    payload = json.loads(execute_tool("screenshot", {"device": "ios:abc123"}))

    assert payload["device"] == "ios:abc123"
    assert payload["platform"] == "ios"
    assert payload["width"] == 393
    assert payload["image"].endswith("...(truncated)")
