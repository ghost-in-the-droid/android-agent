#!/usr/bin/env python3
"""Print jsDelivr purge URLs for the discovery index and changed skill indexes."""
import argparse
import os
import subprocess
from pathlib import PurePosixPath
from urllib.parse import quote


def purge_urls(repo, changed_paths):
    paths = {'skillhub/registry.json'}
    for path in changed_paths:
        parts = PurePosixPath(path).parts
        if len(parts) == 4 and parts[:3] == ('skillhub', 'registry', 'index') and parts[3].endswith('.json'):
            paths.add('/'.join(parts))
    return [f'https://purge.jsdelivr.net/gh/{repo}@main/{quote(path, safe="/")}' for path in sorted(paths)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'))
    args = parser.parse_args()
    if not args.repo:
        parser.error('--repo or GITHUB_REPOSITORY is required')
    if args.base == '0' * 40:
        command = ['git', 'ls-tree', '-r', '--name-only', '-z', 'HEAD']
    else:
        command = ['git', 'diff', '--name-only', '--no-renames', '-z', args.base, 'HEAD', '--']
    paths = subprocess.check_output(command).decode().split('\0')
    print('\n'.join(purge_urls(args.repo, paths)))


if __name__ == '__main__':
    main()
