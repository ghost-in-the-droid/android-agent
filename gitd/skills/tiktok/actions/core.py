"""TikTok core actions — open, navigate, search, dismiss popups."""
from __future__ import annotations

import time
from gitd.skills.base import Action, ActionResult

TIKTOK_PKG = "com.zhiliaoapp.musically"
TIKTOK_SPLASH = f"{TIKTOK_PKG}/com.ss.android.ugc.aweme.splash.SplashActivity"


class OpenApp(Action):
    """Launch TikTok and wait for home screen."""
    name = 'open_app'
    description = 'Force-stop TikTok and relaunch to home screen'

    def execute(self) -> ActionResult:
        self.device.adb("shell", "am", "force-stop", TIKTOK_PKG)
        time.sleep(1)
        self.device.adb("shell", "am", "start", "-n", TIKTOK_SPLASH)
        time.sleep(4)
        # Dismiss any startup popups
        for _ in range(3):
            xml = self.device.dump_xml()
            if self.device.dismiss_popups(xml):
                time.sleep(1)
            else:
                break
        return ActionResult(success=True)

    def postcondition(self) -> bool:
        output = self.device.adb("shell", "dumpsys", "window", timeout=5)
        return TIKTOK_PKG in output


class NavigateToProfile(Action):
    """Navigate to the Profile tab from anywhere in TikTok."""
    name = 'navigate_to_profile'
    description = 'Tap Profile tab in bottom nav'

    def execute(self) -> ActionResult:
        pos = self.find_element('profile_tab')
        if not pos:
            return ActionResult(success=False, error='Profile tab not found')
        self.device.tap(*pos)
        time.sleep(2)
        return ActionResult(success=True, data={'pos': pos})

    def postcondition(self) -> bool:
        xml = self.device.dump_xml()
        # Profile page should show followers count or display name
        return (self.device.find_bounds(xml, resource_id=self.elements.get('followers_count', {}) and
                self.elements['followers_count'].resource_id or 'r1p') is not None or
                'Following' in xml)


class TapSearch(Action):
    """Tap the search icon on the home screen."""
    name = 'tap_search'
    description = 'Open TikTok search'

    def execute(self) -> ActionResult:
        pos = self.find_element('search_icon')
        if not pos:
            return ActionResult(success=False, error='Search icon not found')
        self.device.tap(*pos)
        time.sleep(2)
        return ActionResult(success=True, data={'pos': pos})

    def postcondition(self) -> bool:
        xml = self.device.dump_xml()
        el = self.elements.get('search_box')
        if el and el.resource_id:
            return self.device.find_bounds(xml, resource_id=el.resource_id) is not None
        return 'Search' in xml


class TypeAndSearch(Action):
    """Type a query into the search box and submit."""
    name = 'type_and_search'
    description = 'Type query and press Enter to search'

    def __init__(self, device, elements, *, query: str = '', **kwargs):
        super().__init__(device, elements)
        self.query = query

    def precondition(self) -> bool:
        xml = self.device.dump_xml()
        el = self.elements.get('search_box')
        if el and el.resource_id:
            return self.device.find_bounds(xml, resource_id=el.resource_id) is not None
        return True

    def execute(self) -> ActionResult:
        if not self.query:
            return ActionResult(success=False, error='No query provided')
        # Tap search box
        pos = self.find_element('search_box')
        if pos:
            self.device.tap(*pos, delay=0.3)
        # Clear and type
        self.device.adb("shell", "input", "text", self.query.replace(' ', '%s'))
        time.sleep(0.5)
        self.device.press_enter()
        time.sleep(2)
        return ActionResult(success=True, data={'query': self.query})


class DismissPopup(Action):
    """Detect and dismiss any TikTok popup dialog using skill-defined detectors."""
    name = 'dismiss_popup'
    description = 'Dismiss popups using skill-defined detectors'
    max_retries = 1

    def execute(self) -> ActionResult:
        xml = self.device.dump_xml()
        # Use skill-specific popup detectors if available
        popups = getattr(self, '_popup_detectors', None)
        dismissed = self.device.dismiss_popups(xml, popups=popups)
        return ActionResult(success=True, data={'dismissed': dismissed})
