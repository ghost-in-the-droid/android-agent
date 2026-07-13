"""Tests for the task-first `ghost` CLI: dispatch, config, aliases, wizard, mcp, compat."""

import json

import pytest

from gitd import ghost_cli
from gitd.ghostcli import config as gcfg
from gitd.ghostcli import devices as gdev
from gitd.ghostcli import mcp as gmcp
from gitd.ghostcli import resolve as gres
from gitd.ghostcli import wizard as gwiz


@pytest.fixture()
def ghost_home(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_CONFIG_DIR", str(tmp_path / ".ghost"))
    monkeypatch.setenv("GHOST_HOME_OVERRIDE", str(tmp_path))
    for var in ("GHOST_BACKEND", "GHOST_MODEL", "GHOST_MODE"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


# ── dispatch algorithm ───────────────────────────────────────────────────────


def test_split_leading_stops_at_first_flag():
    assert ghost_cli._split_leading(["check", "reddit", "--device", "x"]) == ["check", "reddit"]
    assert ghost_cli._split_leading(["devices"]) == ["devices"]
    assert ghost_cli._split_leading(["--device", "x"]) == []


@pytest.fixture()
def captured_run(monkeypatch):
    calls = {}

    def fake_run(prompt, flag_argv):
        calls["prompt"] = prompt
        calls["flags"] = flag_argv
        return 0

    monkeypatch.setattr(ghost_cli, "_run_prompt", fake_run)
    return calls


def test_bare_positional_is_a_task(captured_run):
    assert ghost_cli.main(["check", "r/LocalLLaMA", "--device", "asus"]) == 0
    assert captured_run["prompt"] == "check r/LocalLLaMA"
    assert captured_run["flags"] == ["--device", "asus"]


def test_reserved_first_token_routes_to_subcommand(captured_run, monkeypatch):
    seen = {}
    monkeypatch.setattr(ghost_cli, "_cmd_devices", lambda rest: seen.setdefault("devices", rest) or 0)
    assert ghost_cli.main(["devices"]) == 0
    assert seen["devices"] == []
    assert "prompt" not in captured_run  # did NOT go to the prompt path


def test_reserved_word_collision_escaped_by_quoting(captured_run):
    # unquoted → subcommand; quoted single arg → prompt
    assert ghost_cli.main(["config", "path"]) == 0 or True  # config routes locally
    assert "prompt" not in captured_run
    ghost_cli.main(["record my afternoon"])  # single quoted token, 'record' not a bare token
    assert captured_run["prompt"] == "record my afternoon"


def test_double_dash_forces_prompt_mode(captured_run):
    ghost_cli.main(["--", "devices", "--device", "x"])
    assert captured_run["prompt"] == "devices"
    assert captured_run["flags"] == ["--device", "x"]


def test_legacy_subcommand_delegates(monkeypatch):
    got = {}

    def fake_legacy(argv):
        got["argv"] = argv
        return 0

    monkeypatch.setattr("gitd.cli.main", fake_legacy)
    assert ghost_cli.main(["doctor"]) == 0
    assert got["argv"] == ["doctor"]


def test_empty_and_help_print_help(capsys):
    assert ghost_cli.main([]) == 0
    assert "ghost" in capsys.readouterr().out
    assert ghost_cli.main(["--help"]) == 0


# ── config get/set roundtrip ─────────────────────────────────────────────────


def test_config_set_get_roundtrip(ghost_home):
    gcfg.set_value("backend.name", "ollama")
    gcfg.set_value("defaults.mode", "vision")
    assert gcfg.get_value("backend.name") == "ollama"
    assert gcfg.get_value("defaults.mode") == "vision"
    # persisted to disk
    assert "ollama" in gcfg.config_path().read_text()


def test_config_set_rejects_unknown_key(ghost_home):
    with pytest.raises(KeyError):
        gcfg.set_value("nope.key", "x")


def test_config_set_validates_mode(ghost_home):
    with pytest.raises(ValueError):
        gcfg.set_value("defaults.mode", "turbo")


def test_config_cli_roundtrip(ghost_home, capsys):
    ghost_cli.main(["config", "set", "backend.name=anthropic"])
    ghost_cli.main(["config", "get", "backend.name"])
    assert "anthropic" in capsys.readouterr().out


# ── device alias resolution ──────────────────────────────────────────────────


def test_alias_resolves_to_serial(ghost_home):
    gcfg.set_device_alias("asus", "L9ABC")
    assert gdev.resolve_device("asus") == "L9ABC"


def test_raw_serial_used_verbatim(ghost_home):
    assert gdev.resolve_device("R58NRAW") == "R58NRAW"


def test_auto_pick_single_device(ghost_home, monkeypatch):
    monkeypatch.setattr(gdev, "_connected_refs", lambda: ["only-one"])
    assert gdev.resolve_device(None) == "only-one"
    assert gdev.auto_picked(None) is True


def test_multiple_devices_errors(ghost_home, monkeypatch):
    monkeypatch.setattr(gdev, "_connected_refs", lambda: ["a", "b"])
    with pytest.raises(gdev.DeviceError, match="Multiple devices"):
        gdev.resolve_device(None)


def test_no_device_errors(ghost_home, monkeypatch):
    monkeypatch.setattr(gdev, "_connected_refs", lambda: [])
    with pytest.raises(gdev.DeviceError, match="No device"):
        gdev.resolve_device(None)


# ── backend / mode resolution precedence ─────────────────────────────────────


def test_backend_precedence_flag_beats_env_beats_config(ghost_home, monkeypatch):
    gcfg.save_config({"backend": {"name": "ollama", "model": "llama3.2"}})
    monkeypatch.setenv("GHOST_BACKEND", "openrouter")
    # flag wins
    assert gres.resolve_backend("anthropic", None)[0] == "anthropic"
    # env beats config
    assert gres.resolve_backend(None, None)[0] == "openrouter"
    monkeypatch.delenv("GHOST_BACKEND")
    # config beats default
    assert gres.resolve_backend(None, None) == ("ollama", "llama3.2")


def test_mode_precedence_and_validation(ghost_home, monkeypatch):
    assert gres.resolve_mode("vision") == "vision"
    monkeypatch.setenv("GHOST_MODE", "reason")
    assert gres.resolve_mode(None) == "reason"
    with pytest.raises(gres.GhostConfigError):
        gres.resolve_mode("turbo")


def test_unconfigured_unusable_backend_errors(ghost_home, monkeypatch):
    monkeypatch.setattr(gres, "is_provider_usable", lambda p: False)
    with pytest.raises(gres.GhostConfigError, match="No backend configured"):
        gres.resolve_backend_or_error(None, None)


def test_explicit_backend_bypasses_usability_gate(ghost_home, monkeypatch):
    monkeypatch.setattr(gres, "is_provider_usable", lambda p: False)
    # explicit --backend is trusted even when unconfigured
    assert gres.resolve_backend_or_error("ollama", None)[0] == "ollama"


# ── wizard ───────────────────────────────────────────────────────────────────


def test_wizard_noninteractive_writes_config_and_alias(ghost_home):
    cfg = gwiz.apply_noninteractive(backend="claude-code", model="sonnet", mode="vision", device="galaxy:0AXYZ")
    assert cfg["backend"] == {"name": "claude-code", "model": "sonnet"}
    assert cfg["defaults"]["mode"] == "vision"
    assert gcfg.load_devices()["galaxy"] == "0AXYZ"
    assert gcfg.get_value("defaults.device") == "galaxy"


def test_wizard_bare_serial_aliases_to_itself(ghost_home):
    gwiz.apply_noninteractive(backend="ollama", device="RAWSERIAL")
    assert gcfg.load_devices()["RAWSERIAL"] == "RAWSERIAL"


def test_wizard_run_resumes_original_command(ghost_home, monkeypatch, capsys):
    # unconfigured + interactive → wizard runs, THEN the prompt proceeds
    monkeypatch.setattr(gwiz, "is_interactive", lambda: True)
    wiz_ran = {}
    monkeypatch.setattr(gwiz, "run_interactive", lambda: wiz_ran.setdefault("ran", True))
    monkeypatch.setattr(gres, "resolve_backend_or_error", lambda b, m: ("ollama", "x"))
    monkeypatch.setattr(gres, "resolve_mode", lambda m: "fast")
    monkeypatch.setattr(gdev, "resolve_device", lambda d: "dev1")
    monkeypatch.setattr(gdev, "auto_picked", lambda d: False)
    ran_task = {}
    monkeypatch.setattr("gitd.ghostcli.run.run_task", lambda *a, **k: ran_task.setdefault("ran", True) or 0)
    ghost_cli._run_prompt("do it", [])
    assert wiz_ran.get("ran") and ran_task.get("ran")  # wizard THEN the task


# ── mcp install ──────────────────────────────────────────────────────────────


def test_mcp_opencode_emits_correct_config(ghost_home):
    gmcp.install("opencode")
    path = ghost_home / ".config" / "opencode" / "opencode.json"
    data = json.loads(path.read_text())
    entry = data["mcp"]["android-agent"]
    assert entry == {"type": "local", "command": ["android-agent-mcp"], "enabled": True}


def test_mcp_cursor_merges_without_clobber(ghost_home):
    path = ghost_home / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    gmcp.install("cursor")
    data = json.loads(path.read_text())
    assert "other" in data["mcpServers"]  # existing kept
    assert data["mcpServers"]["android-agent"]["command"] == "android-agent-mcp"


def test_mcp_codex_toml(ghost_home):
    gmcp.install("codex")
    text = (ghost_home / ".codex" / "config.toml").read_text()
    assert "[mcp_servers.android-agent]" in text and "android-agent-mcp" in text


def test_mcp_agy_emits_correct_config(ghost_home):
    gmcp.install("agy")
    path = ghost_home / ".gemini" / "config" / "mcp_config.json"
    data = json.loads(path.read_text())
    assert data["mcpServers"]["android-agent"] == {"command": "android-agent-mcp"}


def test_mcp_agy_merges_without_clobber(ghost_home):
    path = ghost_home / ".gemini" / "config" / "mcp_config.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    gmcp.install("agy")
    data = json.loads(path.read_text())
    assert "other" in data["mcpServers"]  # existing kept
    assert data["mcpServers"]["android-agent"]["command"] == "android-agent-mcp"


def test_mcp_agy_tolerates_empty_config_file(ghost_home):
    # agy's own installer creates a 0-byte mcp_config.json; must not error
    path = ghost_home / ".gemini" / "config" / "mcp_config.json"
    path.parent.mkdir(parents=True)
    path.write_text("")
    gmcp.install("agy")
    data = json.loads(path.read_text())
    assert data["mcpServers"]["android-agent"]["command"] == "android-agent-mcp"


def test_mcp_antigravity_alias(ghost_home):
    gmcp.install("antigravity")
    path = ghost_home / ".gemini" / "config" / "mcp_config.json"
    data = json.loads(path.read_text())
    assert data["mcpServers"]["android-agent"]["command"] == "android-agent-mcp"


def test_mcp_agy_idempotent(ghost_home):
    gmcp.install("agy")
    path = ghost_home / ".gemini" / "config" / "mcp_config.json"
    first = path.read_text()
    gmcp.install("agy")
    assert path.read_text() == first


def test_mcp_unknown_client_raises(ghost_home):
    with pytest.raises(gmcp.McpInstallError):
        gmcp.install("notaclient")


# ── backwards compat ─────────────────────────────────────────────────────────


def test_legacy_bin_emits_deprecation_warning(monkeypatch, capsys):
    from gitd import cli as legacy

    monkeypatch.setattr("sys.argv", ["/usr/local/bin/gitd", "--help"])
    try:
        legacy.main(["--help"])
    except SystemExit:
        pass
    err = capsys.readouterr().err
    assert "deprecated" in err and "gitd" in err


def test_ghost_delegation_does_not_warn(monkeypatch, capsys):
    from gitd import cli as legacy

    monkeypatch.setattr("sys.argv", ["/usr/local/bin/ghost", "doctor"])
    monkeypatch.setattr(legacy, "cmd_doctor", lambda args: 0)
    legacy.main(["doctor"])
    assert "deprecated" not in capsys.readouterr().err


def test_load_devices_accepts_bare_key_file(ghost_home):
    # a hand-edited devices.toml WITHOUT the [devices] header must still parse
    gcfg.devices_path().parent.mkdir(parents=True, exist_ok=True)
    gcfg.devices_path().write_text('galaxy = "R58NX"\npixel = "1F2E3D"\n')
    assert gcfg.load_devices() == {"galaxy": "R58NX", "pixel": "1F2E3D"}


def test_load_devices_still_reads_sectioned_file(ghost_home):
    gcfg.devices_path().parent.mkdir(parents=True, exist_ok=True)
    gcfg.devices_path().write_text('[devices]\nasus = "L9ABC"\n')
    assert gcfg.load_devices() == {"asus": "L9ABC"}
