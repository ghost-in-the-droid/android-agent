"""Lint all workflows and audit Hub plus changed workflows with zizmor."""
import argparse
import subprocess
from pathlib import Path

from tools.ci.common import changed_paths


def audit_paths(paths, root=Path('.github/workflows')):
    selected = {str(p) for p in root.glob('skill*.yml')}
    for path in paths:
        candidate = Path(path)
        if candidate.parent == root and candidate.suffix in ('.yml', '.yaml') and candidate.is_file():
            selected.add(str(candidate))
    return sorted(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    args = parser.parse_args()
    subprocess.run(['actionlint'], check=True)
    selected = audit_paths(changed_paths(args.base))
    if selected:
        subprocess.run(['zizmor', '--no-progress', *selected], check=True)


if __name__ == '__main__':
    main()
