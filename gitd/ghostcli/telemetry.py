"""Local opt-in telemetry preference and rotating anonymous identifier."""
from __future__ import annotations

import argparse
import os
import sys
import uuid

from gitd.ghostcli import config


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='ghost telemetry')
    parser.add_argument('state', choices=['on', 'off', 'status'])
    args = parser.parse_args(argv)
    try:
        data = config.load_config()
        preferences = data.setdefault('telemetry', {})
        if args.state in {'on', 'off'}:
            preferences['enabled'] = args.state == 'on'
            if args.state == 'on':
                preferences['install_id'] = str(uuid.uuid4())
            else:
                preferences.pop('install_id', None)
            config.save_config(data)
        enabled = preferences.get('enabled', False) is True
        disabled_by_env = os.environ.get('DO_NOT_TRACK', '').strip() == '1'
        effective = enabled and not disabled_by_env
        print('Telemetry: ' + ('on' if effective else 'off'))
        if enabled and disabled_by_env:
            print('DO_NOT_TRACK=1 overrides the saved on preference.')
        print('Recorded runs send categorical outcomes only when an endpoint is configured.')
        return 0
    except (OSError, ValueError) as exc:
        print(f'Cannot update telemetry preference: {exc}', file=sys.stderr)
        return 1
