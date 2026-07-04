"""Tests for the `android-agent doctor` / `up` CLI commands."""

import types

import gitd.cli as cli


def _by_name(checks, name):
    return next(c for c in checks if c["name"] == name)


def test_doctor_flags_missing_adb(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)  # nothing on PATH
    monkeypatch.setattr(cli, "_port_in_use", lambda *a, **k: False)
    checks = cli.collect_doctor_checks()

    adb = _by_name(checks, "adb on PATH")
    assert adb["status"] == "fail"
    assert "PATH" in adb["hint"]
    # with no adb, the devices probe is skipped entirely (no traceback)
    assert not any(c["name"] == "adb devices" for c in checks)


def test_doctor_ok_with_devices(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("gitd.bots.common.adb.list_connected", lambda: ["emulator-5554"])
    monkeypatch.setattr(cli, "_port_in_use", lambda *a, **k: False)
    checks = cli.collect_doctor_checks()

    assert _by_name(checks, "adb on PATH")["status"] == "ok"
    assert _by_name(checks, "adb devices")["status"] == "ok"
    assert "emulator-5554" in _by_name(checks, "adb devices")["detail"]


def test_doctor_warns_when_no_devices(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "adb" else None)
    monkeypatch.setattr("gitd.bots.common.adb.list_connected", lambda: [])
    monkeypatch.setattr(cli, "_port_in_use", lambda *a, **k: False)
    checks = cli.collect_doctor_checks()

    dev = _by_name(checks, "adb devices")
    assert dev["status"] == "warn"
    assert dev["hint"]


def test_doctor_warns_when_port_in_use(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("gitd.bots.common.adb.list_connected", lambda: [])
    monkeypatch.setattr(cli, "_port_in_use", lambda *a, **k: True)
    checks = cli.collect_doctor_checks()

    port_check = next(c for c in checks if c["name"].startswith("server port"))
    assert port_check["status"] == "warn"
    assert "in use" in port_check["detail"]


def test_cmd_doctor_exit_code_fails_on_missing_adb(monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli, "_port_in_use", lambda *a, **k: False)
    rc = cli.cmd_doctor(None)
    assert rc == 1
    assert "must be fixed" in capsys.readouterr().out


def test_cmd_doctor_exit_zero_when_only_warnings(monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("gitd.bots.common.adb.list_connected", lambda: [])  # 0 devices → warn
    monkeypatch.setattr(cli, "_port_in_use", lambda *a, **k: False)
    rc = cli.cmd_doctor(None)
    assert rc == 0


def test_cmd_up_honors_host_port_overrides(monkeypatch):
    import uvicorn

    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: captured.update(host=host, port=port))

    rc = cli.cmd_up(types.SimpleNamespace(host="1.2.3.4", port=9999))
    assert rc == 0
    assert captured == {"host": "1.2.3.4", "port": 9999}
