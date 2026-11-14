"""URL validation accepts native and accessibility-reader attribute ordering."""

from types import SimpleNamespace

import pytest

from gitd.bots.common.adb import Device
from gitd.skills.engine.context import RunContext
from gitd.skills.engine.privacy import secret_scope
from gitd.skills.engine.validators import evaluate

SPEC = {"kind": "url_contains", "substring": "/inbox"}
URL_BAR = "com.android.chrome:id/url_bar"


def check(xml, *, sensitive=False):
    device = SimpleNamespace(dump_xml=lambda: xml, dump_portal_xml=lambda: xml)
    with secret_scope([], sensitive):
        return evaluate(SPEC, RunContext(action_name="register"), device)


@pytest.mark.parametrize("text_first", [False, True])
@pytest.mark.parametrize("path,expected", [("/inbox", True), ("/signup", False)])
def test_url_bar_attribute_order(text_first, path, expected):
    attributes = [f'resource-id="{URL_BAR}"', f'text="https://mail.example{path}"']
    if text_first:
        attributes.reverse()
    xml = "<hierarchy><node " + " ".join(attributes) + "/></hierarchy>"
    assert check(xml) is expected


@pytest.mark.parametrize("sensitive", [False, True])
def test_url_from_actual_accessibility_conversion(sensitive):
    # Exercise the real converter that produced the live false negative. No ADB.
    node = Device("test-device")._portal_node_to_xml(
        {
            "className": "android.widget.EditText",
            "text": "mail.example/u/0/inbox",
            "resourceId": URL_BAR,
            "boundsInScreen": {"left": 151, "top": 45, "right": 442, "bottom": 150},
        }
    )
    assert node.index('text="') < node.index('resource-id="')
    assert check(f"<hierarchy>{node}</hierarchy>", sensitive=sensitive) is True


def test_url_text_must_belong_to_the_address_bar_node():
    xml = (
        f'<hierarchy><node resource-id="{URL_BAR}"/>'
        '<node text="https://mail.example/inbox" resource-id="page-content"/></hierarchy>'
    )
    assert check(xml) is False


def test_url_content_description_fallback():
    xml = '<hierarchy><node content-desc="https://mail.example/inbox"/></hierarchy>'
    assert check(xml) is True


def test_missing_url_fails():
    assert check('<hierarchy><node text="Inbox"/></hierarchy>') is False
