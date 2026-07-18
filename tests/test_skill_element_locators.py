from gitd.bots.common.ios import IOSDevice
from gitd.skills.base import Element


IOS_XML = """
<hierarchy rotation="0" platform="ios">
  <node text="" content-desc="" resource-id="" class="XCUIElementTypeButton"
        clickable="true" visible="true" bounds="[10,20][110,60]"/>
  <node text="Address" content-desc="Address" resource-id="" class="XCUIElementTypeTextField"
        clickable="true" visible="true" bounds="[20,80][320,124]"/>
</hierarchy>
"""


def test_element_find_uses_ios_class_name_locator():
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    element = Element.from_dict("first_button", {"class_name": "XCUIElementTypeButton"})

    assert element.find(dev, IOS_XML) == (60, 40)


def test_element_find_accepts_class_alias_from_generated_ios_yaml():
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    element = Element.from_dict("address", {"class": "XCUIElementTypeTextField"})

    assert element.class_name == "XCUIElementTypeTextField"
    assert element.find(dev, IOS_XML) == (170, 102)


def test_element_find_prefers_text_before_class_fallback():
    dev = IOSDevice("ios:abc123", appium_url="http://appium.local")
    element = Element.from_dict(
        "address",
        {"text": "Address", "class_name": "XCUIElementTypeButton"},
    )

    assert element.find(dev, IOS_XML) == (170, 102)
