"""TikTok iOS actions backed by normalized WDA XML."""
from __future__ import annotations

import re
import time

from gitd.bots.common.device import is_ios_ref
from gitd.skills.base import Action, ActionResult

TIKTOK_IOS_BUNDLE_ID = "com.zhiliaoapp.musically"
_POPUP_LABELS = (
    r"\bnot now\b",
    r"\bdon(?:'|\u2019)t allow\b",
    r"\bskip\b",
    r"\bclose\b",
    r"\bcancel\b",
    r"\bcontinue\b",
    r"\bok\b",
)


def _is_ios_device(device) -> bool:
    return is_ios_ref(getattr(device, "serial", ""))


def _node_label(device, node: str) -> str:
    return " ".join(
        [
            device.node_text(node),
            device.node_content_desc(node),
            device.node_rid(node),
        ]
    ).strip()


def _tap_matching_node(device, patterns: tuple[str, ...], *, delay: float = 0.8) -> bool:
    compiled = [re.compile(pattern, re.I) for pattern in patterns if pattern]
    xml = device.dump_xml()
    for node in device.nodes(xml):
        label = _node_label(device, node)
        if label and any(pattern.search(label) for pattern in compiled):
            return bool(device.tap_node(node, delay=delay))
    return False


class OpenApp(Action):
    name = "open_app"
    description = "Launch TikTok on iOS"
    max_retries = 1

    def execute(self) -> ActionResult:
        if not _is_ios_device(self.device):
            return ActionResult(success=False, error="tiktok_ios requires an iOS device ref")
        self.device.launch_app(TIKTOK_IOS_BUNDLE_ID)
        time.sleep(2)
        return ActionResult(success=True, data={"bundle_id": TIKTOK_IOS_BUNDLE_ID})


class DismissPopup(Action):
    name = "dismiss_popup"
    description = "Dismiss common TikTok iOS popups when visible"
    max_retries = 1

    def execute(self) -> ActionResult:
        if not _is_ios_device(self.device):
            return ActionResult(success=False, error="dismiss_popup requires an iOS device ref")
        dismissed = _tap_matching_node(self.device, _POPUP_LABELS, delay=0.8)
        return ActionResult(success=True, data={"dismissed": dismissed})


class TapSearch(Action):
    name = "tap_search"
    description = "Tap TikTok iOS search control"

    def execute(self) -> ActionResult:
        if not _is_ios_device(self.device):
            return ActionResult(success=False, error="tap_search requires an iOS device ref")
        if not _tap_matching_node(self.device, ("\\bsearch\\b",), delay=1.0):
            return ActionResult(success=False, error="Search control not found")
        return ActionResult(success=True)


class TypeAndSearch(Action):
    name = "type_and_search"
    description = "Type a query into TikTok iOS search and submit"

    def __init__(self, device, elements=None, query: str = "", **kwargs):
        super().__init__(device, elements)
        self.query = query

    def execute(self) -> ActionResult:
        if not _is_ios_device(self.device):
            return ActionResult(success=False, error="type_and_search requires an iOS device ref")
        if not self.query:
            return ActionResult(success=False, error="No query provided")
        _tap_matching_node(self.device, ("search", "search or enter", "search field"), delay=0.3)
        self.device.type_text(self.query)
        self.device.press_enter()
        time.sleep(2)
        return ActionResult(success=True, data={"query": self.query})


class NavigateToProfile(Action):
    name = "navigate_to_profile"
    description = "Tap TikTok iOS Profile tab"

    def execute(self) -> ActionResult:
        if not _is_ios_device(self.device):
            return ActionResult(success=False, error="navigate_to_profile requires an iOS device ref")
        if not _tap_matching_node(self.device, ("\\bprofile\\b", "\\bme\\b"), delay=1.0):
            return ActionResult(success=False, error="Profile tab not found")
        return ActionResult(success=True)


class CaptureVisibleText(Action):
    name = "capture_visible_text"
    description = "Capture visible TikTok iOS text for workflow evidence"

    def __init__(self, device, elements=None, max_lines: int = 80, **kwargs):
        super().__init__(device, elements)
        self.max_lines = max(1, int(max_lines))

    def execute(self) -> ActionResult:
        if not _is_ios_device(self.device):
            return ActionResult(success=False, error="capture_visible_text requires an iOS device ref")
        if hasattr(self.device, "extract_visible_text"):
            text = self.device.extract_visible_text(max_lines=self.max_lines)
        else:
            xml = self.device.dump_xml()
            lines: list[str] = []
            seen: set[str] = set()
            for node in self.device.nodes(xml):
                label = _node_label(self.device, node)
                if not label or label in seen:
                    continue
                seen.add(label)
                lines.append(label)
                if len(lines) >= self.max_lines:
                    break
            text = "\n".join(lines)
        lines = [line.strip() for line in text.splitlines() if line.strip()][: self.max_lines]
        return ActionResult(
            success=True,
            data={
                "text": "\n".join(lines),
                "lines": lines,
                "line_count": len(lines),
            },
        )


class VerifyVisibleText(Action):
    name = "verify_visible_text"
    description = "Verify expected text appears in TikTok iOS XML"
    max_retries = 2
    retry_delay = 1.0

    def __init__(self, device, elements=None, expected: str = "TikTok", **kwargs):
        super().__init__(device, elements)
        self.expected = expected

    def execute(self) -> ActionResult:
        xml = self.device.dump_xml()
        if self.expected.lower() in xml.lower():
            return ActionResult(success=True, data={"expected": self.expected})
        return ActionResult(success=False, error=f"Expected text not visible: {self.expected}")
