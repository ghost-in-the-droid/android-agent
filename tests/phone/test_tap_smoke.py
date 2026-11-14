"""tap_smoke — LaunchApp + TapElement open a Settings sub-page."""

from gitd.skills._base.actions.core import LaunchApp, TapElement
from gitd.skills.base import Element

from .helpers import screen_texts, wait_settled, wait_until

SETTINGS = "com.android.settings"
ELEMENTS = {"battery": Element("battery", text="Battery")}


def test_tap_opens_battery_page(phone):
    phone.adb("shell", "am", "force-stop", SETTINGS)
    assert LaunchApp(phone, None, package=SETTINGS).run(), "Settings did not come to the foreground"
    assert wait_settled(phone, text="Battery"), "Battery row never rendered or kept moving"

    result = TapElement(phone, ELEMENTS, element_name="battery").run()
    assert result, f"tap_element failed: {result.error}"

    # The Battery page replaces the home list; "Battery usage" only exists on it.
    texts = wait_until(lambda: (t := screen_texts(phone)) and "Battery usage" in t and t)
    assert texts, f"tap did not navigate to the Battery page; on screen: {screen_texts(phone)[:15]}"
