#!/usr/bin/env python3
"""Aggregate validated Worker JSON lines into per-skill quality.runs inputs."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import uuid

FIELDS = {'schema_version', 'skill', 'app_version', 'outcome', 'os', 'backend', 'install_id', 'timestamp'}


def aggregate(lines, catalog, *, now=None):
    now = now or datetime.now(timezone.utc)
    runs = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict) or set(event) != FIELDS:
                raise ValueError('Unexpected fields')
            identity = uuid.UUID(event['install_id'])
            if str(identity) != event['install_id'] or identity.version != 4:
                raise ValueError('Invalid identifier')
            if (type(event['schema_version']) is not int or event['schema_version'] != 1 or
                    not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}/[a-z0-9][a-z0-9_-]{0,63}', event['skill']) or
                    not re.fullmatch(r'[0-9][0-9A-Za-z.+_-]{0,63}', event['app_version']) or
                    re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', event['app_version']) or
                    event['skill'] not in catalog or event['app_version'] not in catalog[event['skill']] or
                    event['outcome'] not in ('passed', 'failed') or event['os'] not in ('android', 'ios') or
                    event['backend'] not in ('device', 'fake')):
                raise ValueError('Invalid category')
            timestamp = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            if timestamp.tzinfo is None or timestamp > now:
                raise ValueError('Invalid timestamp')
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError(f'Invalid telemetry line {number}') from exc
        # Simulations are test signals, not public reliability measurements.
        if event['backend'] == 'fake':
            continue
        counts = runs.setdefault(event['skill'], dict(passed=0, total=0, passed_90d=0, total_90d=0))
        passed = int(event['outcome'] == 'passed')
        counts['total'] += 1
        counts['passed'] += passed
        if timestamp >= now - timedelta(days=90):
            counts['total_90d'] += 1
            counts['passed_90d'] += passed
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jsonl', nargs='+')
    parser.add_argument('--catalog', required=True, help='JSON skill ID to app-version enum mapping')
    args = parser.parse_args()
    with open(args.catalog) as source:
        catalog = json.load(source)
    def lines():
        for path in args.jsonl:
            with open(path) as source:
                yield from source
    print(json.dumps(aggregate(lines(), catalog), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
