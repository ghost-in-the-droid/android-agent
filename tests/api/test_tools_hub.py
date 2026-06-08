def test_tools_hub_exposes_platform_support(client):
    response = client.get("/api/tools")
    assert response.status_code == 200

    categories = response.json()
    web = next(category for category in categories if category["category"] == "Web")
    screen = next(category for category in categories if category["category"] == "Screen Reading")
    input_tools = next(category for category in categories if category["category"] == "Input")
    app_management = next(category for category in categories if category["category"] == "App Management")
    clipboard = next(category for category in categories if category["category"] == "Clipboard & Notifications")
    skills = next(category for category in categories if category["category"] == "Skills")
    open_url = next(tool for tool in web["tools"] if tool["name"] == "open_url")
    current_url = next(tool for tool in web["tools"] if tool["name"] == "get_current_url")
    read_news = next(tool for tool in web["tools"] if tool["name"] == "read_news")
    device_health = next(tool for tool in screen["tools"] if tool["name"] == "device_health")
    fix_device_health = next(tool for tool in screen["tools"] if tool["name"] == "fix_device_health")
    start_recording = next(tool for tool in screen["tools"] if tool["name"] == "start_screen_recording")
    type_unicode = next(tool for tool in input_tools["tools"] if tool["name"] == "type_unicode")
    press_back = next(tool for tool in input_tools["tools"] if tool["name"] == "press_back")
    press_home = next(tool for tool in input_tools["tools"] if tool["name"] == "press_home")
    app_state = next(tool for tool in app_management["tools"] if tool["name"] == "app_state")
    explore_app = next(tool for tool in app_management["tools"] if tool["name"] == "explore_app")
    paste_text = next(tool for tool in clipboard["tools"] if tool["name"] == "paste_text")
    run_workflow = next(tool for tool in skills["tools"] if tool["name"] == "run_workflow")
    run_action = next(tool for tool in skills["tools"] if tool["name"] == "run_action")

    assert open_url["platform_support"]["support"] == "cross_platform"
    assert open_url["platform_support"]["ios"] is True
    assert current_url["platform_support"]["support"] == "ios_supported"
    assert current_url["platform_support"]["android"] is False
    assert read_news["platform_support"]["support"] == "ios_supported"
    assert read_news["platform_support"]["ios"] is True
    assert device_health["platform_support"]["support"] == "cross_platform"
    assert fix_device_health["platform_support"]["support"] == "cross_platform"
    assert fix_device_health["platform_support"]["ios"] is True
    assert start_recording["platform_support"]["support"] == "cross_platform"
    assert start_recording["platform_support"]["ios"] is True
    assert type_unicode["platform_support"]["support"] == "cross_platform"
    assert type_unicode["platform_support"]["ios"] is True
    assert press_back["platform_support"]["support"] == "cross_platform"
    assert press_back["platform_support"]["ios"] is True
    assert press_home["platform_support"]["support"] == "cross_platform"
    assert press_home["platform_support"]["ios"] is True
    assert app_state["platform_support"]["support"] == "cross_platform"
    assert app_state["platform_support"]["ios"] is True
    assert explore_app["platform_support"]["support"] == "cross_platform"
    assert explore_app["platform_support"]["ios"] is True
    assert paste_text["platform_support"]["support"] == "cross_platform"
    assert paste_text["platform_support"]["ios"] is True
    assert run_workflow["platform_support"]["support"] == "cross_platform"
    assert run_workflow["platform_support"]["ios"] is True
    assert run_action["platform_support"]["support"] == "cross_platform"
    assert run_action["platform_support"]["ios"] is True


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
    assert supports["start_screen_recording"]["support"] == "cross_platform"
    assert supports["start_screen_recording"]["ios"] is True
    assert supports["fix_device_health"]["support"] == "cross_platform"
    assert supports["fix_device_health"]["ios"] is True
    assert supports["extract_articles"]["support"] == "cross_platform"
    assert set(body["categories"]) == {"cross_platform", "android_only", "ios_supported", "ios_planned"}


def test_tools_test_endpoint_rejects_unsupported_platform_combo(client):
    android_news = client.post(
        "/api/tools/test",
        json={"name": "read_news", "args": {"device": "emulator-5554", "url": "https://text.npr.org/"}},
    )
    ios_shell = client.post(
        "/api/tools/test",
        json={"name": "shell", "args": {"device": "ios:abc123", "command": "ls"}},
    )

    assert android_news.status_code == 200
    assert android_news.json()["ok"] is False
    assert android_news.json()["platform"] == "android"
    assert android_news.json()["support"] == "ios_supported"
    assert "implemented only for iOS" in android_news.json()["error"]

    assert ios_shell.status_code == 200
    assert ios_shell.json()["ok"] is False
    assert ios_shell.json()["platform"] == "ios"
    assert ios_shell.json()["support"] == "android_only"
    assert "Android-only" in ios_shell.json()["error"]


def test_ios_packages_endpoint_returns_verified_bundle_inventory(client, monkeypatch):
    class FakeIOSDevice:
        def list_apps(self, query="", verify=True):
            assert query == ""
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

    monkeypatch.setattr("gitd.services.device_context.get_device", lambda device: FakeIOSDevice())

    response = client.get("/api/phone/packages/ios:abc123")

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "ios"
    assert body["packages"] == ["com.google.chrome.ios"]
    assert body["apps"][0]["bundle_id"] == "com.google.chrome.ios"
    assert "configured/common" in body["note"]
