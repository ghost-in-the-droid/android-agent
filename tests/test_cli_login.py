"""Tests for `android-agent login` (Claude subscription sign-in, no API key)."""

import json
import types

import gitd.cli as cli


def _write_creds(home, payload):
    d = home / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / ".credentials.json").write_text(json.dumps(payload))


# ── _claude_auth_state (offline, never reads token values) ───────────────────


def test_auth_state_not_installed(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda n: None)
    assert cli._claude_auth_state() == "not_installed"


def test_auth_state_logged_out(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.shutil, "which", lambda n: "/usr/bin/claude")
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)  # no creds file
    assert cli._claude_auth_state() == "logged_out"


def test_auth_state_logged_in(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.shutil, "which", lambda n: "/usr/bin/claude")
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    _write_creds(tmp_path, {"claudeAiOauth": {"accessToken": "SECRET-should-not-be-read"}})
    assert cli._claude_auth_state() == "logged_in"


# ── cmd_login ────────────────────────────────────────────────────────────────


def test_login_not_installed_guides_and_fails(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_claude_auth_state", lambda: "not_installed")
    rc = cli.cmd_login(types.SimpleNamespace(relogin=False))
    assert rc == 1
    assert "not installed" in capsys.readouterr().out.lower()


def test_login_already_signed_in_records_default(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_claude_auth_state", lambda: "logged_in")
    recorded = {}
    monkeypatch.setattr(cli, "_record_default_provider", lambda p: recorded.update(p=p))
    rc = cli.cmd_login(types.SimpleNamespace(relogin=False))
    assert rc == 0
    assert recorded["p"] == "claude-code"
    assert "signed in" in capsys.readouterr().out.lower()


def test_login_delegates_to_claude_auth_login_when_logged_out(monkeypatch):
    states = iter(["logged_out", "logged_in"])  # before login, then after
    monkeypatch.setattr(cli, "_claude_auth_state", lambda: next(states))
    ran = {}
    monkeypatch.setattr(
        cli.subprocess, "run", lambda cmd, **k: ran.update(cmd=cmd) or types.SimpleNamespace(returncode=0)
    )
    monkeypatch.setattr(cli, "_record_default_provider", lambda p: None)
    rc = cli.cmd_login(types.SimpleNamespace(relogin=False))
    assert rc == 0
    assert ran["cmd"] == ["claude", "auth", "login"]  # delegates to the sanctioned flow


def test_login_aborts_if_claude_login_fails(monkeypatch):
    monkeypatch.setattr(cli, "_claude_auth_state", lambda: "logged_out")
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **k: types.SimpleNamespace(returncode=1))
    rc = cli.cmd_login(types.SimpleNamespace(relogin=False))
    assert rc == 1


def test_record_default_provider_upserts_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cli._record_default_provider("claude-code")
    assert "DEFAULT_PROVIDER=claude-code" in (tmp_path / ".env").read_text()

    # upsert (not duplicate) when the key already exists, preserving other lines
    (tmp_path / ".env").write_text("FOO=bar\nDEFAULT_PROVIDER=old\n")
    cli._record_default_provider("claude-code")
    env = (tmp_path / ".env").read_text()
    assert env.count("DEFAULT_PROVIDER=") == 1
    assert "DEFAULT_PROVIDER=claude-code" in env and "FOO=bar" in env


# ── doctor subscription check + create_session default ───────────────────────


def test_doctor_subscription_ok_when_signed_in(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(cli, "_claude_auth_state", lambda: "logged_in")
    monkeypatch.setattr(cli, "_port_in_use", lambda *a, **k: False)
    monkeypatch.setattr("gitd.bots.common.adb.list_connected", lambda: [])
    sub = next(c for c in cli.collect_doctor_checks() if c["name"] == "Claude subscription")
    assert sub["status"] == "ok"


def test_doctor_subscription_warns_when_signed_out(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(cli, "_claude_auth_state", lambda: "logged_out")
    monkeypatch.setattr(cli, "_port_in_use", lambda *a, **k: False)
    monkeypatch.setattr("gitd.bots.common.adb.list_connected", lambda: [])
    sub = next(c for c in cli.collect_doctor_checks() if c["name"] == "Claude subscription")
    assert sub["status"] == "warn"
    assert "login" in sub["hint"]


def test_create_session_honors_default_provider(monkeypatch):
    from gitd.config import settings
    from gitd.services import agent_chat

    monkeypatch.setattr(settings, "default_provider", "claude-code")
    assert agent_chat.create_session(device="d").provider == "claude-code"  # no provider → default
    assert agent_chat.create_session(device="d", provider="ollama").provider == "ollama"  # explicit wins
