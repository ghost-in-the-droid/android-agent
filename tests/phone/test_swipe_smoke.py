"""swipe_smoke — SwipeDirection scrolls the Settings home list."""

from gitd.skills._base.actions.core import LaunchApp, SwipeDirection

from .helpers import screen_texts, wait_until

SETTINGS = "com.android.settings"
ANCHOR = "Battery"  # a mid-list row that stays in the tree before and after the swipe
MIN_SCROLL_PX = 300


def anchor_top(dev) -> int | None:
    """Top y of the ANCHOR row, or None if it is not in the UI tree."""
    bounds = dev.find_bounds(dev.dump_xml(), text=ANCHOR)
    return dev.node_bounds(f'bounds="{bounds}"')[1] if bounds else None


def test_swipe_up_scrolls_settings_list(phone):
    phone.adb("shell", "am", "force-stop", SETTINGS)
    assert LaunchApp(phone, None, package=SETTINGS).run(), "Settings did not come to the foreground"
    assert wait_until(lambda: "Search settings" in screen_texts(phone)), "Settings home page never rendered"
    before = wait_until(lambda: anchor_top(phone))
    assert before, f"{ANCHOR!r} row not on the Settings home page"

    result = SwipeDirection(phone, None, direction="up", distance=1000).run()
    assert result, f"swipe_direction failed: {result.error}"

    # Compare the anchor row's position, not which rows are present: on GH runners
    # rows scrolled off the top stay in the uiautomator tree with clipped bounds.
    # Poll because a software-GPU emulator can take seconds to settle the fling.
    after = wait_until(lambda: (y := anchor_top(phone)) is not None and before - y >= MIN_SCROLL_PX and y)
    assert after, f"swipe did not scroll the list: {ANCHOR!r} top was y={before}, now y={anchor_top(phone)}"
