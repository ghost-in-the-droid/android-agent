import html
import re

from gitd.skills.tiktok_ios import load
from gitd.skills.tiktok_ios.actions import (
    CaptureVisibleText,
    DismissPopup,
    NavigateToProfile,
    OpenApp,
    TapSearch,
    TypeAndSearch,
    VerifyVisibleText,
    WaitVisibleText,
)
from gitd.skills.tiktok_ios.actions.core import TIKTOK_IOS_BUNDLE_ID
from gitd.skills.tiktok_ios.workflows import OpenAppSmoke, ProfileSmoke, SearchSmoke


TIKTOK_XML = """<hierarchy>
<node text="TikTok" content-desc="TikTok" resource-id="TikTok" class="XCUIElementTypeApplication" clickable="false" bounds="[0,0][390,844]" />
<node text="Close" content-desc="Close" resource-id="Close" class="XCUIElementTypeButton" clickable="true" bounds="[344,44][384,84]" />
<node text="Search" content-desc="Search" resource-id="Search" class="XCUIElementTypeButton" clickable="true" bounds="[300,44][380,96]" />
<node text="Search or enter URL" content-desc="Search field" resource-id="Search field" class="XCUIElementTypeSearchField" clickable="true" bounds="[20,90][370,134]" />
<node text="Profile" content-desc="Profile" resource-id="Profile" class="XCUIElementTypeButton" clickable="true" bounds="[300,780][380,836]" />
</hierarchy>"""


class FakeIOSDevice:
    serial = "ios:abc123"

    def __init__(self):
        self.launched = []
        self.typed = []
        self.keys = []
        self.tapped = []

    def launch_app(self, bundle_id, *args, **kwargs):
        self.launched.append(bundle_id)

    def dump_xml(self) -> str:
        if self.typed:
            query = html.escape(self.typed[-1])
            return (
                TIKTOK_XML.replace("</hierarchy>", "")
                + f'<node text="{query}" content-desc="{query}" resource-id="Search query" '
                + 'class="XCUIElementTypeStaticText" clickable="false" bounds="[20,150][370,190]" />'
                + "</hierarchy>"
            )
        return TIKTOK_XML

    def nodes(self, xml: str) -> list[str]:
        return re.findall(r"<node[^>]+/?>", xml)

    def node_text(self, node: str) -> str:
        return self._attr(node, "text")

    def node_content_desc(self, node: str) -> str:
        return self._attr(node, "content-desc")

    def node_rid(self, node: str) -> str:
        return self._attr(node, "resource-id")

    def tap_node(self, node: str, delay=0.8) -> bool:
        self.tapped.append(self.node_text(node) or self.node_content_desc(node) or self.node_rid(node))
        return True

    def type_text(self, text: str, *args, **kwargs):
        self.typed.append(text)

    def press_enter(self, *args, **kwargs):
        self.keys.append("ENTER")

    @staticmethod
    def _attr(node: str, attr: str) -> str:
        m = re.search(rf'\b{re.escape(attr)}="([^"]*)"', node)
        return html.unescape(m.group(1).strip()) if m else ""


def test_tiktok_ios_skill_loads_actions_workflows_and_elements():
    skill = load()
    device = FakeIOSDevice()

    assert skill.name == "tiktok_ios"
    assert skill.platforms == ["ios"]
    assert skill.ios_bundle_id == TIKTOK_IOS_BUNDLE_ID
    assert set(skill.list_actions()) == {
        "open_app",
        "dismiss_popup",
        "tap_search",
        "type_and_search",
        "navigate_to_profile",
        "capture_visible_text",
        "wait_visible_text",
        "verify_visible_text",
    }
    assert set(skill.list_workflows()) == {"open_app_smoke", "search_smoke", "profile_smoke"}
    assert "search_tab" in skill._elements_for_device(device)


def test_tiktok_ios_actions_use_normalized_ios_tree(monkeypatch):
    monkeypatch.setattr("gitd.skills.tiktok_ios.actions.core.time.sleep", lambda *_args, **_kwargs: None)
    device = FakeIOSDevice()

    assert OpenApp(device).run().success is True
    assert device.launched == [TIKTOK_IOS_BUNDLE_ID]

    assert DismissPopup(device).run().data == {"dismissed": True}
    assert TapSearch(device).run().success is True
    assert TypeAndSearch(device, query="#cats").run().data == {"query": "#cats"}
    assert WaitVisibleText(device, expected="#cats", timeout=0).run().success is True
    assert NavigateToProfile(device).run().success is True
    captured = CaptureVisibleText(device, max_lines=3).run()
    assert captured.success is True
    assert captured.data["lines"] == [
        "TikTok TikTok TikTok",
        "Close Close Close",
        "Search Search Search",
    ]
    assert VerifyVisibleText(device, expected="TikTok").run().success is True

    assert device.tapped[:4] == ["Close", "Search", "Search", "Profile"]
    assert device.typed == ["#cats"]
    assert device.keys == ["ENTER"]


def test_tiktok_ios_wait_visible_text_returns_evidence_on_timeout(monkeypatch):
    monkeypatch.setattr("gitd.skills.tiktok_ios.actions.core.time.sleep", lambda *_args, **_kwargs: None)
    device = FakeIOSDevice()

    result = WaitVisibleText(device, expected="not on screen", timeout=0).run()

    assert result.success is False
    assert result.error == "Expected text not visible: not on screen"
    assert result.data["expected"] == "not on screen"
    assert result.data["attempts"] == 1
    assert "TikTok" in result.data["visible_text"]


def test_tiktok_ios_rejects_android_device(monkeypatch):
    monkeypatch.setattr("gitd.skills.tiktok_ios.actions.core.time.sleep", lambda *_args, **_kwargs: None)
    device = FakeIOSDevice()
    device.serial = "emulator-5554"

    result = OpenApp(device).run()

    assert result.success is False
    assert "requires an iOS device ref" in result.error
    assert device.launched == []


def test_tiktok_ios_smoke_workflows_are_registered_with_safe_steps(monkeypatch):
    monkeypatch.setattr("gitd.skills.tiktok_ios.actions.core.time.sleep", lambda *_args, **_kwargs: None)
    device = FakeIOSDevice()

    open_wf = OpenAppSmoke(device)
    search_wf = SearchSmoke(device, query="#news", max_lines=3)
    profile_wf = ProfileSmoke(device, max_lines=2)
    search_steps = search_wf.steps()

    assert [step.name for step in open_wf.steps()] == ["open_app", "dismiss_popup"]
    assert [step.name for step in search_steps] == [
        "open_app",
        "dismiss_popup",
        "tap_search",
        "type_and_search",
        "wait_visible_text",
        "capture_visible_text",
    ]
    assert [step.name for step in profile_wf.steps()] == [
        "open_app",
        "dismiss_popup",
        "navigate_to_profile",
        "wait_visible_text",
        "capture_visible_text",
    ]
    assert search_steps[-3].query == "#news"
    assert search_steps[-1].max_lines == 3
    assert search_steps[-2].expected == "#news"
    assert profile_wf.steps()[-1].max_lines == 2

    search_result = load().get_workflow("search_smoke", device, query="#news").run()
    assert search_result.success is True
    assert search_result.data["completed_steps"] == 6
    assert search_result.data["step_results"][-3]["data"] == {"query": "#news"}
    assert search_result.data["step_results"][-2]["name"] == "wait_visible_text"
    assert search_result.data["step_results"][-2]["data"]["expected"] == "#news"
    assert search_result.data["step_results"][-1]["name"] == "capture_visible_text"
    assert search_result.data["step_results"][-1]["data"]["line_count"] == 6

    profile_result = load().get_workflow("profile_smoke", device, max_lines=2).run()
    assert profile_result.success is True
    assert profile_result.data["completed_steps"] == 5
    assert profile_result.data["step_results"][-2]["name"] == "wait_visible_text"
    assert profile_result.data["step_results"][-2]["data"]["expected"] == "Profile"
    assert profile_result.data["step_results"][-1]["name"] == "capture_visible_text"
    assert profile_result.data["step_results"][-1]["data"]["line_count"] == 2
