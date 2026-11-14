"""Regressions for helper return data and schema-directed CLI parameter types."""

import pytest
import yaml

from gitd.bots.common.adb import input_text_arg
from gitd.skills.engine import cli, load_skill, run_action
from gitd.skills.engine.loader import Param
from gitd.skills.engine.runner import _resolve_params


@pytest.fixture
def example(tmp_path, monkeypatch):
    class Device:
        serial = "mock"

        def __init__(self):
            self.calls = []

        def dump_xml(self):
            return '<hierarchy><node text="Ready" /></hierarchy>'

        def dismiss_popups(self, **kwargs):
            return False

        def adb(self, *args):
            self.calls.append(args)
            return ""

    device = Device()
    monkeypatch.setattr("gitd.skills.engine.runner._get_device", lambda serial: device)
    raw = {
        "name": "contracts", "author": "example", "version": "1.0.0",
        "license": "MIT", "generated_with": "test", "tos_risk": "low", "skill_class": "hard",
        "fingerprint": {"os": "android", "app_package": "com.example.contracts"},
        "actions": [{
            "name": "write", "ref_prompt": "Write a value",
            "params": [{"name": "value", "type": "str", "required": True}],
            "steps": [{"action": "type_text", "text": "{value}"}],
            "end_state_validator": {"kind": "text_visible", "text": "Ready"},
        }],
    }
    (tmp_path / "README.md").write_text("Contract test fixture.\n")
    (tmp_path / "SOFT.md").write_text("Mock device only.\n")

    def write():
        (tmp_path / "skill.yaml").write_text(yaml.safe_dump(raw))
        return load_skill(tmp_path)

    return tmp_path, raw, device, write


@pytest.mark.parametrize("expression", [
    "{'echo': '5', 'count': 2}",
    "{'data': {'echo': '5', 'count': 2}}",
    "{'success': True, 'data': {'echo': '5', 'count': 2}}",
    "ActionResult(success=True, data={'echo': '5', 'count': 2})",
])
def test_python_action_data_reaches_result_and_later_steps(example, expression):
    path, raw, device, write = example
    (path / "helpers.py").write_text(
        "from gitd.skills.base import ActionResult\n"
        f"def produce(device, params, context):\n    return {expression}\n"
    )
    action = raw["actions"][0]
    action["steps"] = [
        {"python_action": "helpers:produce"},
        {"action": "type_text", "text": "{context.echo}"},
    ]
    result = run_action(write(), "write", {"value": "unused"}, device_serial="mock")
    assert result.success, result.error
    assert result.data == {"echo": "5", "count": 2}
    assert ("shell", "input", "text", input_text_arg("5")) in device.calls


@pytest.mark.parametrize("expression", [
    "{'success': False, 'error': 'refused'}",
    "ActionResult(success=False, error='refused')",
])
def test_python_action_failure_envelopes_still_fail(example, expression):
    path, raw, device, write = example
    (path / "helpers.py").write_text(
        "from gitd.skills.base import ActionResult\n"
        f"def produce(device, params, context):\n    return {expression}\n"
    )
    raw["actions"][0]["steps"] = [{"python_action": "helpers:produce"}]
    result = run_action(write(), "write", {"value": "unused"}, device_serial="mock")
    assert not result.success and "refused" in result.error["message"]


@pytest.mark.parametrize("command", ["test", "run"])
@pytest.mark.parametrize("value", ["5", "005", "false", '["x"]'])
def test_cli_string_params_reach_type_text_losslessly(example, command, value):
    path, raw, device, write = example
    write()
    args = [command, str(path)]
    args += ["--live", "--action", "write"] if command == "test" else ["write", "--no-fingerprint-check"]
    assert cli.main(args + ["--device", "mock", "--param", "value=" + value]) == 0
    assert ("shell", "input", "text", input_text_arg(value)) in device.calls


@pytest.mark.parametrize("kind,raw,expected", [
    ("str", "005", "005"),
    ("str", "true", "true"),
    ("int", "5", 5),
    ("float", "-2.5", -2.5),
    ("bool", "false", False),
    ("list[str]", '["a", 5]', ["a", "5"]),
    ("path", "005", "005"),
])
def test_cli_values_are_coerced_by_declaration(kind, raw, expected):
    parsed = cli._parse_params(["value=" + raw])
    actual = _resolve_params([Param(name="value", type=kind)], parsed, "s", "a")["value"]
    assert actual == expected and type(actual) is type(expected)


@pytest.mark.parametrize("value", [5, True])
def test_string_declaration_normalizes_typed_api_values_and_defaults(value):
    defs = [Param(name="value", type="str", default=value)]
    assert _resolve_params(defs, {"value": value}, "s", "a")["value"] == str(value)
    assert _resolve_params(defs, {}, "s", "a")["value"] == str(value)


@pytest.mark.parametrize("choices,raw,expected", [
    ([1, 2], "2", 2),
    ([False, True], "false", False),
    (["2", 2], "2", "2"),
])
def test_cli_enum_values_follow_declared_choices(choices, raw, expected):
    actual = _resolve_params(
        [Param(name="value", type="enum", values=choices)],
        cli._parse_params(["value=" + raw]), "s", "a",
    )["value"]
    assert actual == expected and type(actual) is type(expected)


@pytest.mark.parametrize("expression,warn,success,expected", [
    ("{'success': True, 'count': 3}", True, True, {}),
    ("{'success': False, 'error': 'refused', 'count': 3}", True, False, {}),
    ("{'data': {'count': 3}, 'ignored': 'private-value'}", True, True, {'count': 3}),
    ("{'success': True, 'data': {'count': 3}}", False, True, {'count': 3}),
    ("{'count': 3}", False, True, {'count': 3}),
])
def test_envelope_sibling_warning_preserves_return_contract(example, caplog, expression, warn, success, expected):
    path, raw, device, write = example
    (path / "helpers.py").write_text(
        f"def produce(device, params, context):\n    return {expression}\n"
    )
    raw["actions"][0]["steps"] = [{"python_action": "helpers:produce"}]
    result = run_action(write(), "write", {"value": "unused"}, device_serial="mock")
    assert result.success is success
    if success:
        assert result.data == expected
    warnings = [r.message for r in caplog.records if 'ignored sibling keys' in r.message]
    assert bool(warnings) is warn
    assert 'private-value' not in caplog.text
    if warn:
        assert 'put payload fields inside data' in warnings[0]


@pytest.mark.parametrize("choices", [["yes", "no"], [None, "yes"]])
def test_cli_null_enum_text_is_not_coerced_to_absence(choices):
    from gitd.skills.engine.errors import ParamError
    with pytest.raises(ParamError, match="'null' not in"):
        _resolve_params([Param(name="value", type="enum", values=choices, required=True)],
                        {"value": "null"}, "s", "a")


def test_literal_null_enum_and_optional_absence_remain_distinct():
    assert _resolve_params([Param(name="value", type="enum", values=["null", "yes"])],
                           {"value": "null"}, "s", "a") == {"value": "null"}
    assert _resolve_params([Param(name="value", type="enum", values=["yes"])],
                           {}, "s", "a") == {"value": None}
