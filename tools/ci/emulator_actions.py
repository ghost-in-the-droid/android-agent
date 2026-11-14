"""Optional emulator action execution; all device work happens on hosted CI."""
import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tools.ci.common import skill_dirs
from tools.ci.drift import covered




def failure_reason(command, code, output):
    """Short, plain-text reason for a failed CLI invocation: verb, exit code, last output lines."""
    lines = [ln.strip() for ln in (output or '').splitlines() if ln.strip()]
    tail = ' | '.join(lines[-2:]) if lines else 'no output'
    return f"ghost skill {command[0]} exit {code}: {tail}"[:500]

def iter_actions(raw):
    """Yield (name, action_dict) for a skill.yaml actions block.

    Schema v2 writes ``actions:`` as a list of mappings with a ``name`` key (what
    ``ghost skill validate`` accepts); the older mapping form {name: {...}} is also
    accepted so the runner never crashes on a skill the validator passed.
    """
    actions = raw.get('actions') or []
    if isinstance(actions, dict):
        return list(actions.items())
    if isinstance(actions, list):
        out = []
        for entry in actions:
            if not isinstance(entry, dict) or not entry.get('name'):
                raise ValueError('action entries must be mappings with a name')
            out.append((str(entry['name']), entry))
        return out
    raise ValueError('actions must be a list or a mapping')

def matrix(paths, root=Path('.')):
    return {'skill': [p for p in skill_dirs(paths) if (root / p / 'skill.yaml').is_file()]}


def params(action):
    value = action.get('demo_params')
    if value is None:
        case = action.get('test_case') or {}
        value = case.get('params', {})
    if not isinstance(value, dict):
        raise ValueError('Action demo_params or test_case.params must be a mapping')
    return value


def mismatch(expected, actual):
    for key, value in expected.items():
        if value in ('*', '', None):
            continue
        if key not in actual:
            return f'fingerprint {key} unavailable'
        if key in ('os_version', 'app_version'):
            try:
                matches = covered(str(actual[key]), str(value))
            except ValueError:
                return f'fingerprint {key}: unsupported range or concrete version'
        else:
            matches = fnmatch.fnmatchcase(str(actual[key]), str(value))
        if not matches:
            return f'fingerprint {key}: requires {value}, emulator has {actual[key]}'
    return ''


def adb(*args, timeout=20):
    return subprocess.run(['adb', '-s', 'emulator-5554', *args], check=True,
                          capture_output=True, text=True, timeout=timeout).stdout.strip()


def boot():
    adb('wait-for-device', timeout=120)
    for _ in range(60):
        if adb('shell', 'getprop', 'sys.boot_completed', timeout=10) == '1':
            break
        time.sleep(2)
    else:
        raise RuntimeError('Emulator never finished booting')
    for setting in ('window_animation_scale', 'transition_animation_scale', 'animator_duration_scale'):
        adb('shell', 'settings', 'put', 'global', setting, '0')
    adb('shell', 'settings', 'put', 'system', 'screen_off_timeout', '2147483647')
    adb('shell', 'svc', 'power', 'stayon', 'true')


def execute(skill_dir, output):
    from gitd.skills.engine.loader import load_skill
    from gitd.skills.engine.evidence import collect_fingerprint
    path = Path(skill_dir)
    if skill_dir not in skill_dirs([skill_dir + '/skill.yaml']):
        raise ValueError('Invalid skill directory')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result = {'skill': skill_dir, 'actions': []}
    destination = output / 'result.json'
    def save():
        for row in result['actions']:
            # Keep device/CLI exception text within the reporter's plain-text schema.
            row['reason'] = re.sub(r'[\x00-\x1f]', ' ', row['reason']).replace('<', 'less than ').replace('>', 'greater than ')[:500]
        destination.write_text(json.dumps(result, indent=2))
    save()
    boot()
    import yaml
    raw = yaml.safe_load((path / 'skill.yaml').read_text())
    skill = load_skill(path)
    for index, (name, action) in enumerate(iter_actions(raw)):
        row = {'name': name, 'status': 'fail', 'steps': 0, 'seconds': 0, 'fingerprint': {}, 'reason': ''}
        result['actions'].append(row)
        save()
        try:
            fingerprint = collect_fingerprint(skill, 'emulator-5554')
            for key, command in {'screen_wxh': ('wm', 'size'), 'density': ('wm', 'density')}.items():
                text = adb('shell', *command)
                fingerprint[key] = text.split(':')[-1].strip()
            fingerprint['locale'] = adb('shell', 'getprop', 'persist.sys.locale')
            row['fingerprint'] = fingerprint
            reason = mismatch({**raw.get('fingerprint', {}), **action.get('fingerprint', {})}, fingerprint)
            if reason:
                row.update(status='skip', reason=reason)
                print(f'Skipping {name}: {reason}')
                continue
            arguments = []
            for key, value in params(action).items():
                arguments.extend(['--param', f'{key}={str(value) if isinstance(value, str) else json.dumps(value)}'])
            remote = f'/sdcard/ghost-ci-{index}.mp4'
            local = output / f'action-{index}.mp4'
            before = set((path / 'runs').glob('*.json'))
            started = time.monotonic()
            recorder = subprocess.Popen(['adb', '-s', 'emulator-5554', 'shell', 'screenrecord', '--time-limit', '170', remote], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            statuses = []
            try:
                for command in ([ 'test', skill_dir, '--live', '--device', 'emulator-5554', '--action', name],
                                ['run', skill_dir, name, '--device', 'emulator-5554', '--record']):
                    remaining = 180 - (time.monotonic() - started)
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, 180)
                    proc = subprocess.run(['python3', '-m', 'gitd.skills.engine.cli', *command, *arguments],
                                          env={**os.environ, 'PYTHONPATH': '.'}, timeout=remaining,
                                          capture_output=True, text=True)
                    out = (getattr(proc, 'stdout', '') or '') + (getattr(proc, 'stderr', '') or '')
                    if out:
                        print(out, end='')
                    statuses.append(proc.returncode)
                    if proc.returncode != 0 and not row['reason']:
                        row['reason'] = failure_reason(command, proc.returncode, out)
                row['status'] = 'pass' if statuses == [0, 0] else 'fail'
            finally:
                row['seconds'] = round(time.monotonic() - started, 2)
                try:
                    adb('shell', 'pkill', '-2', 'screenrecord', timeout=5)
                except subprocess.SubprocessError:
                    pass
                try:
                    recorder.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    recorder.kill()
                    recorder.wait(timeout=5)
                try:
                    adb('pull', remote, str(local), timeout=30)
                except subprocess.SubprocessError:
                    row['status'] = 'fail'
                    row['reason'] = 'Screen recording pull failed'
                if not local.is_file() or local.is_symlink():
                    row['status'] = 'fail'
                    row['reason'] = 'No screen recording was collected'
                recorded_artifact = False
                for artifact in sorted(set((path / 'runs').glob('*.json')) - before):
                    if artifact.is_symlink() or artifact.stat().st_size > 200000:
                        continue
                    payload = json.loads(artifact.read_text())
                    recorded = next((a for a in payload.get('actions', []) if a['name'] == name), None)
                    if recorded is None or not payload.get('signature'):
                        continue
                    recorded_artifact = True
                    row['steps'] = len(recorded.get('steps', []))
                    runs = output / 'runs'
                    runs.mkdir(exist_ok=True)
                    shutil.copyfile(artifact, runs / artifact.name)
                if not recorded_artifact:
                    row['status'] = 'fail'
                    row['reason'] = 'No fresh integrity-signed run record was collected'
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            # Missing target packages and unsupported platforms cannot match this image.
            if not row['fingerprint']:
                row['status'] = 'skip'
            row['reason'] = str(exc)[:500]
            print(f'{name}: {row["status"]}: {row["reason"]}')
        finally:
            save()
    return int(any(a['status'] == 'fail' for a in result['actions']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    return execute(args.skill, args.output)


if __name__ == '__main__':
    raise SystemExit(main())
