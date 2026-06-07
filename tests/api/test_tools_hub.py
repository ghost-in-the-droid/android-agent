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
