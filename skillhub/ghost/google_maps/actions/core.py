"""Google Maps core actions — search, directions, travel mode, route summary."""
from __future__ import annotations

import re
import time

from gitd.skills.base import Action, ActionResult

MAPS_PKG = "com.google.android.apps.maps"

# Travel mode → content-desc prefix on the directions mode tabs.
# Descs are dynamic ("Driving mode: 10 minutes"), so tabs are located by
# prefix regex — the Element locator chain only does exact matches.
MODE_DESC_PREFIX = {
    "driving": "Driving mode",
    "transit": "Public transport mode",
    "walking": "Walking mode",
    "cycling": "Cycling mode",
}


def find_desc_prefix(device, xml: str, prefix: str) -> tuple[int, int] | None:
    """Center of the first node whose content-desc starts with prefix."""
    for node in device.nodes(xml):
        if device.node_content_desc(node).startswith(prefix):
            b = device.node_bounds(node)
            if b:
                return device.node_center(b)
    return None


class OpenApp(Action):
    """Force-stop Google Maps and relaunch to the explore/home screen."""
    name = "open_app"
    description = "Force-stop Google Maps and relaunch"

    def execute(self) -> ActionResult:
        self.device.adb("shell", "am", "force-stop", MAPS_PKG)
        time.sleep(1)
        self.device.adb("shell", "monkey", "-p", MAPS_PKG,
                        "-c", "android.intent.category.LAUNCHER", "1")
        time.sleep(5)
        return ActionResult(success=True)

    def postcondition(self) -> bool:
        output = self.device.adb("shell", "dumpsys", "window", timeout=5)
        return MAPS_PKG in output


class SearchPlace(Action):
    """Type a place into the search box and land on its place card.

    Handles both outcomes of a search: direct hit (place card opens) and
    results list (taps the first result). Steps are linear in a Workflow,
    so this branching lives inside one action.
    """
    name = "search_place"
    description = "Search a place and open its place card"

    def __init__(self, device, elements=None, *, query: str = "", **kwargs):
        super().__init__(device, elements)
        self.query = query

    def precondition(self) -> bool:
        return bool(self.query) and self.find_element("search_box") is not None

    def execute(self) -> ActionResult:
        pos = self.find_element("search_box")
        if not pos:
            return ActionResult(success=False, error="search box not found")
        self.device.tap(*pos, delay=1.5)

        text = str(self.query)
        if all(ord(c) < 128 for c in text):
            from gitd.bots.common.adb import input_text_arg
            self.device.adb("shell", "input", "text", input_text_arg(text))
        else:
            # Umlauts/ß in German addresses — `input text` can't type these
            self.device.type_unicode(text)
        time.sleep(0.5)
        self.device.press_enter(delay=3.0)

        # Direct hit → place card with a "Directions …" button
        for _ in range(4):
            xml = self.device.dump_xml()
            if find_desc_prefix(self.device, xml, "Directions"):
                return ActionResult(success=True, data={"query": text, "via": "place_card"})
            time.sleep(1.5)

        # Results list → tap the first result row below the omnibox
        xml = self.device.dump_xml()
        first = self._first_result(xml)
        if first:
            self.device.tap(*first, delay=3.0)
            xml = self.device.dump_xml()
            if find_desc_prefix(self.device, xml, "Directions"):
                return ActionResult(success=True, data={"query": text, "via": "results_list"})
        return ActionResult(success=False, error=f"no place card for query: {text}")

    def _first_result(self, xml: str) -> tuple[int, int] | None:
        """Topmost clickable node below the search omnibox (y > 220)."""
        candidates = []
        for node in self.device.nodes(xml):
            if 'clickable="true"' not in node:
                continue
            b = self.device.node_bounds(node)
            if b and b[1] > 220 and (b[2] - b[0]) > 500:
                candidates.append(b)
        if not candidates:
            return None
        candidates.sort(key=lambda b: b[1])
        return self.device.node_center(candidates[0])

    def postcondition(self) -> bool:
        xml = self.device.dump_xml()
        return find_desc_prefix(self.device, xml, "Directions") is not None


class OpenDirections(Action):
    """Tap the Directions button on an open place card."""
    name = "open_directions"
    description = "Open the directions view from a place card"

    def execute(self) -> ActionResult:
        xml = self.device.dump_xml()
        # Dynamic desc: "Directions to <place>"
        pos = find_desc_prefix(self.device, xml, "Directions")
        if not pos:
            return ActionResult(success=False, error="Directions button not found")
        self.device.tap(*pos, delay=4.0)
        return ActionResult(success=True)

    def postcondition(self) -> bool:
        xml = self.device.dump_xml()
        return (self.find_element("mode_tabs", xml) is not None
                or find_desc_prefix(self.device, xml, "Driving mode") is not None)


class SelectTravelMode(Action):
    """Select a travel mode tab (driving / transit / walking / cycling)."""
    name = "select_travel_mode"
    description = "Select travel mode on the directions screen"

    def __init__(self, device, elements=None, *, mode: str = "driving", **kwargs):
        super().__init__(device, elements)
        self.mode = str(mode).lower()

    def precondition(self) -> bool:
        return self.mode in MODE_DESC_PREFIX

    def execute(self) -> ActionResult:
        prefix = MODE_DESC_PREFIX[self.mode]
        xml = self.device.dump_xml()
        pos = find_desc_prefix(self.device, xml, prefix)
        if not pos:
            return ActionResult(success=False, error=f"mode tab not found: {self.mode}")
        self.device.tap(*pos, delay=3.0)
        return ActionResult(success=True, data={"mode": self.mode})


class ReadRouteSummary(Action):
    """Parse the directions screen into structured route data. Read-only."""
    name = "read_route_summary"
    description = "Read ETA, distance, and per-mode times from the directions screen"

    def __init__(self, device, elements=None, *, mode: str = "", **kwargs):
        super().__init__(device, elements)
        self.mode = str(mode).lower()

    def execute(self) -> ActionResult:
        xml = self.device.dump_xml()
        data: dict = {"modes": {}}

        # Per-mode ETAs: "Driving mode: 10 minutes" / "Public transport mode: 23 minutes"
        for mode, prefix in MODE_DESC_PREFIX.items():
            m = re.search(rf'content-desc="{prefix}: ([^"]+)"', xml)
            if m:
                data["modes"][mode] = m.group(1)

        # ETA of the mode actually shown. Prefer the mode this action was
        # asked about — the Portal XML path drops the selected="true"
        # attribute, so the regex below only works on uiautomator dumps.
        if self.mode in data["modes"]:
            data["selected_mode"] = self.mode
            data["eta"] = data["modes"][self.mode]
        else:
            m = re.search(r'content-desc="([A-Za-z ]+) mode: ([^"]+)"[^>]*selected="true"', xml)
            if m:
                data["selected_mode"] = m.group(1).lower()
                data["eta"] = m.group(2)

        # Selected route: "Selected route 10 minutes via Torstraße",
        # walking/cycling prefix it: "Walk route, Selected route 39 minutes via …"
        m = re.search(r'content-desc="(?:[^"]*?, )?Selected route ([^"]+)"', xml)
        if m:
            data["selected_route"] = m.group(1)
        m = re.search(r'text="\(([\d.,]+\s*(?:km|m|mi|ft))\)"', xml)
        if m:
            data["distance"] = m.group(1).replace(" ", " ")

        # Start / destination labels
        m = re.search(r'content-desc="Start location, ([^"]+)"', xml)
        if m:
            data["origin"] = m.group(1)
        m = re.search(r'content-desc="Destination, ([^"]+)"', xml)
        if m:
            data["destination"] = m.group(1)

        if not data["modes"] and "eta" not in data:
            return ActionResult(success=False, error="no route data on screen")
        return ActionResult(success=True, data=data)


class CloseCard(Action):
    """Close the current place card or directions view."""
    name = "close_card"
    description = "Close the open card via its header close button"
    max_retries = 1

    def execute(self) -> ActionResult:
        pos = self.find_element("close_card")
        if not pos:
            return ActionResult(success=False, error="close button not found")
        self.device.tap(*pos, delay=1.5)
        return ActionResult(success=True)
