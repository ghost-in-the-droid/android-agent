"""Three independent vendor signals; network failures never grant trust."""
import argparse
import base64
import sys
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import yaml

PACKAGE = re.compile(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+')
REPOSITORY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')


def load_policy(path):
    path = Path(path)
    if not path.exists():
        return []  # Curated policy may not have landed yet; other signals still work.
    if path.stat().st_size > 100000:
        raise ValueError('Vendor policy is too large')
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw.get('version') != 1 or not isinstance(raw.get('prefixes'), list):
        raise ValueError('Vendor policy requires version 1 and prefixes')
    prefixes = []
    for item in raw['prefixes']:
        if not isinstance(item, dict) or not isinstance(item.get('prefix'), str) or not PACKAGE.fullmatch(item['prefix']):
            raise ValueError('Invalid vendor package prefix')
        if not all(isinstance(item.get(key), str) and item[key] for key in ('vendor', 'category')):
            raise ValueError('Vendor prefix requires vendor and category')
        if item.get('vendor_repo') is not None and (not isinstance(item['vendor_repo'], str) or not REPOSITORY.fullmatch(item['vendor_repo'])):
            raise ValueError('Invalid curated vendor repository')
        prefixes.append(dict(item))
    return prefixes


def gh(endpoint):
    process = subprocess.run(['gh', 'api', endpoint], check=True, capture_output=True, text=True, timeout=20)
    if len(process.stdout) > 1000000:
        raise ValueError('Vendor API response too large')
    return json.loads(process.stdout)


def check_vendor(package, policy=()):
    if not isinstance(package, str) or not PACKAGE.fullmatch(package) or len(package) > 200:
        return {'trusted': False, 'signal': 'none'}
    matching = [entry for entry in policy if package == entry['prefix'] or package.startswith(entry['prefix'] + '.')]
    if any(not entry.get('vendor_repo') for entry in matching):
        return {'trusted': True, 'signal': 'prefix'}
    try:
        with urllib.request.urlopen(f'https://f-droid.org/en/packages/{package}/', timeout=10) as response:
            if response.status == 200:
                return {'trusted': True, 'signal': 'fdroid'}
    except (OSError, urllib.error.URLError):
        pass
    for entry in matching:
        vendor_repo = entry.get('vendor_repo')
        if not vendor_repo:
            continue
        try:
            repo = gh(f'repos/{vendor_repo}')
            stars = repo.get('stargazers_count')
            if type(stars) is int and stars >= 1000:
                releases = gh(f'repos/{vendor_repo}/releases?per_page=1')
                if isinstance(releases, list) and releases and isinstance(releases[0], dict) and type(releases[0].get('id')) is int:
                    return {'trusted': True, 'signal': 'github'}
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            pass
    return {'trusted': False, 'signal': 'none'}


def has_submitter_python(raw, paths, directory):
    def inside_base(target):
        if isinstance(target, dict):
            target = target.get('function')
        path = target.split(':', 1)[0] if isinstance(target, str) else ''
        return path.startswith('skillhub/_base/') and '..' not in path.split('/') and path.endswith('.py')
    def inspect(value):
        if isinstance(value, dict):
            return any((key in ('python_action', 'custom_python') and not inside_base(item)) or inspect(item)
                       for key, item in value.items())
        if isinstance(value, list):
            return any(inspect(item) for item in value)
        return False
    return inspect(raw) or any(path.startswith(directory + '/') and path.endswith('.py') and not path.startswith('skillhub/_base/') for path in paths)


def verdict(manifests, paths, policy, head_sha, approval_source='none'):
    from tools.ci.review_guard import valid_sha
    valid_sha(head_sha)
    if approval_source not in ('none', 'sha-label', 'maintainer-comment'):
        raise ValueError('Invalid approval source')
    approved = approval_source != 'none'
    rows = []
    for directory, raw in sorted(manifests.items()):
        if not isinstance(raw, dict) or not isinstance(raw.get('fingerprint'), dict):
            raise ValueError('Skill requires a fingerprint')
        package = raw['fingerprint'].get('app_package')
        vendor = check_vendor(package, policy)
        python = has_submitter_python(raw, paths, directory)
        branch = 'sha-approval' if approved else 'vendor-no-python' if vendor['trusted'] and not python else 'blocked'
        warnings = ['skill.yaml vendor_repo ignored; only curated mappings are used'] if 'vendor_repo' in raw else []
        rows.append({'skill': directory, 'package': package if isinstance(package, str) else '', **vendor,
                     'has_submitter_python': python, 'branch': branch, 'warnings': warnings})
    return {'schema_version': 2, 'kind': 'vendor-trust', 'head_sha': head_sha,
            'allowed': all(row['branch'] != 'blocked' for row in rows), 'approval_source': approval_source, 'skills': rows}


def check_skills(skills, policy, head_sha, approval_source='none'):
    manifests, paths = {}, []
    for directory in skills:
        manifest = Path(directory) / 'skill.yaml'
        if not manifest.is_file():
            continue
        if manifest.is_symlink() or manifest.stat().st_size > 200000:
            raise ValueError('Invalid skill manifest')
        manifests[directory] = yaml.safe_load(manifest.read_text())
        paths.extend(path.as_posix() for path in Path(directory).rglob('*.py'))
    return verdict(manifests, paths, load_policy(policy), head_sha, approval_source)


def origin_verdict(repo, pr, files, token, policy_path):
    from tools.ci.common import api, skill_dirs
    from tools.ci.review_guard import approved_from_api, valid_sha
    head = valid_sha(pr['head']['sha'])
    paths = [row['filename'] for row in files if row.get('status') != 'removed']
    manifests = {}
    for directory in skill_dirs([row['filename'] for row in files]):
        try:
            content = api(repo, f'contents/{directory}/skill.yaml?ref={head}', token)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and any(row['filename'] == directory + '/skill.yaml' and row.get('status') == 'removed' for row in files):
                continue
            raise
        if content.get('type') != 'file' or content.get('encoding') != 'base64' or type(content.get('size')) is not int or not 0 <= content['size'] <= 200000:
            raise ValueError('Invalid head manifest response')
        encoded = content.get('content')
        if not isinstance(encoded, str) or len(encoded) > 300000:
            raise ValueError('Manifest response too large')
        body = base64.b64decode(''.join(encoded.split()), validate=True)
        if len(body) > 200000:
            raise ValueError('Manifest too large')
        manifests[directory] = yaml.safe_load(body)
        # Also inspect existing Python files that were not changed by this PR.
        listing = api(repo, f'contents/{directory}?ref={head}', token)
        if not isinstance(listing, list) or len(listing) > 1000:
            raise ValueError('Invalid skill directory listing')
        for item in listing:
            if isinstance(item, dict) and isinstance(item.get('path'), str) and item['path'].startswith(directory + '/') and item['path'].endswith('.py'):
                paths.append(item['path'])
    return verdict(manifests, paths, load_policy(policy_path), head, approved_from_api(repo, pr, token))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', required=True)
    parser.add_argument('--policy', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--repo')
    parser.add_argument('--pr', type=int)
    args = parser.parse_args()
    from tools.ci.common import skill_dirs
    skills = json.loads(args.matrix)['skill']
    if skills != skill_dirs([skill + '/skill.yaml' for skill in skills]):
        raise ValueError('Invalid skill matrix')
    from tools.ci.review_guard import approved_from_api
    source = 'none'
    if args.repo and args.pr:
        from tools.ci.common import api
        token = os.environ.get('GH_TOKEN', '')
        # The PR-side trust job runs with a read-only token on the PR's permissions; on a
        # private repo or a fork these lookups may 403/404. Any failure means "no approval
        # visible from here" (fail closed to the unapproved branch), never a crash.
        try:
            pr = api(args.repo, f'pulls/{args.pr}', token)
            if pr['head']['sha'] == args.head:
                source = approved_from_api(args.repo, pr, token)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            print(f'::warning::approval lookup unavailable ({exc.__class__.__name__}); treating as not approved', file=sys.stderr)
            source = 'none'
    result = check_skills(skills, args.policy, args.head, source)
    for row in result['skills']:
        print(f"{row['skill']}: {row['branch']}", file=sys.stderr)
        for warning in row['warnings']:
            print(warning, file=sys.stderr)
    Path(args.output).write_text(json.dumps(result, indent=2))
    # An untrusted vendor is an intentional gate stop, not a schema/analyzer failure.
    print('true' if result['allowed'] else 'false')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
