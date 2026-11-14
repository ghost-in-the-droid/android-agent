"""Origin-side CI modification guards and commit-bound approval handling."""
import re
import urllib.error
from urllib.parse import quote

from tools.ci.common import api, pages, skill_dirs

WARNING = 'this PR modifies CI or trust policy; results are not trusted'
EXPECTED = {'Optional skill emulator runs': '.github/workflows/skill-emulator-run.yml',
            'Skill submission': '.github/workflows/skill-submission.yml'}
SHA = re.compile(r'[0-9a-f]{40}')


def valid_sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError('A full head SHA is required')
    return value


def modified_ci(files, run):
    expected = EXPECTED.get(run.get('name'))
    if not expected or run.get('path') != expected:
        return True
    directories = skill_dirs([row.get('filename', '') for row in files])
    if not directories:
        return True
    for row in files:
        for path in (row.get('filename'), row.get('previous_filename')):
            if path is None:
                continue
            # Check raw paths, including rename sources; normalization must not
            # turn traversal or malformed metadata into an allowed skill path.
            if not isinstance(path, str) or any(p in ('', '.', '..') for p in path.split('/')):
                return True
            if not any(path.startswith(directory + '/') for directory in directories):
                return True
    return False


def approval(head, labels, comments=(), permission=None, events=()):
    head = valid_sha(head)
    wanted = 'approved:' + head
    if wanted in labels and permission:
        matching = [event for event in events if event.get('event') in ('labeled', 'unlabeled')
                    and event.get('label', {}).get('name') == wanted]
        # GitHub issue events are chronological. A removed label cannot retain
        # the authority of its earlier maintainer application.
        if matching and matching[-1].get('event') == 'labeled':
            login = matching[-1].get('actor', {}).get('login')
            if login and permission(login) in ('admin', 'maintain'):
                return 'sha-label'
    if permission:
        pattern = re.compile(r'(?<![A-Za-z0-9_-])security-approved ' + head + r'(?![A-Za-z0-9])')
        for comment in comments:
            login = comment.get('user', {}).get('login')
            if login and isinstance(comment.get('body'), str) and pattern.search(comment['body']):
                if permission(login) in ('admin', 'maintain'):
                    return 'maintainer-comment'
    return 'none'


def approved_from_api(repo, pr, token):
    head = valid_sha(pr['head']['sha'])
    labels = [label['name'] for label in pr.get('labels', [])]
    try:
        events = pages(repo, f'issues/{pr["number"]}/events', token)
        comments = pages(repo, f'issues/{pr["number"]}/comments', token)
        def permission(login):
            result = api(repo, f'collaborators/{quote(login, safe="")}/permission', token)
            return result.get('role_name', result.get('permission'))
        return approval(head, labels, comments, permission, events)
    except (OSError, urllib.error.URLError, RuntimeError):
        return 'none'  # Missing API permission cannot grant approval.


def remove_stale_approvals(repo, number, pr, token):
    wanted = 'approved:' + valid_sha(pr['head']['sha'])
    for label in pr.get('labels', []):
        name = label['name']
        if name.casefold().startswith(('approved:', 'security-approved')) and name != wanted:
            api(repo, f'issues/{number}/labels/{quote(name, safe="")}', token, 'DELETE')


def changed_files(repo, number, pr, token):
    files = pages(repo, f'pulls/{number}/files', token)
    if pr.get('changed_files', len(files)) > len(files):
        raise ValueError('Changed-file response is incomplete')
    if any(not isinstance(row.get('filename'), str) or not row['filename'] for row in files):
        raise ValueError('Invalid changed-file metadata')
    return files
