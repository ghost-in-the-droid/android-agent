from gitd.bots.common.ios import IOSDevice


def test_ios_dismiss_popups_taps_skill_specific_button(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    taps = []
    monkeypatch.setattr(dev, "tap", lambda x, y, delay=0.8: taps.append((x, y, delay)))

    xml = """
    <hierarchy rotation="0" platform="ios">
      <node text="Turn on notifications" content-desc="" resource-id="" class="XCUIElementTypeStaticText"
            clickable="false" visible="true" bounds="[40,300][350,340]"/>
      <node text="Not now" content-desc="" resource-id="" class="XCUIElementTypeButton"
            clickable="true" visible="true" bounds="[120,420][270,470]"/>
    </hierarchy>
    """

    dismissed = dev.dismiss_popups(
        xml,
        popups=[{"detect": "Turn on notifications", "button": "Not now", "label": "Notification prompt"}],
    )

    assert dismissed is True
    assert taps == [(195, 445, 1.0)]


def test_ios_dismiss_popups_uses_generic_compact_button_fallback(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    taps = []
    monkeypatch.setattr(dev, "tap", lambda x, y, delay=0.8: taps.append((x, y, delay)))

    xml = """
    <hierarchy rotation="0" platform="ios">
      <node text="Newsletter content should not be tapped" content-desc="" resource-id=""
            class="XCUIElementTypeStaticText" clickable="true" visible="true"
            bounds="[0,120][390,500]"/>
      <node text="Cancel" content-desc="" resource-id="" class="XCUIElementTypeButton"
            clickable="false" visible="true" bounds="[140,600][250,644]"/>
    </hierarchy>
    """

    dismissed = dev.dismiss_popups(xml, popups=[])

    assert dismissed is True
    assert taps == [(195, 622, 1.0)]


def test_ios_dismiss_popups_supports_back_method(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    backs = []
    monkeypatch.setattr(dev, "back", lambda delay=1.0: backs.append(delay))

    xml = """
    <hierarchy rotation="0" platform="ios">
      <node text="Limited offer" content-desc="" resource-id="" class="XCUIElementTypeStaticText"
            clickable="false" visible="true" bounds="[20,200][370,260]"/>
    </hierarchy>
    """

    dismissed = dev.dismiss_popups(xml, popups=[{"detect": "Limited offer", "method": "back"}])

    assert dismissed is True
    assert backs == [1.0]


def test_ios_dismiss_popups_ignores_large_content_nodes(monkeypatch):
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    taps = []
    monkeypatch.setattr(dev, "tap", lambda x, y, delay=0.8: taps.append((x, y, delay)))

    xml = """
    <hierarchy rotation="0" platform="ios">
      <node text="Cancel culture article headline" content-desc="" resource-id=""
            class="XCUIElementTypeStaticText" clickable="true" visible="true"
            bounds="[0,120][390,500]"/>
    </hierarchy>
    """

    dismissed = dev.dismiss_popups(xml, popups=[])

    assert dismissed is False
    assert taps == []
