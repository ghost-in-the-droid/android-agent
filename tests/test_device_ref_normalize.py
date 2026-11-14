"""Device arguments copied from list_devices display lines resolve to the bare id, never widen scope."""

import asyncio
from types import SimpleNamespace

import pytest

from gitd import mcp_server
from gitd.bots.common import device
from gitd.bots.common.device import DeviceRefError, resolve_device_ref
from gitd.services import agent_tools
from gitd.skills.engine import runner


@pytest.fixture(autouse=True)
def connected(monkeypatch):
    monkeypatch.delenv("GHOST_DEVICE", raising=False)
    monkeypatch.delenv("ANDROID_SERIAL", raising=False)
    monkeypatch.setattr(device, "list_connected", lambda: ["phone-x", "phone-y"])
    monkeypatch.setattr(device, "ios_refs_from_host", lambda: ["ios:fake-udid"])
    monkeypatch.setattr(device, "ios_enabled", lambda: True)


@pytest.mark.parametrize(
    "raw",
    [
        "phone-x (SM-A1)",
        "phone-x  model=SM-A1",
        '"phone-x"',
        "'phone-x'",
        "`phone-x`",
        "`phone-x (SM-A1)`",
        "  phone-x\n",
        '"phone-x (SM-A1)"',
    ],
)
def test_display_line_quotes_and_backticks_resolve_to_the_id(raw):
    assert resolve_device_ref(raw) == "phone-x"


def test_ios_display_line_with_nested_parentheses_resolves():
    raw = "ios:fake-udid  model=Test iPhone  platform=iOS  hint=Start Appium (port 4723)."
    assert resolve_device_ref(raw) == "ios:fake-udid"
    assert resolve_device_ref("ios:fake-udid (Test iPhone; iOS)") == "ios:fake-udid"


def test_verbatim_and_empty_values_pass_through_without_enumeration(monkeypatch):
    monkeypatch.setattr(device, "list_connected", lambda: pytest.fail("verbatim ids need no adb probe"))
    assert resolve_device_ref("phone-x") == "phone-x"
    assert resolve_device_ref("fake:demo") == "fake:demo"
    assert resolve_device_ref("") == ""
    assert resolve_device_ref("  ") == ""


def test_unknown_display_line_is_refused_naming_the_valid_ids():
    with pytest.raises(DeviceRefError) as exc:
        resolve_device_ref("phone-z (SM-A9)")
    message = str(exc.value)
    assert "not a connected device id" in message
    assert "phone-x, phone-y, ios:fake-udid" in message


@pytest.mark.parametrize("variable", ["GHOST_DEVICE", "ANDROID_SERIAL"])
def test_scope_is_never_widened_by_normalization(monkeypatch, variable):
    monkeypatch.setenv(variable, "phone-x")
    assert resolve_device_ref("phone-x (SM-A1)") == "phone-x"
    with pytest.raises(DeviceRefError) as exc:
        resolve_device_ref("phone-y (SM-A2)")  # connected, but outside the session scope
    assert "outside this session's device scope" in str(exc.value)
    assert "Valid device id(s): phone-x." in str(exc.value)
    assert "phone-y," not in str(exc.value)


def test_scope_accepts_its_own_ref_even_when_not_enumerated(monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", "phone-q")
    assert resolve_device_ref("`phone-q (SM-A3)`") == "phone-q"


def _record_mcp_device(monkeypatch):
    seen = []
    monkeypatch.setattr(mcp_server, "get_device", lambda ref: SimpleNamespace(back=lambda: seen.append(ref)))
    return seen


def test_mcp_tool_call_with_display_line_drives_the_bare_id(monkeypatch):
    seen = _record_mcp_device(monkeypatch)
    asyncio.run(mcp_server.mcp.call_tool("press_back", {"device": "phone-x (SM-A1)"}))
    assert seen == ["phone-x"]


def test_mcp_tool_call_out_of_scope_is_refused_before_device_use(monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", "phone-x")
    seen = _record_mcp_device(monkeypatch)
    result = mcp_server.press_back("phone-y (SM-A2)")
    assert seen == []
    assert result.startswith("Error: device 'phone-y (SM-A2)' is outside")
    assert 'device="phone-x"' in result


def test_mcp_list_devices_lines_round_trip_through_the_normalizer(monkeypatch):
    monkeypatch.setattr(mcp_server, "Device", lambda ref: SimpleNamespace(adb=lambda *a, **k: "SM-A1 (Galaxy)"))
    monkeypatch.setattr(mcp_server, "_ios_device_details_by_serial", lambda: {})
    lines = mcp_server.list_devices().splitlines()
    assert lines[0] == mcp_server.DEVICE_LIST_HEADER
    assert [resolve_device_ref(line) for line in lines[1:]] == ["phone-x", "phone-y", "ios:fake-udid"]


def test_agent_tool_call_normalizes_and_refuses(monkeypatch):
    seen = []
    monkeypatch.setattr(agent_tools, "_execute_tool_inner", lambda name, args: seen.append(args["device"]) or "ok")
    assert agent_tools.execute_tool("get_phone_state", {"device": "`phone-x (SM-A1)`"}) == "ok"
    assert seen == ["phone-x"]
    result = agent_tools.execute_tool("get_phone_state", {"device": "phone-z (SM-A9)"})
    assert result.startswith("Error: device 'phone-z (SM-A9)' is not a connected device id")
    assert seen == ["phone-x"]


def _fake_skill():
    action = SimpleNamespace(name="go", params=[], requires_state=[])
    return SimpleNamespace(name="fake-skill", actions=[action], action_names=lambda: ["go"], action=lambda name: action)


def test_run_skill_engine_normalizes_device_serial(monkeypatch):
    seen = []

    def fake_run(skill, name, supplied, device_serial, trace, **options):
        seen.append(device_serial)
        return runner.RunResult(success=True, skill=skill.name, action=name)

    monkeypatch.setattr(runner, "_run_action", fake_run)
    assert runner.run_action(_fake_skill(), "go", {}, "phone-x (SM-A1)").success
    assert seen == ["phone-x"]

    monkeypatch.setenv("GHOST_DEVICE", "phone-x")
    refused = runner.run_action(_fake_skill(), "go", {}, device_serial='"phone-y (SM-A2)"')
    assert (refused.success, refused.status, refused.skill, refused.action) == (False, "refused", "fake-skill", "go")
    assert refused.error["kind"] == "device_ref"
    assert "Valid device id(s): phone-x." in refused.error["message"]
    assert seen == ["phone-x"]


# Fable S1: a session scope is strict. Any ref outside it is refused, not only rewritten ones.


@pytest.mark.parametrize("variable", ["GHOST_DEVICE", "ANDROID_SERIAL"])
def test_scope_refuses_an_exact_out_of_scope_id(monkeypatch, variable):
    monkeypatch.setenv(variable, "phone-x")
    assert resolve_device_ref("phone-x") == "phone-x"  # in-scope exact id unchanged
    assert resolve_device_ref("") == ""  # caller default is still the scope
    for other in ("phone-y", "fake:demo", "ios:fake-udid"):
        with pytest.raises(DeviceRefError) as exc:
            resolve_device_ref(other)
        assert "outside this session's device scope" in str(exc.value)
        assert 'Valid device id(s): phone-x. Pass only the id, e.g. device="phone-x".' in str(exc.value)


def test_no_scope_exact_ids_are_unchanged(monkeypatch):
    monkeypatch.setattr(device, "list_connected", lambda: pytest.fail("unscoped verbatim ids need no adb probe"))
    for ref in ("phone-y", "fake:demo", "never-connected-9"):
        assert resolve_device_ref(ref) == ref


def test_mcp_tool_refuses_exact_out_of_scope_id(monkeypatch):
    monkeypatch.setenv("GHOST_DEVICE", "phone-x")
    seen = _record_mcp_device(monkeypatch)
    result = mcp_server.press_back("phone-y")
    assert seen == []
    assert result.startswith("Error: device 'phone-y' is outside this session's device scope")
    asyncio.run(mcp_server.mcp.call_tool("press_back", {"device": "phone-x"}))
    assert seen == ["phone-x"]


def test_agent_tool_refuses_exact_out_of_scope_id(monkeypatch):
    monkeypatch.setenv("ANDROID_SERIAL", "phone-x")
    seen = []
    monkeypatch.setattr(agent_tools, "_execute_tool_inner", lambda name, args: seen.append(args["device"]) or "ok")
    result = agent_tools.execute_tool("get_phone_state", {"device": "phone-y"})
    assert result.startswith("Error: device 'phone-y' is outside this session's device scope")
    assert seen == []
    assert agent_tools.execute_tool("get_phone_state", {"device": "phone-x"}) == "ok"
    assert seen == ["phone-x"]


def test_run_action_refuses_exact_out_of_scope_id(monkeypatch):
    seen = []

    def fake_run(skill, name, supplied, device_serial, trace, **options):
        seen.append(device_serial)
        return runner.RunResult(success=True, skill=skill.name, action=name)

    monkeypatch.setattr(runner, "_run_action", fake_run)
    monkeypatch.setenv("GHOST_DEVICE", "phone-x")
    refused = runner.run_action(_fake_skill(), "go", {}, device_serial="phone-y")
    assert (refused.success, refused.status) == (False, "refused")
    assert refused.error["kind"] == "device_ref"
    assert "Valid device id(s): phone-x." in refused.error["message"]
    assert seen == []
    assert runner.run_action(_fake_skill(), "go", {}, device_serial="phone-x").success
    assert seen == ["phone-x"]
