def test_tools_hub_exposes_platform_support(client):
    response = client.get("/api/tools")
    assert response.status_code == 200

    categories = response.json()
    web = next(category for category in categories if category["category"] == "Web")
    open_url = next(tool for tool in web["tools"] if tool["name"] == "open_url")
    current_url = next(tool for tool in web["tools"] if tool["name"] == "get_current_url")

    assert open_url["platform_support"]["support"] == "cross_platform"
    assert open_url["platform_support"]["ios"] is True
    assert current_url["platform_support"]["support"] == "ios_supported"
    assert current_url["platform_support"]["android"] is False


def test_tools_platforms_endpoint(client):
    response = client.get("/api/tools/platforms")
    assert response.status_code == 200
    body = response.json()

    supports = {tool["name"]: tool for tool in body["tools"]}

    assert supports["shell"]["support"] == "android_only"
    assert supports["clipboard_get"]["support"] == "cross_platform"
    assert supports["clipboard_get"]["ios"] is True
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
