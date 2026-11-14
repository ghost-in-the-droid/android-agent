from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest
from gitd.ghostcli import config, telemetry
from gitd.ghostcli.telemetry_transport import send_run
from tools.aggregate_telemetry import aggregate

ID = '12345678-1234-4234-8234-123456789012'
CATALOG = {'ghost/google_maps': ['25.0.0']}


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('GHOST_CONFIG_DIR', str(tmp_path))
    monkeypatch.delenv('DO_NOT_TRACK', raising=False)
    monkeypatch.delenv('GHOST_TELEMETRY_DEBUG', raising=False)
    events = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            events.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(204)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('GHOST_TELEMETRY_ENDPOINT', f'http://127.0.0.1:{server.server_port}/run')
    yield events
    server.shutdown()
    server.server_close()
    thread.join()


def send():
    send_run(SimpleNamespace(author='ghost', name='google_maps'), SimpleNamespace(success=True, data={'private':'secret'}), {'app_version':'25.0.0', 'os':'android', 'hardware':'secret'})


def test_consent_transport_and_debug(endpoint, monkeypatch, capsys):
    send()
    assert endpoint == []
    telemetry.main(['on'])
    send()
    assert len(endpoint) == 1
    assert set(endpoint[0]) == {'schema_version','skill','app_version','outcome','os','backend','install_id'}
    assert 'secret' not in json.dumps(endpoint)
    monkeypatch.setenv('DO_NOT_TRACK','1')
    send()
    monkeypatch.delenv('DO_NOT_TRACK')
    monkeypatch.setenv('GHOST_TELEMETRY_DEBUG','1')
    send()
    assert 'Telemetry debug:' in capsys.readouterr().out
    assert len(endpoint) == 1
    monkeypatch.delenv('GHOST_TELEMETRY_DEBUG')
    monkeypatch.delenv('GHOST_TELEMETRY_ENDPOINT')
    send()
    telemetry.main(['off'])
    send()
    assert len(endpoint) == 1


def event(**changes):
    return json.dumps(dict(schema_version=1,skill='ghost/google_maps',app_version='25.0.0',outcome='passed',os='android',backend='device',install_id=ID,timestamp='2026-10-05T00:00:00Z') | changes)


def test_aggregate_windows_and_simulations():
    now = datetime(2026,10,5,tzinfo=timezone.utc)
    rows = [event(),event(outcome='failed'),event(timestamp='2025-01-01T00:00:00Z'),event(backend='fake')]
    assert aggregate(rows, CATALOG, now=now) == {'ghost/google_maps':dict(passed=2,total=3,passed_90d=1,total_90d=2)}


@pytest.mark.parametrize('changes',[{'ip':'127.0.0.1'},{'text':'secret'},{'skill':'127.0.0.1'},{'outcome':'secret'},{'app_version':'unknown'},{'timestamp':'2099-01-01T00:00:00Z'},{'install_id':'bad'},{'schema_version':True}])
def test_aggregate_rejects_unknown_and_private_fields(changes):
    with pytest.raises(ValueError, match='line 1'):
        aggregate([event(**changes)], CATALOG)


def test_worker_node():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', str(root/'infra/telemetry-worker/test.mjs')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_record_cli_posts_only_recorded_runs(endpoint, monkeypatch, tmp_path):
    from gitd.skills.engine import cli, evidence
    telemetry.main(['on'])
    skill = SimpleNamespace(author='ghost', name='google_maps')
    result = SimpleNamespace(success=True, data={}, duration_ms=1)
    monkeypatch.setattr(cli, 'load_skill', lambda path: skill)
    monkeypatch.setattr(cli, 'run_action', lambda *args, **kwargs: result)
    monkeypatch.setattr(evidence, 'collect_fingerprint', lambda *args: {'app_version':'25.0.0','os':'android'})
    monkeypatch.setattr(evidence, 'write_evidence', lambda *args, **kwargs: tmp_path/'evidence.json')
    args = ['ghost/google_maps', 'search_place', '--device', 'fake:fixture']
    assert cli.cmd_run(args) == 0
    assert endpoint == []
    assert cli.cmd_run(args + ['--record']) == 0
    assert len(endpoint) == 1
    assert endpoint[0]['backend'] == 'fake'
    telemetry.main(['off'])
    assert cli.cmd_run(args + ['--record']) == 0
    assert len(endpoint) == 1


def test_transport_failure_is_nonfatal(endpoint, monkeypatch, capsys):
    telemetry.main(['on'])
    monkeypatch.setattr('gitd.ghostcli.telemetry_transport.build_opener', lambda *args: (_ for _ in ()).throw(OSError('secret')))
    send()
    assert 'Telemetry delivery skipped.' in capsys.readouterr().err
    assert endpoint == []
