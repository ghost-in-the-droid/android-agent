"""Measure Portal snapshot HTTP latency without saving UI content or identifiers.

Run against an already-open public demo app, with a device-specific existing
forward to Portal's port 8080. No installs, launches, taps or recordings occur.
The result contains aggregate timing/size/node counts only. This is end-to-end
HTTP timing, not an isolated measurement of AccessibilityNodeInfo.refresh().
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.request

from gitd.bots.common.adb import Device


def _count_nodes(value):
    if isinstance(value, list):
        return sum(_count_nodes(child) for child in value)
    if not isinstance(value, dict):
        return 0
    return 1 + sum(_count_nodes(child) for child in value.get('children', []))


def measure(device, port: int, package: str, *, samples: int = 20, warmups: int = 3) -> dict:
    if not 1 <= port <= 65535 or not 1 <= samples <= 1000 or not 0 <= warmups <= 100:
        raise ValueError('Invalid port, sample or warmup count')
    if not package or '/' in package:
        raise ValueError('Expected a demo package name')

    def require_demo():
        if device.foreground_package() != package:
            raise RuntimeError('Expected public demo app is not foreground; measurement aborted')

    require_demo()
    result = {
        'model': device.adb('shell', 'getprop', 'ro.product.model'),
        'android_release': device.adb('shell', 'getprop', 'ro.build.version.release'),
        'api_level': int(device.adb('shell', 'getprop', 'ro.build.version.sdk')),
        'demo_package': package, 'samples_per_endpoint': samples, 'warmups_per_endpoint': warmups,
        'method': 'HTTP request/read/JSON decode; foreground checks outside timed interval; no UI content retained',
        'endpoints': {},
    }
    for endpoint in ('state', 'elements'):
        times, sizes, counts = [], [], []
        for index in range(warmups + samples):
            require_demo()
            started = time.perf_counter()
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/{endpoint}', timeout=10) as response:
                raw = response.read()
            payload = json.loads(raw)
            elapsed = (time.perf_counter() - started) * 1000
            require_demo()
            if payload.get('status') != 'success':
                raise RuntimeError('Portal snapshot failed')
            data = payload.get('result')
            if isinstance(data, str):
                data = json.loads(data)
            if endpoint == 'state':
                tree = data.get('a11y_tree') if isinstance(data, dict) else None
                if not tree:
                    raise RuntimeError('Portal returned no tree')
                count = _count_nodes(tree)
            else:
                if not isinstance(data, list):
                    raise RuntimeError('Portal returned no element list')
                count = len(data)
            if index >= warmups:
                times.append(elapsed); sizes.append(len(raw)); counts.append(count)
        ordered = sorted(times)
        result['endpoints'][endpoint] = {
            'min_ms': round(min(times), 3), 'median_ms': round(statistics.median(times), 3),
            'p95_ms': round(ordered[math.ceil(.95 * samples) - 1], 3),
            'max_ms': round(max(times), 3), 'samples_over_1000_ms': sum(t > 1000 for t in times),
            'response_bytes_min': min(sizes), 'response_bytes_max': max(sizes),
            'nodes_min': min(counts), 'nodes_max': max(counts),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--package', required=True)
    parser.add_argument('--samples', type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(measure(Device(args.device), args.port, args.package, samples=args.samples), indent=2))


if __name__ == '__main__':
    main()
