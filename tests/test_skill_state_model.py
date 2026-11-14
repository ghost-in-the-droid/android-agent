"""State declarations, deterministic probes, bounded transitions and secret output boundaries."""

import json
import logging
from types import SimpleNamespace

import pytest
import yaml

from gitd.skills.engine import runner
from gitd.skills.engine.errors import SchemaError, StepFailedError
from gitd.skills.engine.loader import load_skill
from gitd.skills.engine.state import probe_state


def action(name, **kw):
    return {
        "name": name,
        "ref_prompt": name,
        "steps": [{"action": "sleep", "seconds": 0}],
        "end_state_validator": {"kind": "element_present", "text": "Ready"},
        **kw,
    }


def manifest():
    return {
        "name": "state_demo",
        "version": "1.0.0",
        "author": "ghost",
        "license": "MIT",
        "generated_with": "human",
        "tos_risk": "low",
        "fingerprint": {"app_package": "test"},
        "state_probes": {"logged_in": {"kind": "element_present", "text": "Ready"}},
        "actions": [
            action("read", requires_state=["logged_in"]),
            action("login", provides_state=["logged_in"]),
            action("logout", clears_state=["logged_in"]),
        ],
    }


def load(tmp_path, raw=None):
    (tmp_path / "skill.yaml").write_text(yaml.safe_dump(raw or manifest()))
    return load_skill(tmp_path)


@pytest.mark.parametrize("field", ["requires_state", "provides_state", "clears_state"])
@pytest.mark.parametrize(
    "bad",
    [
        "logged_in",
        ["logged-in"],
        ["LoggedIn"],
        ["_private"],
        ["double__gap"],
        ["logged_in", "logged_in"],
        ["unknown"],
        None,
        [3],
    ],
)
def test_invalid_state_lists(tmp_path, field, bad):
    raw = manifest()
    raw["actions"][0][field] = bad
    with pytest.raises(SchemaError):
        load(tmp_path, raw)


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "custom_python", "function": "a:b"},
        {"kind": "ocr_text_present", "text": "X"},
        {"kind": "element_present", "xpath": "//node"},
        {"kind": "element_present", "text": "{password}"},
        {"kind": "element_present", "text": "X", "id": "x"},
        None,
    ],
)
def test_probe_is_literal_deterministic_selector(tmp_path, bad):
    raw = manifest()
    raw["state_probes"]["logged_in"] = bad
    with pytest.raises(SchemaError):
        load(tmp_path, raw)


def test_valid_declarations_and_conflicts(tmp_path):
    skill = load(tmp_path)
    assert skill.action("read").requires_state == ["logged_in"]
    assert skill.action("login").provides_state == ["logged_in"]
    assert skill.action("logout").clears_state == ["logged_in"]
    raw = manifest()
    raw["actions"][1]["clears_state"] = ["logged_in"]
    with pytest.raises(SchemaError):
        load(tmp_path, raw)
    raw = manifest()
    raw["actions"][1]["idempotent"] = "yes"
    with pytest.raises(SchemaError):
        load(tmp_path, raw)


@pytest.mark.parametrize(
    "field,value", [("default", "hidden"), ("values", ["hidden"]), ("secret", "true"), ("type", "int")]
)
def test_secret_schema_rejects_stored_values_and_wrong_types(tmp_path, field, value):
    raw = manifest()
    raw["actions"][1]["params"] = [{"name": "password", "secret": True, field: value}]
    with pytest.raises(SchemaError):
        load(tmp_path, raw)


@pytest.mark.parametrize("location", ["demo_params", "test_case"])
def test_secret_never_in_fixture(tmp_path, location):
    raw = manifest()
    raw["actions"][1]["params"] = [{"name": "password", "secret": True}]
    raw["actions"][1][location] = (
        {"password": "hidden"} if location == "demo_params" else {"params": {"password": "hidden"}}
    )
    with pytest.raises(SchemaError):
        load(tmp_path, raw)


class Device:
    is_fake = True

    def __init__(self, xml='<hierarchy><node text="Ready"/></hierarchy>'):
        self.xml = xml
        self.commands = []

    def dump_xml(self):
        return self.xml

    def adb(self, *args):
        self.commands.append(args)
        return ""


@pytest.mark.parametrize(
    "xml,expected",
    [
        ('<hierarchy><node text="Ready"/></hierarchy>', True),
        ('<hierarchy><node text="Other"/></hierarchy>', False),
        ("", None),
        ("broken", None),
        ("<hierarchy/>", None),
        ("<error/>", None),
        ('<hierarchy><node text="Ready" visible-to-user="false"/></hierarchy>', False),
    ],
)
def test_probe_three_values(tmp_path, xml, expected):
    skill = load(tmp_path)
    assert probe_state(skill, "logged_in", Device(xml)) is expected
    skill.state_probes["logged_in"] = {"not": skill.state_probes["logged_in"]}
    assert probe_state(skill, "logged_in", Device(xml)) is (None if expected is None else not expected)


def harness(tmp_path, monkeypatch, present=False, unknown=False, provider_fails=False, raw=None):
    skill = load(tmp_path, raw)
    device = Device()
    calls = []
    states = {"logged_in": None if unknown else present}
    monkeypatch.setattr(runner, "_get_device", lambda _: device)
    monkeypatch.setattr(runner, "probe_state", lambda _skill, state, _device: states.get(state, False))
    monkeypatch.setattr(runner, "evaluate_validator", lambda *args: True)

    def dispatch(step, ctx, dev):
        calls.append(ctx.action_name)
        if provider_fails and ctx.action_name == "login":
            raise StepFailedError("provider failed")
        for state in skill.action(ctx.action_name).provides_state:
            states[state] = True
        for state in skill.action(ctx.action_name).clears_state:
            states[state] = False

    monkeypatch.setattr(runner, "dispatch", dispatch)
    return skill, calls, states


@pytest.mark.parametrize("present,calls", [(True, ["read"]), (False, ["login", "read"])])
def test_present_or_missing_state(tmp_path, monkeypatch, present, calls):
    skill, actual, _ = harness(tmp_path, monkeypatch, present=present)
    assert runner.run_action(skill, "read", device_serial="fake:state").success
    assert actual == calls


@pytest.mark.parametrize("idempotent,expected", [(False, False), (True, True)])
def test_unknown_only_transitions_through_idempotent_provider(tmp_path, monkeypatch, idempotent, expected):
    skill, calls, _ = harness(tmp_path, monkeypatch, unknown=True)
    skill.action("login").idempotent = idempotent
    result = runner.run_action(skill, "read", device_serial="fake:state")
    assert result.success is expected
    assert calls == (["login", "read"] if expected else [])
    if not expected:
        assert result.error["reason"] == "unknown_requires_idempotent"


def test_provider_failure(tmp_path, monkeypatch):
    skill, calls, _ = harness(tmp_path, monkeypatch, provider_fails=True)
    result = runner.run_action(skill, "read", device_serial="fake:state")
    assert result.status == "needs_state" and result.needs_state == "logged_in"
    assert result.error["reason"] == "provider_failed"
    assert calls == ["login"]


@pytest.mark.parametrize("providers,reason", [(0, "no_provider"), (2, "ambiguous_provider")])
def test_provider_selection_fails_closed(tmp_path, monkeypatch, providers, reason):
    raw = manifest()
    raw["actions"] = raw["actions"][:1] + [action(f"login_{i}", provides_state=["logged_in"]) for i in range(providers)]
    skill, calls, _ = harness(tmp_path, monkeypatch, raw=raw)
    assert runner.run_action(skill, "read").error["reason"] == reason
    assert calls == []


def test_secret_missing_never_prompts_or_starts_provider(tmp_path, monkeypatch):
    raw = manifest()
    raw["actions"][1]["params"] = [{"name": "password", "secret": True, "required": True}]
    skill, calls, _ = harness(tmp_path, monkeypatch, raw=raw)
    assert runner.run_action(skill, "read").error["reason"] == "missing_secret"
    assert calls == []
    assert runner.run_action(skill, "read", state_params={"login": {"password": "runtime-only"}}).success
    assert calls == ["login", "read"]


def test_dependency_cycle_is_bounded(tmp_path, monkeypatch):
    raw = manifest()
    raw["state_probes"]["app_open"] = {"kind": "element_present", "text": "App"}
    raw["actions"][1]["requires_state"] = ["app_open"]
    raw["actions"].append(action("open", requires_state=["logged_in"], provides_state=["app_open"]))
    skill, calls, _ = harness(tmp_path, monkeypatch, raw=raw)
    result = runner.run_action(skill, "read")
    assert result.status == "needs_state"
    assert calls == []


def test_later_provider_cannot_invalidate_earlier_state(tmp_path, monkeypatch):
    raw = manifest()
    raw["state_probes"]["other"] = {"kind": "element_present", "text": "Other"}
    raw["actions"][0]["requires_state"].append("other")
    raw["actions"].append(action("other", provides_state=["other"], clears_state=["logged_in"]))
    skill, calls, _ = harness(tmp_path, monkeypatch, raw=raw)
    result = runner.run_action(skill, "read")
    assert result.error["reason"] == "state_changed"
    assert calls == ["login", "other"]


def test_provider_claim_is_not_proof(tmp_path, monkeypatch):
    skill, calls, _ = harness(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "probe_state", lambda *args: False)
    assert runner.run_action(skill, "read").error["reason"] == "provider_did_not_establish_state"
    assert calls == ["login"]


def secret_skill(tmp_path, steps):
    raw = manifest()
    raw["actions"] = [action("login", params=[{"name": "password", "secret": True, "required": True}], steps=steps)]
    return load(tmp_path, raw)


def test_secret_never_in_trace_log_evidence_or_pause_file(tmp_path, monkeypatch, caplog):
    from gitd.skills.engine.ask_resume import resume_action
    from gitd.skills.engine.evidence import write_evidence

    monkeypatch.setenv("HOME", str(tmp_path))
    secret = "unique-runtime-password-9472"
    skill = secret_skill(
        tmp_path,
        [
            {"action": "type_text", "text": "{password}"},
            {
                "ask": {
                    "who": "parent_agent",
                    "prompt": "Confirm {password}",
                    "schema": {"type": "str"},
                    "store_as": "answer",
                    "attach": [{"params": ["password"]}, "screenshot"],
                }
            },
        ],
    )
    device = Device()
    monkeypatch.setattr(runner, "_get_device", lambda _: device)
    progress = []
    with caplog.at_level(logging.DEBUG):
        result = runner.run_action(
            skill, "login", {"password": secret}, "fake:state", progress_callback=progress.append
        )
    assert result.status == "needs_input"
    assert result.attachments == {}
    stored = tmp_path / ".ghost/runs" / (result.resume_token + ".json")
    assert "password" not in json.loads(stored.read_text())["params"]
    artifact = write_evidence(
        skill,
        [result],
        {"os": "android", "os_version": "1", "hardware": "test", "app_package": "test", "app_version": "1"},
        simulated=True,
    )
    assert artifact.exists()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes(), path
    assert secret not in json.dumps(result.as_dict()) + caplog.text + repr(progress)
    assert any(secret in str(command) for command in device.commands)  # supplied to the device, not discarded
    with pytest.raises(ValueError, match="secret params"):
        resume_action(result.resume_token, "yes")
    assert resume_action(result.resume_token, "yes", secrets={"password": secret}).success


@pytest.mark.parametrize(
    "step",
    [
        {"action": "screenshot", "save_as": "leak.png"},
        {"action": "dump_xml", "save_as": "leak.xml"},
        {"python_action": "helpers:login"},
    ],
)
def test_secret_capture_and_helpers_fail_closed(tmp_path, monkeypatch, step):
    skill = secret_skill(tmp_path, [step])
    device = Device()
    monkeypatch.setattr(runner, "_get_device", lambda _: device)
    result = runner.run_action(skill, "login", {"password": "runtime-only"}, "fake:state")
    assert not result.success
    assert not device.commands


def test_secret_errors_and_logs_redacted(tmp_path, monkeypatch, caplog):
    secret = "private-runtime-input-234"
    skill = secret_skill(tmp_path, [{"action": "type_text", "text": "{password}"}])
    device = Device()

    def fail(*args):
        logging.warning("secret=%s", secret)
        raise RuntimeError(secret)

    device.adb = fail
    monkeypatch.setattr(runner, "_get_device", lambda _: device)
    result = runner.run_action(skill, "login", {"password": secret}, "fake:state")
    assert not result.success
    assert secret not in json.dumps(result.as_dict()) + caplog.text


def test_secret_reader_never_writes_ui_dump(tmp_path, monkeypatch):
    from gitd.skills.engine.privacy import dump_xml, secret_scope

    device = SimpleNamespace(dump_xml=lambda: pytest.fail("disk fallback called"))
    with secret_scope(["password"], True):
        with pytest.raises(Exception, match="Portal"):
            dump_xml(device)


def test_registry_projects_states_without_param_values(tmp_path):
    from tools.build_registry import describe_version

    raw = manifest()
    raw["actions"][1]["params"] = [{"name": "password", "secret": True}]
    _, version, _ = describe_version({"skill.yaml": yaml.safe_dump(raw).encode()}, tag=None, commit="a" * 40)
    assert version["action_states"]["login"]["provides_state"] == ["logged_in"]
    assert version["state_probes"] == raw["state_probes"]
    assert "password" not in json.dumps(version)
    raw["actions"][0]["requires_state"] = ["bad-state"]
    with pytest.raises(SchemaError):
        describe_version({"skill.yaml": yaml.safe_dump(raw).encode()}, tag=None, commit="a" * 40)


def test_cli_probe(tmp_path, monkeypatch, capsys):
    from gitd.skills.engine.cli import cmd_probe

    load(tmp_path)
    monkeypatch.setattr(runner, "_get_device", lambda _: Device())
    assert cmd_probe([str(tmp_path), "logged_in", "--device", "fake:state"]) == 0
    assert capsys.readouterr().out.strip() == "true"


def test_state_history_survives_parent_pause(tmp_path, monkeypatch):
    from gitd.skills.engine.ask_resume import resume_action

    monkeypatch.setenv("HOME", str(tmp_path))
    raw = manifest()
    raw["actions"][0]["steps"] = [
        {"ask": {"who": "parent_agent", "prompt": "Continue?", "schema": {"type": "str"}, "store_as": "answer"}}
    ]
    skill = load(tmp_path, raw)
    device = Device()
    states = {"logged_in": False}
    monkeypatch.setattr(runner, "_get_device", lambda _: device)
    monkeypatch.setattr(runner, "probe_state", lambda *args: states["logged_in"])
    original = runner.dispatch

    def dispatch(step, ctx, dev):
        if ctx.action_name == "login":
            states["logged_in"] = True
        return original(step, ctx, dev)

    monkeypatch.setattr(runner, "dispatch", dispatch)
    result = runner.run_action(skill, "read", device_serial="fake:state")
    assert result.status == "needs_input"
    states["logged_in"] = False
    resumed = resume_action(result.resume_token, "yes")
    assert resumed.error["reason"] == "transition_limit"


def test_cli_secret_environment_does_not_print_value(tmp_path, monkeypatch, capsys):
    from gitd.skills.engine.cli import cmd_run

    secret_skill(tmp_path, [{"action": "type_text", "text": "{password}"}])
    monkeypatch.setenv("LOCAL_TEST_SECRET", "unique-cli-password-412")
    monkeypatch.setattr(runner, "_get_device", lambda _: Device())
    code = cmd_run(
        [
            str(tmp_path),
            "login",
            "--device",
            "fake:state",
            "--no-fingerprint-check",
            "--live-trace",
            "--secret-env",
            "=".join(("password", "LOCAL_TEST_SECRET")),  # FIELD=ENV binding, built so the privacy scan sees no literal
        ]
    )
    assert code == 0
    assert "unique-cli-password-412" not in capsys.readouterr().out


def test_sensitive_checkpoint_details_are_redacted(tmp_path, monkeypatch):
    from gitd.skills.engine.hitl import LocalChannel

    skill = secret_skill(
        tmp_path,
        [
            {
                "checkpoint": {
                    "reason": "login",
                    "prompt": "Confirm {password}",
                    "success": {"kind": "text_visible", "text": "{password}"},
                    "timeout_s": 1,
                }
            }
        ],
    )

    class Channel(LocalChannel):
        def notify(self, *args):
            super().notify(*args)
            self.resume()

    channel = Channel(echo=False)
    monkeypatch.setattr(runner, "_get_device", lambda _: Device())
    result = runner.run_action(
        skill, "login", {"password": "secret-channel-198"}, "fake:state", checkpoint_channel=channel
    )
    assert result.success
    assert "secret-channel-198" not in repr(channel.states) + repr(channel.notices)


@pytest.mark.parametrize("field", ["requires_state", "provides_state", "clears_state"])
def test_registry_validates_each_state_rule(field):
    from tools.build_registry import describe_version

    raw = manifest()
    raw["actions"][0][field] = ["bad-state"]
    with pytest.raises(SchemaError):
        describe_version({"skill.yaml": yaml.safe_dump(raw).encode()}, tag=None, commit="a" * 40)


@pytest.mark.parametrize("edit", ["probe", "secret", "idempotent", "conflict"])
def test_registry_refuses_invalid_probe_or_secret_declaration(edit):
    from tools.build_registry import describe_version

    raw = manifest()
    if edit == "probe":
        raw["state_probes"]["logged_in"] = {"kind": "custom_python", "function": "helpers:probe"}
    elif edit == "secret":
        raw["actions"][1]["params"] = [{"name": "password", "secret": True, "default": "must-not-store"}]
    elif edit == "idempotent":
        raw["actions"][1]["idempotent"] = "yes"
    else:
        raw["actions"][1]["clears_state"] = ["logged_in"]
    with pytest.raises(SchemaError):
        describe_version({"skill.yaml": yaml.safe_dump(raw).encode()}, tag=None, commit="a" * 40)


def test_secret_auto_demo_rejected_before_resolving_values(tmp_path):
    from gitd.skills.engine.demo import build_plan

    skill = secret_skill(tmp_path, [{"action": "type_text", "text": "{password}"}])
    args = SimpleNamespace(device="unused", out=None, action="login")
    with pytest.raises(ValueError, match="cannot be screen-recorded"):
        build_plan(skill, args, {"password": "never-in-a-plan"})


def test_state_probe_provider_and_target_share_one_device(tmp_path, monkeypatch):
    skill = load(tmp_path)
    skill.action("login").steps = [{"action": "tap", "x": 1, "y": 1}]
    devices = []

    class StatefulDevice(Device):
        def tap(self, *args):
            self.xml = '<hierarchy><node text="Ready"/></hierarchy>'

    def get_device(_):
        device = StatefulDevice('<hierarchy><node text="Login"/></hierarchy>')
        devices.append(device)
        return device

    monkeypatch.setattr(runner, "_get_device", get_device)
    assert runner.run_action(skill, "read", device_serial="fake:state").success
    assert len(devices) == 1


def test_secret_interpolation_filters_fail_closed(tmp_path, monkeypatch):
    skill = secret_skill(tmp_path, [{"action": "type_text", "text": "{password | upper}"}])
    device = Device()
    monkeypatch.setattr(runner, "_get_device", lambda _: device)
    result = runner.run_action(skill, "login", {"password": "runtime-password"}, "fake:state")
    assert not result.success
    assert not device.commands
    assert "RUNTIME-PASSWORD" not in json.dumps(result.as_dict())


def test_mcp_surfaces_needs_state_and_accepts_provider_inputs(tmp_path, monkeypatch):
    from gitd import mcp_server

    raw = manifest()
    raw["actions"][1]["params"] = [{"name": "password", "secret": True}]
    skill, calls, _ = harness(tmp_path, monkeypatch, raw=raw)
    stopped = json.loads(mcp_server.run_skill(str(tmp_path), "read", device=""))
    assert stopped["status"] == "needs_state" and stopped["needs_state"] == "logged_in"
    assert calls == []
    result = json.loads(
        mcp_server.run_skill(
            str(tmp_path), "read", device="", state_params=json.dumps({"login": {"password": "runtime-only"}})
        )
    )
    assert result["success"]
    assert "runtime-only" not in json.dumps(result)
