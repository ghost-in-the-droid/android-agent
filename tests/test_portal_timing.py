"""The timing harness records aggregates, refuses foreign focus, and validates Portal replies."""
import io
import json
from types import SimpleNamespace

import pytest

from tools.bench import portal_timing as timing


class Demo:
    def foreground_package(self):
        return 'com.example.demo'

    def adb(self, *args):
        return {'ro.product.model': 'DemoModel', 'ro.build.version.release': '16',
                'ro.build.version.sdk': '36'}[args[-1]]


def test_aggregate_output_does_not_retain_node_content(monkeypatch):
    requests = []
    def get(url, timeout):
        requests.append(url)
        data = ({'a11y_tree': {'text': 'SYNTHETIC_PRIVATE_CANARY', 'children': [{}, {}]}}
                if url.endswith('/state') else [{'text': 'SYNTHETIC_PRIVATE_CANARY'}])
        return io.BytesIO(json.dumps({'status': 'success', 'result': json.dumps(data)}).encode())
    monkeypatch.setattr(timing.urllib.request, 'urlopen', get)
    result = timing.measure(Demo(), 12345, 'com.example.demo', samples=2, warmups=1)
    assert len(requests) == 6
    assert result['endpoints']['state']['nodes_min'] == 3
    assert result['endpoints']['elements']['nodes_max'] == 1
    assert 'SYNTHETIC_PRIVATE_CANARY' not in json.dumps(result)
    assert '127.0.0.1' not in json.dumps(result)


def test_foreign_focus_aborts_before_network(monkeypatch):
    device = Demo()
    device.foreground_package = lambda: 'com.example.foreign'
    monkeypatch.setattr(timing.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('must not read'))
    with pytest.raises(RuntimeError, match='not foreground'):
        timing.measure(device, 12345, 'com.example.demo')


@pytest.mark.parametrize('payload', [{'status': 'error'}, {'status': 'success', 'result': '{}'}])
def test_unsuccessful_or_empty_state_is_not_a_latency_success(monkeypatch, payload):
    monkeypatch.setattr(timing.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(json.dumps(payload).encode()))
    with pytest.raises(RuntimeError, match='failed|no tree'):
        timing.measure(Demo(), 12345, 'com.example.demo', samples=1, warmups=0)
