"""Local terminal capture with phone capture and all rendering on an SSH host."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid


def remote_command(plan, *arguments):
    host = plan.get('render_host') or '<render-host>'
    root = plan['render_root']
    # Expand only the leading home marker, never arbitrary shell expressions.
    directory = '"$HOME"/' + shlex.quote(root[2:]) if root.startswith('~/') else shlex.quote(root)
    command = 'cd ' + directory + ' && ' + shlex.join([
        plan['render_python'], 'scripts/showcase/record_skill_demo.py', *map(str, arguments)])
    return ['ssh', '-o', 'BatchMode=yes', host, command]


def transfer(plan, local, remote, *, receive=False):
    host = plan.get('render_host') or '<render-host>'
    source, destination = (f'{host}:{remote}', str(local)) if receive else (str(local), f'{host}:{remote}')
    return ['scp', '-q', '-o', 'BatchMode=yes', source, destination]


def dry_commands(plan):
    from gitd.skills.engine.demo import capture_command
    work = '/tmp/ghost-demo-<random-id>'
    host = plan.get('render_host') or '<render-host>'
    return {
        'render_tools': remote_command(plan, '--check-tools', *([] if plan['ocr'] else ['--no-ocr'])),
        'prepare_remote': ['ssh', '-o', 'BatchMode=yes', host, 'mkdir -m 700 ' + shlex.quote(work)],
        'upload_plan': transfer(plan, '<local-workdir>/plan.json', work + '/plan.json'),
        'upload_spec': transfer(plan, '<local-workdir>/action.spec.yaml', work + '/action.spec.yaml'),
        'phone_start': remote_command(plan, '--phone-start', work + '/plan.json', '--workdir', work),
        'local_cast': capture_command(plan, '<local-workdir>'),
        'phone_stop': remote_command(plan, '--phone-stop', work + '/plan.json', '--workdir', work),
        'upload_cast': transfer(plan, '<local-workdir>/terminal.cast', work + '/terminal.cast'),
        'compose_remote': remote_command(plan, '--compose-plan', work + '/plan.json',
                                         '--external-cast', work + '/terminal.cast', '--phone-video', work + '/phone.mp4',
                                         '--out', work + '/demo.webm', '--workdir', work),
        'download_video': transfer(plan, '<local-workdir>/demo.webm', work + '/demo.webm', receive=True),
        'download_metrics': transfer(plan, '<local-workdir>/metrics.json', work + '/metrics.json', receive=True),
        'cleanup_remote': remote_command(plan, '--cleanup', work),
    }


def portable_demo_meta(plan):
    """What a re-record needs, without this machine's paths (home dirs are scrubbed identifiers)."""
    import copy
    from gitd.skills.engine.demo import REPO_ROOT
    meta = {key: copy.deepcopy(plan[key]) for key in ('agent', 'params', 'mcp_config', 'render_host', 'render_root',
                                                      'phone_offset_s', 'capture_offset_s', 'limits') if key in plan}
    for server in (meta.get('mcp_config') or {}).get('mcpServers', {}).values():
        if str(server.get('command', '')).endswith(('python', 'python3')) or '/python' in str(server.get('command', '')):
            server['command'] = 'python3'
        env = server.get('env') or {}
        if env.get('PYTHONPATH') == str(REPO_ROOT):
            env['PYTHONPATH'] = '<repo>'
    return meta


def checked(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=kwargs.pop('timeout', 180), **kwargs)


def record_split(plan, recorder):
    from gitd.skills.engine import demo
    import yaml
    if not plan.get('render_host'):
        raise ValueError('--render-host or GHOST_DEMO_RENDER_HOST is required; local encoding is disabled')
    tools = checked(remote_command(plan, '--check-tools', *([] if plan['ocr'] else ['--no-ocr'])))
    missing = json.loads(tools.stdout).get('missing', [])
    if missing:
        raise RuntimeError('Render host missing tools: ' + ', '.join(missing) + '; install adb, agg, ffmpeg/ffprobe, and Tesseract there')
    if not plan['ocr']:
        print('Warning: OCR disabled; review the recording before sharing')
    public_text = plan['prompt'] + '\n' + json.dumps(plan['spec'].get('cards', {}), ensure_ascii=False)
    if recorder.scan_text(public_text, recorder.load_forbidden()):
        raise RuntimeError('Demo prompt or cards contain forbidden private text')
    remote_work = '/tmp/ghost-demo-' + uuid.uuid4().hex
    host = plan['render_host']
    checked(['ssh', '-o', 'BatchMode=yes', host, 'mkdir -m 700 ' + shlex.quote(remote_work)])
    phone_started = False
    with tempfile.TemporaryDirectory(prefix='ghost-demo-local-') as temporary:
        workdir = Path(temporary)
        import socket
        saved_plan = dict(plan)
        saved_plan['capture_hostname'] = socket.gethostname()
        saved_plan['privacy_patterns'] = '\n'.join(source for source, pattern in recorder.load_forbidden())
        started = None
        before = set(Path(plan['artifact_dir']).glob('*.json'))
        try:
            (workdir / 'plan.json').write_text(json.dumps(saved_plan))
            (workdir / 'action.spec.yaml').write_text(yaml.safe_dump(plan['spec'], sort_keys=False, allow_unicode=True))
            (workdir / 'mcp.json').write_text(json.dumps(plan['mcp_config']))
            checked(transfer(plan, workdir / 'plan.json', remote_work + '/plan.json'))
            checked(transfer(plan, workdir / 'action.spec.yaml', remote_work + '/action.spec.yaml'))
            phone_started = True
            ready = checked(remote_command(plan, '--phone-start', remote_work + '/plan.json', '--workdir', remote_work))
            metadata = json.loads(ready.stdout.strip().splitlines()[-1])
            phone_time = float(metadata['started_at'])
            started = time.time()
            env = dict(os.environ)
            env.pop('TMUX', None)
            env.update(plan['spec']['env'])
            env.update(TERM='xterm-256color', PYTHONUNBUFFERED='1', COLUMNS='60', LINES='28', GHOST_TELEMETRY_ENDPOINT='')
            recorder.capture_external_cast(demo.capture_command(plan, workdir), workdir / 'terminal.cast',
                                           env=env, cwd=str(demo.REPO_ROOT), timeout=150)
            checked(remote_command(plan, '--phone-stop', remote_work + '/plan.json', '--workdir', remote_work))
            phone_started = False
            # Cross-host clocks can drift. Remote start and stop bracket the
            # phone capture; terminal header supplies the local cast origin.
            terminal_start = started
            try:
                from datetime import datetime
                header = json.loads((workdir / 'terminal.cast').read_text().splitlines()[0])
                if header.get('timestamp'):
                    terminal_start = datetime.fromisoformat(header['timestamp'].replace('Z', '+00:00')).timestamp()
            except (ValueError, TypeError, AttributeError):
                pass
            # SSH round-trip time bounds offset uncertainty; the manual lead
            # knob handles stream startup latency. Assume synchronized clocks.
            saved_plan['capture_offset_s'] = terminal_start - phone_time - plan['phone_offset_s']
            saved_plan['capture_duration_s'] = time.time() - started
            artifacts = set(Path(plan['artifact_dir']).glob('*.json')) - before
            valid = []
            for artifact in artifacts:
                try:
                    evidence = json.loads(artifact.read_text())
                    if evidence.get('signature', {}).get('value') and any(a.get('name') == plan['action'] for a in evidence.get('actions', [])):
                        valid.append(artifact)
                except (OSError, ValueError, AttributeError):
                    pass
            if not valid and plan.get("mode") != "soft":
                raise RuntimeError('Agent did not produce a signed run artifact for the selected action')
            if valid:
                print(f'Run artifact: {sorted(valid)[-1]}')
            (workdir / 'plan.json').write_text(json.dumps(saved_plan))
            checked(transfer(plan, workdir / 'plan.json', remote_work + '/plan.json'))
            checked(transfer(plan, workdir / 'terminal.cast', remote_work + '/terminal.cast'))
            checked(transfer(plan, workdir / 'action.spec.yaml', remote_work + '/action.spec.yaml'))
            checked(remote_command(plan, '--compose-plan', remote_work + '/plan.json',
                                   '--external-cast', remote_work + '/terminal.cast', '--phone-video', remote_work + '/phone.mp4',
                                   '--out', remote_work + '/demo.webm', '--workdir', remote_work), timeout=900)
            checked(transfer(plan, workdir / 'demo.webm', remote_work + '/demo.webm', receive=True))
            checked(transfer(plan, workdir / 'metrics.json', remote_work + '/metrics.json', receive=True))
            demo.check_size(workdir / 'demo.webm')
            metrics = json.loads((workdir / 'metrics.json').read_text())
            if (metrics.get('codec') != 'vp9' or metrics.get('audio') is not False or
                    max(metrics.get('width', 0), metrics.get('height', 0)) != plan['limits']['long_side_px'] or
                    not 0 < metrics.get('duration_s', 0) <= 30 or metrics.get('size_bytes') != (workdir / 'demo.webm').stat().st_size):
                raise RuntimeError('Remote clip does not satisfy hub limits')
            destination = Path(plan['out'])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workdir / 'demo.webm', destination)
            spec_path = Path(plan['spec_out'])
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            saved_spec = dict(plan['spec'])
            saved_spec['skill_demo'] = portable_demo_meta(saved_plan)
            spec_path.write_text(yaml.safe_dump(saved_spec, sort_keys=False, allow_unicode=True))
            if plan['legacy_out']:
                legacy = Path(plan['legacy_out'])
                if legacy.is_symlink():
                    legacy.unlink()
                if legacy.resolve() != destination.resolve():
                    shutil.copy2(destination, legacy)
            demo.warn_folder_size(plan['demos_dir'])
            print(f"Demo: {destination} ({metrics['size_bytes']} bytes, {metrics['duration_s']:.2f} s)")
            return 0
        finally:
            if phone_started:
                try:
                    checked(remote_command(plan, '--phone-stop', remote_work + '/plan.json', '--workdir', remote_work))
                except (OSError, subprocess.SubprocessError):
                    print('Warning: remote phone stop failed; screenrecord has a 179-second hard limit')
            try:
                checked(remote_command(plan, '--cleanup', remote_work))
            except (OSError, subprocess.SubprocessError):
                print('Warning: remote temporary recording directory needs manual cleanup')
