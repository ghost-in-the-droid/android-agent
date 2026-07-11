"""iOS feature gate (#759 STAGE plan): OFF by default, Android path unchanged.

The suite runs with GITD_ENABLE_IOS=1 (tests/conftest.py); these tests
explicitly close the gate to pin the disabled-state contract:

* `ios:` refs raise NotImplementedError from get_device()
* iOS devices disappear from discovery
* plain Android serials are entirely unaffected
"""

import pytest

from gitd.bots.common import device as device_mod
from gitd.bots.common.adb import Device


@pytest.fixture()
def gate_closed(monkeypatch):
    monkeypatch.delenv("GITD_ENABLE_IOS", raising=False)
    monkeypatch.setattr("gitd.config.settings.ios_platform_enabled", False)


@pytest.fixture()
def gate_open(monkeypatch):
    monkeypatch.setenv("GITD_ENABLE_IOS", "1")


def test_gate_closed_by_default_config(gate_closed):
    assert device_mod.ios_enabled() is False


def test_ios_ref_raises_when_disabled(gate_closed):
    with pytest.raises(NotImplementedError, match="iOS support is disabled"):
        device_mod.get_device("ios:0000TEST-0000000000000000")


def test_ios_discovery_empty_when_disabled(gate_closed):
    assert device_mod.ios_refs_from_env() == []
    assert device_mod.ios_refs_from_host() == []
    assert device_mod.list_configured_ios_devices() == []


def test_android_path_unchanged_when_disabled(gate_closed):
    dev = device_mod.get_device("ANDROIDSERIAL123")
    assert isinstance(dev, Device)
    assert device_mod.platform_for_device("ANDROIDSERIAL123") == "android"


def test_env_override_opens_gate(gate_closed, monkeypatch):
    monkeypatch.setenv("GITD_ENABLE_IOS", "1")
    assert device_mod.ios_enabled() is True


def test_settings_flag_opens_gate(gate_closed, monkeypatch):
    monkeypatch.setattr("gitd.config.settings.ios_platform_enabled", True)
    assert device_mod.ios_enabled() is True


def test_execute_tool_surfaces_disabled_error_for_ios_ref(gate_closed):
    from gitd.services.agent_tools import execute_tool

    result = execute_tool("tap", {"device": "ios:0000TEST-0000000000000000", "x": 1, "y": 1})
    assert "iOS support is disabled" in result
