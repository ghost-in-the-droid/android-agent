def test_tools_hub_exposes_platform_support(client):
    response = client.get("/api/tools")
    assert response.status_code == 200

    categories = response.json()
    web = next(category for category in categories if category["category"] == "Web")
    screen = next(category for category in categories if category["category"] == "Screen Reading")
    app_management = next(category for category in categories if category["category"] == "App Management")
    clipboard = next(category for category in categories if category["category"] == "Clipboard & Notifications")
    open_url = next(tool for tool in web["tools"] if tool["name"] == "open_url")
    current_url = next(tool for tool in web["tools"] if tool["name"] == "get_current_url")
    read_news = next(tool for tool in web["tools"] if tool["name"] == "read_news")
    device_health = next(tool for tool in screen["tools"] if tool["name"] == "device_health")
    app_state = next(tool for tool in app_management["tools"] if tool["name"] == "app_state")
    paste_text = next(tool for tool in clipboard["tools"] if tool["name"] == "paste_text")

    assert open_url["platform_support"]["support"] == "cross_platform"
    assert open_url["platform_support"]["ios"] is True
    assert current_url["platform_support"]["support"] == "ios_supported"
    assert current_url["platform_support"]["android"] is False
    assert read_news["platform_support"]["support"] == "ios_supported"
    assert read_news["platform_support"]["ios"] is True
    assert device_health["platform_support"]["support"] == "cross_platform"
    assert app_state["platform_support"]["support"] == "cross_platform"
    assert app_state["platform_support"]["ios"] is True
    assert paste_text["platform_support"]["support"] == "cross_platform"
    assert paste_text["platform_support"]["ios"] is True


def test_tools_platforms_endpoint(client):
    response = client.get("/api/tools/platforms")
    assert response.status_code == 200
    body = response.json()

    supports = {tool["name"]: tool for tool in body["tools"]}

    assert supports["shell"]["support"] == "android_only"
    assert supports["clipboard_get"]["support"] == "cross_platform"
    assert supports["clipboard_get"]["ios"] is True
    assert supports["app_state"]["support"] == "cross_platform"
    assert supports["app_state"]["ios"] is True
    assert supports["extract_articles"]["support"] == "cross_platform"
    assert set(body["categories"]) == {"cross_platform", "android_only", "ios_supported", "ios_planned"}


def test_ios_packages_endpoint_returns_verified_bundle_inventory(client, monkeypatch):
    class FakeIOSDevice:
        def list_apps(self, verify=True):
            assert verify is True
            return [
                {
                    "name": "Chrome",
                    "package": "com.google.chrome.ios",
                    "bundle_id": "com.google.chrome.ios",
                    "platform": "ios",
                    "verified": True,
                    "installed": True,
                }
            ]

    monkeypatch.setattr("gitd.routers.phone.get_device", lambda device: FakeIOSDevice())

    response = client.get("/api/phone/packages/ios:abc123")

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "ios"
    assert body["packages"] == ["com.google.chrome.ios"]
    assert body["apps"][0]["bundle_id"] == "com.google.chrome.ios"
    assert "configured/common" in body["note"]
