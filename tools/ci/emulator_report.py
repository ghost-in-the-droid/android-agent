"""Validate bounded emulator summaries and publish one proof comment from trusted code."""
import argparse
import io
import json
import math
import os
import re
import urllib.request
import zipfile
from tools.ci.common import api, pages

MARKER = '<!-- ghost-skill-emulator -->'
MAX_RESULT = 200000
MAX_ARCHIVE = 1000000
FINGERPRINT_FIELDS = {'os', 'os_version', 'hardware', 'app_package', 'app_version',
                      'screen_wxh', 'density', 'locale', 'theme'}


def text(value, limit):
    if not isinstance(value, str) or len(value) > limit or any(c in value for c in '<>') or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid result text (size, HTML or control characters)')


def validate_result(result):
    if not isinstance(result, dict) or set(result) != {'skill', 'actions'}:
        raise ValueError('Invalid result object')
    text(result['skill'], 180)
    if not re.fullmatch(r'skillhub/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', result['skill']):
        raise ValueError('Invalid skill path')
    if not isinstance(result['actions'], list) or len(result['actions']) > 100:
        raise ValueError('Invalid action count')
    names = set()
    for row in result['actions']:
        if not isinstance(row, dict) or set(row) != {'name', 'status', 'steps', 'seconds', 'fingerprint', 'reason'}:
            raise ValueError('Invalid action object')
        text(row['name'], 80)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', row['name']) or row['name'] in names:
            raise ValueError('Invalid or duplicate action name')
        names.add(row['name'])
        if row['status'] not in ('pass', 'fail', 'skip'):
            raise ValueError('Invalid status enum')
        if type(row['steps']) is not int or not 0 <= row['steps'] <= 10000:
            raise ValueError('Invalid step count')
        if type(row['seconds']) not in (int, float) or not math.isfinite(row['seconds']) or not 0 <= row['seconds'] <= 3600:
            raise ValueError('Invalid wall time')
        text(row['reason'], 500)
        fingerprint = row['fingerprint']
        if not isinstance(fingerprint, dict) or set(fingerprint) - FINGERPRINT_FIELDS:
            raise ValueError('Invalid fingerprint fields')
        for value in fingerprint.values():
            text(value, 256)
        if 'os' in fingerprint and fingerprint['os'] not in ('android', 'ios'):
            raise ValueError('Invalid fingerprint OS')
        if row['status'] == 'pass':
            required = {'os', 'os_version', 'hardware', 'app_package', 'app_version'}
            if not required <= fingerprint.keys() or any(not fingerprint[k] or '*' in fingerprint[k] for k in required):
                raise ValueError('Passing action requires a concrete fingerprint')
    return result


def cell(value):
    value = str(value)[:1000].replace('@', '@\u200b')
    for source, target in {'&': '&amp;', '<': '&lt;', '>': '&gt;', '|': '&#124;', '`': '&#96;', '[': '&#91;', ']': '&#93;', '(': '&#40;', ')': '&#41;', '\\': '&#92;', '*': '&#42;', '_': '&#95;'}.items():
        value = value.replace(source, target)
    return value.replace('\n', ' ').replace('\r', ' ')


def render(results, repo, run_id, conclusion='success', trusted=True):
    url = f'https://github.com/{repo}/actions/runs/{int(run_id)}'
    failed = conclusion != 'success' or any(row['status'] == 'fail' for result in results for row in result['actions'])
    icon = '🟡' if not trusted else '🔴' if failed else ('🟢' if results and any(r['status'] == 'pass' for v in results for r in v['actions']) else '🟡')
    lines = [MARKER, f'## {icon} Skill emulator run results', '', '| Skill | Action | Result | Steps | Wall time | Artifacts | Fingerprint / reason |', '| --- | --- | --- | --- | --- | --- | --- |']
    if not trusted:
        from tools.ci.review_guard import WARNING
        lines[1] = '## Warning: ' + WARNING
    for result in results:
        artifact = result.get('_artifact_id')
        link = f'{url}/artifacts/{int(artifact)}' if artifact else url
        rows = result['actions'] or [{'name': 'boot', 'status': 'fail', 'reason': 'No action result; inspect boot logs'}]
        for row in rows:
            status = row['status']
            if not trusted and status == 'pass':
                status = 'untrusted'
            mark = {'pass': '🟢', 'fail': '🔴', 'skip': '🟡', 'untrusted': '🟡'}[status]
            fingerprint = json.dumps(row.get('fingerprint', {}), sort_keys=True)
            lines.append(f'| {cell(result["skill"])} | {cell(row["name"])} | {mark} {status} | {cell(row.get("steps", 0))} | {cell(row.get("seconds", 0))} s | [video and integrity-signed run record]({link}) | {cell(fingerprint)} {cell(row.get("reason", ""))} |')
    if not results:
        lines.append(f'No run result is available. [Inspect the run and trust gate]({url}).')
    body = '\n'.join(lines)
    if len(body) > 60000:
        raise ValueError('Proof comment exceeds size limit')
    return body


def artifact_list(repo, run, token):
    artifacts = []
    for page in range(1, 21):
        batch = api(repo, f'actions/runs/{run}/artifacts?per_page=100&page={page}', token)['artifacts']
        artifacts.extend(batch)
        if len(batch) < 100:
            return artifacts
    raise ValueError('Artifact pagination limit exceeded')


def bounded_json(repo, artifact, token):
    if artifact['size_in_bytes'] > MAX_ARCHIVE:
        raise ValueError('Emulator result archive too large')
    # The download endpoint is constructed from trusted GitHub metadata, never result JSON.
    request = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/artifacts/{int(artifact["id"])}/zip', headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise ValueError('Emulator result archive too large')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) != 1 or entries[0].filename != 'result.json' or entries[0].file_size > MAX_RESULT:
            raise ValueError('Archive must contain only bounded result.json')
        raw = archive.read(entries[0])
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def read_summary(repo, artifact, token):
    return validate_result(bounded_json(repo, artifact, token))


def publish_run(repo, run, number, token, conclusion='success', trusted=True):
    results = []
    artifacts = artifact_list(repo, run, token) if trusted else []
    for artifact in artifacts:
        if not re.fullmatch(r'skill-emulator-result-\d+', artifact['name']) or artifact['expired']:
            continue
        if len(results) >= 100:
            raise ValueError('Too many emulator summaries')
        result = read_summary(repo, artifact, token)
        media_name = artifact['name'].replace('-result-', '-media-')
        media = next((a for a in artifacts if a['name'] == media_name and not a['expired']), None)
        result['_artifact_id'] = media['id'] if media else artifact['id']
        results.append(result)
    body = render(sorted(results, key=lambda r: r['skill']), repo, run, conclusion, trusted)
    comments = pages(repo, f'issues/{number}/comments', token)
    sticky = next((c for c in comments if c.get('user', {}).get('login') == 'github-actions[bot]' and MARKER in c.get('body', '')), None)
    api(repo, f'issues/comments/{sticky["id"]}' if sticky else f'issues/{number}/comments', token,
        'PATCH' if sticky else 'POST', {'body': body})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=int, required=True)
    args = parser.parse_args()
    repo, token = os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN']
    run = api(repo, f'actions/runs/{args.run}', token)
    if run['event'] != 'pull_request' or run['name'] != 'Optional skill emulator runs':
        raise ValueError('Only emulator PR runs can be reported')
    pulls = run.get('pull_requests', []) or [p for p in pages(repo, 'pulls?state=open', token) if p['head']['sha'] == run['head_sha']]
    if not pulls:
        return
    number = pulls[0]['number']
    pr = api(repo, f'pulls/{number}', token)
    if pr['state'] != 'open' or pr['head']['sha'] != run['head_sha']:
        return
    from tools.ci.review_guard import changed_files, modified_ci
    try:
        files = changed_files(repo, number, pr, token)
        trusted = not modified_ci(files, run)
    except (OSError, ValueError, RuntimeError):
        trusted = False
    publish_run(repo, args.run, number, token, run['conclusion'], trusted)


if __name__ == '__main__':
    main()
