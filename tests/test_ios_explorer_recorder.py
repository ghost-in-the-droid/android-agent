import base64
import json

from gitd.skills.auto_creator import AppExplorer, ios_state_hash
from gitd.skills.macro_recorder import Macro, MacroRecorder, MacroStep


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)

IOS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0" platform="ios">
  <node index="0" text="" resource-id="" class="XCUIElementTypeApplication" content-desc="" clickable="false" bounds="[0,0][390,844]">
    <node index="1" text="Top Story" resource-id="headline" class="XCUIElementTypeButton" content-desc="" clickable="true" bounds="[10,20][180,80]" />
  </node>
</hierarchy>
"""


class FakeIOSDevice:
    serial = "ios:abc123"

    def __init__(self):
        self.launched: list[str] = []
        self.taps: list[tuple[int, int]] = []
        self.keys: list[str] = []
        self.typed: list[str] = []
        self.back_count = 0

    def launch_app(self, bundle_id: str):
        self.launched.append(bundle_id)

    def dump_xml(self) -> str:
        return IOS_XML

    def take_screenshot(self) -> bytes:
        return PNG_BYTES

    def get_phone_state(self) -> dict:
        return {"bundleId": self.launched[-1] if self.launched else "com.example.app"}

    def tap(self, x: int, y: int, delay: float = 0):
        self.taps.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 500, delay: float = 0):
        pass

    def back(self, delay: float = 0):
        self.back_count += 1

    def type_text(self, text: str):
        self.typed.append(text)

    def press_key(self, key: str):
        self.keys.append(key)


def test_ios_app_explorer_uses_bundle_id_and_wda_screenshot(tmp_path):
    dev = FakeIOSDevice()
    explorer = AppExplorer(
        dev=dev,
        package="com.google.chrome.ios",
        output_dir=str(tmp_path),
        max_depth=0,
        max_states=1,
        settle_time=0,
    )

    graph = explorer.explore()

    assert dev.launched == ["com.google.chrome.ios"]
    assert graph["platform"] == "ios"
    assert graph["package"] == "com.google.chrome.ios"
    assert graph["state_identity"]["ios"] == ["bundle_id", "activity", "xml_structure_hash", "screenshot_hash"]
    assert graph["total_states"] == 1

    state = next(iter(graph["states"].values()))
    assert state["activity"] == "com.google.chrome.ios"
    assert state["elements"][0]["text"] == "Top Story"
    assert (tmp_path / "state_graph.json").exists()
    assert (tmp_path / "screenshots" / f"{state['state_id']}.png").read_bytes() == PNG_BYTES
    assert json.loads((tmp_path / "state_graph.json").read_text())["platform"] == "ios"


def test_ios_app_explorer_progress_includes_dashboard_metadata(tmp_path):
    dev = FakeIOSDevice()
    explorer = AppExplorer(
        dev=dev,
        package="com.google.chrome.ios",
        output_dir=str(tmp_path),
        max_depth=1,
        max_states=3,
        settle_time=0,
    )
    explorer._write_progress(current_depth=0)

    progress = json.loads((tmp_path / "progress.json").read_text())

    assert progress["device"] == "ios:abc123"
    assert progress["package"] == "com.google.chrome.ios"
    assert progress["platform"] == "ios"
    assert progress["output_dir"] == str(tmp_path)
    assert progress["current_activity"] == ""
    assert progress["max_states"] == 3


def test_ios_state_hash_uses_bundle_activity_tree_and_screenshot():
    same = ios_state_hash("com.example.app", "com.example.app", IOS_XML, PNG_BYTES)

    assert ios_state_hash("com.example.app", "com.example.app", IOS_XML, PNG_BYTES) == same
    assert ios_state_hash("com.other.app", "com.example.app", IOS_XML, PNG_BYTES) != same
    assert ios_state_hash("com.example.app", "com.other.app", IOS_XML, PNG_BYTES) != same
    assert ios_state_hash("com.example.app", "com.example.app", IOS_XML, b"different") != same


def test_ios_macro_recorder_replays_type_and_home_with_ios_primitives():
    dev = FakeIOSDevice()
    recorder = MacroRecorder(dev)
    macro = Macro(
        name="ios_macro",
        device_serial=dev.serial,
        steps=[
            MacroStep(action="type", timestamp=0.0, params={"text": "hello world"}),
            MacroStep(action="home", timestamp=0.0),
        ],
    )

    recorder.replay(macro, speed=10)

    assert dev.typed == ["hello world"]
    assert dev.keys == ["HOME"]
