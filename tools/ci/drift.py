"""Check Play Store releases and upsert one drift issue per skill."""
import argparse
import json
import os
import re
from pathlib import Path

from tools.ci.common import api, pages


def numeric_version(value):
    if not re.fullmatch(r'\d+(?:\.\d+)*', value):
        raise ValueError(f'Unsupported app version: {value}')
    return tuple(int(v) for v in value.split('.'))


def covered(version, expression):
    """Numeric ranges support comparisons, OR, caret, tilde and wildcards.

    Unknown Play Store versions or ranges are skipped, never guessed.
    """
    if expression.strip() in ('', '*'):
        return True
    current = numeric_version(version)

    def cmp(left, right):
        count = max(len(left), len(right))
        left, right = left + (0,) * (count - len(left)), right + (0,) * (count - len(right))
        return (left > right) - (left < right)

    for alternative in expression.split('||'):
        tokens = re.findall(r'(>=|<=|>|<|=|\^|~)?\s*(\d+(?:\.(?:\d+|[xX*]))*)', alternative)
        remainder = re.sub(r'(>=|<=|>|<|=|\^|~)?\s*\d+(?:\.(?:\d+|[xX*]))*', '', alternative)
        if not tokens or remainder.strip(' ,'):
            raise ValueError(f'Unsupported range: {expression}')
        matches = []
        for operator, expected in tokens:
            parts = expected.split('.')
            if any(p in ('x', 'X', '*') for p in parts):
                first = next(i for i, p in enumerate(parts) if p in ('x', 'X', '*'))
                if operator or any(p not in ('x', 'X', '*') for p in parts[first:]):
                    raise ValueError(f'Unsupported range: {expression}')
                prefix = tuple(int(p) for p in parts[:first])
                matches.append(current[:len(prefix)] == prefix)
                continue
            target = numeric_version(expected)
            comparison = cmp(current, target)
            if operator in ('^', '~'):
                upper = list(target + (0,) * max(0, 3 - len(target)))
                index = min(1, len(target) - 1) if operator == '~' else next((i for i, v in enumerate(upper) if v), len(upper) - 1)
                upper[index] += 1
                upper[index + 1:] = [0] * (len(upper) - index - 1)
                matches.append(comparison >= 0 and cmp(current, tuple(upper)) < 0)
            else:
                matches.append({'': comparison == 0, '=': comparison == 0, '>': comparison > 0,
                                '<': comparison < 0, '>=': comparison >= 0, '<=': comparison <= 0}[operator])
        if all(matches):
            return True
    return False


def drift_candidates(registry, versions):
    result = []
    for ref, skill in sorted(registry.get('skills', {}).items()):
        entry = skill['versions'][skill['latest']]
        fingerprints = entry.get('fingerprint', {})
        if isinstance(fingerprints, dict):
            fingerprints = [fingerprints]
        for fingerprint in fingerprints:
            package = fingerprint.get('app_package')
            version = versions.get(package)
            if fingerprint.get('os', 'android') != 'android' or not version:
                continue
            expression = fingerprint.get('app_version', '*')
            try:
                matches = covered(version, expression)
            except ValueError as exc:
                print(f'Warning: {ref}: {exc}')
                continue
            if not matches:
                result.append({'skill': ref, 'package': package, 'version': version, 'range': expression})
                break
    return result


def sync_issues(repo, candidates, token):
    existing = pages(repo, 'issues?state=all&labels=skill-drift', token)
    labels = pages(repo, 'labels', token)
    if not any(label['name'] == 'skill-drift' for label in labels):
        api(repo, 'labels', token, 'POST', {'name': 'skill-drift', 'color': 'd93f0b'})
    for item in candidates:
        marker = f'<!-- ghost-skill-drift:{item["skill"]} -->'
        issue = next((i for i in existing if marker in i.get('body', '') and 'pull_request' not in i), None)
        data = {'title': f'drift: {item["skill"]} app {item["version"]} released, fingerprint covers {item["range"]}',
                'body': f'{marker}\n\nPlay Store package: `{item["package"]}`\n\nReleased version: `{item["version"]}`\n\nDeclared range: `{item["range"]}`\n\nPlease verify the skill on this app version and update its fingerprint if appropriate.',
                'labels': ['skill-drift']}
        if issue:
            data['state'] = 'open'
        api(repo, f'issues/{issue["number"]}' if issue else 'issues', token, 'PATCH' if issue else 'POST', data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', default='skillhub/registry.json')
    parser.add_argument('--versions', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    candidates = drift_candidates(json.loads(Path(args.registry).read_text()), json.loads(Path(args.versions).read_text()))
    print(json.dumps(candidates, indent=2))
    if not args.dry_run:
        sync_issues(os.environ['GITHUB_REPOSITORY'], candidates, os.environ['GH_TOKEN'])


if __name__ == '__main__':
    main()
