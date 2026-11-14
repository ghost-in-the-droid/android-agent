#!/usr/bin/env python3
"""Skill demos using the seed worker's original showcase wrapper.

Copy the existing brand assets into a temporary showcase directory, generate
intro-<demo>.png, and join the per-action spec with a one-entry copy.yaml.
Capture uses record_demo helpers, including its external-cast entry point,
so a Claude TUI driver is never nested inside another asciinema recording.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]


def prepare_showcase(plan, recorder, workdir):
    import shutil
    import yaml
    showcase = workdir / 'showcase'
    brand = showcase / '_brand'
    original_brand = getattr(recorder, '_original_brand_dir', recorder.BRAND_DIR)
    recorder._original_brand_dir = original_brand
    shutil.copytree(original_brand, brand)
    sys.path.insert(0, str(REPO_ROOT / 'scripts/showcase'))
    import skill_cards
    skill_cards.BRAND_DIR = brand
    cards = skill_cards.resolve(plan['spec'])
    skill_cards.build(plan['spec']['demo'], plan['spec'])
    # record_demo's original compositor reads these shared names in this isolated workspace.
    shutil.copy2(brand / f"outro-{plan['spec']['demo']}.png", brand / 'outro.png')
    shutil.copy2(brand / f"bg-{plan['spec']['demo']}.png", brand / 'cprime-bg.png')
    plan['spec']['timeline'][0]['caption'] = cards['subheader']
    directory = showcase / plan['spec']['demo']
    directory.mkdir()
    (directory / 'spec.yaml').write_text(yaml.safe_dump(plan['spec'], sort_keys=False))
    (showcase / 'copy.yaml').write_text(yaml.safe_dump({'demos': [plan['copy_entry']]}))
    (workdir / 'mcp.json').write_text(json.dumps(plan['mcp_config']))
    recorder.SHOWCASE_DIR, recorder.BRAND_DIR = showcase, brand
    recorder.TERM_COLS = 60
    return recorder.load_spec(plan['spec']['demo'])


def read_plan(path):
    return json.loads(Path(path).read_text())


def load_helpers():
    sys.path.insert(0, str(REPO_ROOT))
    from gitd.skills.engine import demo
    return demo, demo.load_recorder()


def privacy_patterns(plan, recorder, workdir):
    extra = Path(workdir) / 'capture-forbidden.txt'
    extra.write_text(plan.get('privacy_patterns', ''))
    extra.chmod(0o600)
    return recorder.load_forbidden(extra_paths=[extra])


def clean_reset(dev, spec):
    """Reset only an installed, non-system demo app; seed via targeted broadcasts."""
    import re
    package = spec.get('demo_app', '')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+', package):
        raise ValueError('Invalid demo app package')
    system = dev.adb('shell', 'pm', 'list', 'packages', '-s').splitlines()
    installed = dev.adb('shell', 'pm', 'list', 'packages', '-3').splitlines()
    if f'package:{package}' in system or f'package:{package}' not in installed:
        raise ValueError('Demo reset requires an installed non-system app; system apps are never cleared')
    seeds = spec.get('seed', [])
    if not isinstance(seeds, list) or any(not isinstance(seed, dict) or not isinstance(seed.get('action'), str)
                                         or not isinstance(seed.get('extras', {}), dict) for seed in seeds):
        raise ValueError('seed must be a list of broadcast actions and string extras')
    if any(not isinstance(k, str) or not isinstance(v, str) for seed in seeds for k, v in seed.get('extras', {}).items()):
        raise ValueError('seed extras must be strings')
    dev.adb('shell', 'am', 'force-stop', package)
    if dev.adb('shell', 'pm', 'clear', package).strip() != 'Success':
        raise RuntimeError('Demo app reset failed')
    import shlex
    for seed in seeds:
        command = ['am', 'broadcast', '-p', package, '-a', seed['action']]
        for key, value in seed.get('extras', {}).items():
            command += ['--es', key, value]
        dev.adb('shell', shlex.join(command))
    dev.adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')


def remote_phone_start(plan, workdir):
    import os
    import subprocess
    import time
    helpers, recorder = load_helpers()
    # Phone tasks talk only to this render host's adb server.
    os.environ['ADB_SERVER_SOCKET'] = 'tcp:127.0.0.1:5037'
    workdir = Path(workdir)
    dev = recorder.get_device(plan['serial'])
    helpers.require_clean_device(dev, plan['physical_account_override'])
    state = {'serial': dev.serial, 'restore': {}, 'remote': '/sdcard/ghost_demo_' + workdir.name + '.mp4'}
    state_path = workdir / 'phone-state.json'
    if state_path.exists():
        raise RuntimeError('Phone recording already started in this workspace')
    state_path.write_text(json.dumps(state))
    try:
        state['restore'] = recorder.phone_privacy_prep(dev, workdir, privacy_patterns(plan, recorder, workdir), need_ocr=plan['ocr'])
        state_path.write_text(json.dumps(state))
        setup = dict(plan['spec'])
        setup['setup'] = [step for step in setup.get('setup', []) if step['step'] != 'launch_app']
        recorder.run_setup(dev, setup)
        clean_reset(dev, plan['spec'])
        command = ['adb', '-s', dev.serial, 'shell', 'screenrecord', '--bit-rate', '8000000', '--time-limit', '179']
        if plan['spec'].get('record_size'):
            command.extend(['--size', plan['spec']['record_size']])
        command.append(state['remote'])
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        state['pid'] = process.pid
        state['started_at'] = time.time()
        state_path.write_text(json.dumps(state))
        time.sleep(1.5)
        if process.poll() is not None:
            raise RuntimeError('Remote screenrecord exited before capture')
        recorder.run_setup(dev, {'setup': [{'step': 'launch_app', 'args': {'package': plan['spec']['demo_app']}}]})
        print(json.dumps({'started_at': state['started_at']}))
    except BaseException:
        remote_phone_stop(plan, workdir, pull=False)
        raise


def remote_phone_stop(plan, workdir, *, pull=True):
    import os
    import subprocess
    import time
    helpers, recorder = load_helpers()
    os.environ['ADB_SERVER_SOCKET'] = 'tcp:127.0.0.1:5037'
    workdir = Path(workdir)
    state_path = workdir / 'phone-state.json'
    if not state_path.exists():
        return
    state = read_plan(state_path)
    dev = recorder.get_device(state['serial'])
    try:
        dev.adb_soft('shell', 'pkill', '-2', 'screenrecord')
        time.sleep(1.5)
        if pull and state.get('pid'):
            subprocess.run(['adb', '-s', dev.serial, 'pull', state['remote'], str(workdir / 'phone.mp4')], check=True, capture_output=True, timeout=30)
    finally:
        dev.adb_soft('shell', 'rm', '-f', state['remote'])
        recorder.phone_privacy_restore(dev, state.get('restore', {}))
        state_path.unlink(missing_ok=True)
    print(json.dumps({'stopped_at': time.time()}))


def compose_existing(plan, cast, phone_video, out, workdir):
    import subprocess
    helpers, recorder = load_helpers()
    workdir = Path(workdir)
    spec = prepare_showcase(plan, recorder, workdir)
    patterns = privacy_patterns(plan, recorder, workdir)
    # Use the local host identity sent in the plan for substitutions, never log it.
    extra = [(plan['serial'], '<ANDROID_DEVICE>')]
    if plan.get('capture_hostname'):
        extra.append((plan['capture_hostname'], 'ghost-demo'))
    scrubbed = workdir / 'terminal_scrubbed.cast'
    recorder.scrub_cast(Path(cast), scrubbed, extra=extra, cols=60, rows=28)
    if recorder.scan_text(scrubbed.read_text(), patterns):
        raise RuntimeError('Terminal privacy scan failed')
    elapsed = plan.get('capture_duration_s', 0)
    if elapsed > 28:
        print('Warning: recording exceeds 30 seconds; final clip will be trimmed')
    spec = fit_timeline(spec, recorder, elapsed)
    recorder.render_terminal(scrubbed, workdir / 'terminal.mp4', workdir)
    recorder.composite(spec, workdir, workdir / 'terminal.mp4', Path(phone_video),
                       plan.get('capture_offset_s', -plan['phone_offset_s']), workdir / 'composite.webm')
    composite = workdir / 'composite.webm'
    if plan.get('trim_idle'):
        duration_probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json',
                                         str(composite)], check=True, capture_output=True, text=True, timeout=30)
        duration = float(json.loads(duration_probe.stdout)['format']['duration'])
        # Preserve readable intro/outro cards while dropping idle frames from the
        # already composited middle. No pane is ever cut independently.
        end = duration - recorder.OUTRO_S
        if end <= recorder.INTRO_S:
            raise RuntimeError('Composite is too short to trim')
        filters = (f'[0:v]split=3[a][b][c];[a]trim=end={recorder.INTRO_S},setpts=PTS-STARTPTS[intro];'
                   f'[b]trim=start={recorder.INTRO_S}:end={end},mpdecimate,setpts=N/30/TB[body];'
                   f'[c]trim=start={end},setpts=PTS-STARTPTS[outro];'
                   '[intro][body][outro]concat=n=3:v=1:a=0[out]')
        trimmed = workdir / 'trimmed.webm'
        recorder.run(['ffmpeg', '-y', '-i', str(composite), '-filter_complex', filters, '-map', '[out]',
                      '-an', '-c:v', 'libvpx-vp9', str(trimmed)], 'trim final composite', heavy=True)
        composite = trimmed
    limits = plan.get('limits', {})
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json',
                            str(composite)], check=True, capture_output=True, text=True, timeout=30)
    composite_s = float(json.loads(probe.stdout)['format']['duration'])
    speed = max(1.0, composite_s / FIT_SECONDS)
    if speed > 1.0:
        print(f'Composite runs {composite_s:.1f} s; speeding up {speed:.2f}x to fit {FIT_SECONDS:.0f} s')
    recorder.run(helpers.transcode_command(composite, Path(out), limits.get('long_side_px', 720),
                                           limits.get('crf', 41), speed), 'hub demo limits', heavy=True)
    helpers.check_size(out)
    if plan['ocr'] and recorder.ocr_gate(Path(out), workdir, patterns):
        Path(out).unlink(missing_ok=True)
        raise RuntimeError('OCR privacy gate failed')
    if not plan['ocr']:
        print('Warning: OCR disabled; review the recording before sharing')
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(out)],
                           check=True, capture_output=True, text=True, timeout=30)
    data = json.loads(probe.stdout)
    video = next(stream for stream in data['streams'] if stream['codec_type'] == 'video')
    metrics = {'codec': video['codec_name'], 'width': video['width'], 'height': video['height'],
               'audio': any(stream['codec_type'] == 'audio' for stream in data['streams']),
               'duration_s': float(data['format']['duration']), 'size_bytes': Path(out).stat().st_size}
    (workdir / 'metrics.json').write_text(json.dumps(metrics))
    print(json.dumps(metrics))


FIT_SECONDS = 29.5   # hub cap is 30 s; leave room for container rounding


def fit_timeline(spec, recorder, capture_s):
    """Make the composite cover the whole capture instead of the planned timeline.

    A real agent session runs 30 to 60 s, but the plan's timeline ends at a fixed
    ~26 s and record_demo trims the composite to timeline_end. Stretch the timeline
    to the measured capture (caption times scale with it) so nothing is cut; the
    transcode then speeds the clip up uniformly to fit the 30 s cap.
    """
    planned = recorder.timeline_end(spec)
    if not capture_s or capture_s <= planned:
        return spec
    last_t = float(spec['timeline'][-1]['t'])
    if last_t <= 0:
        return spec
    scale = (capture_s - (planned - last_t)) / last_t   # last step's own tail stays as is
    spec = dict(spec)
    spec['timeline'] = [dict(step, t=round(float(step['t']) * scale, 2)) for step in spec['timeline']]
    print(f'Timeline stretched {planned:.1f} s -> {recorder.timeline_end(spec):.1f} s to cover the capture')
    return spec


def remote_main(argv):
    import argparse
    import shutil
    parser = argparse.ArgumentParser(description='Render-host stages for split skill demos')
    parser.add_argument('--check-tools', action='store_true')
    parser.add_argument('--no-ocr', action='store_true')
    parser.add_argument('--phone-start')
    parser.add_argument('--phone-stop')
    parser.add_argument('--compose-plan')
    parser.add_argument('--external-cast')
    parser.add_argument('--phone-video')
    parser.add_argument('--workdir')
    parser.add_argument('--out')
    parser.add_argument('--cleanup')
    args = parser.parse_args(argv)
    if args.check_tools:
        required = ['adb', 'agg', 'ffmpeg', 'ffprobe'] + ([] if args.no_ocr else ['tesseract'])
        print(json.dumps({'missing': [tool for tool in required if not shutil.which(tool)]}))
        return 0
    if args.cleanup:
        directory = Path(args.cleanup)
        # Cleanup can delete only a single generated directory immediately in /tmp.
        if directory.parent != Path('/tmp') or not directory.name.startswith('ghost-demo-') or directory.is_symlink():
            raise ValueError('Refusing cleanup outside a generated /tmp/ghost-demo-* directory')
        if (directory / 'phone-state.json').exists():
            remote_phone_stop({}, directory, pull=False)
        shutil.rmtree(directory, ignore_errors=True)
        return 0
    if not args.workdir:
        parser.error('--workdir is required')
    if args.phone_start:
        remote_phone_start(read_plan(args.phone_start), args.workdir)
    elif args.phone_stop:
        remote_phone_stop(read_plan(args.phone_stop), args.workdir)
    elif args.compose_plan:
        if not all([args.external_cast, args.phone_video, args.out]):
            parser.error('--compose-plan requires --external-cast, --phone-video and --out')
        compose_existing(read_plan(args.compose_plan), args.external_cast, args.phone_video, args.out, args.workdir)
    else:
        parser.error('Select a remote stage')
    return 0


def main(argv=None):
    import argparse
    sys.path.insert(0, str(REPO_ROOT))
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(option in argv for option in ('--check-tools', '--phone-start', '--phone-stop', '--compose-plan', '--cleanup')):
        return remote_main(argv)
    from gitd.skills.engine.cli import cmd_demo
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill_dir')
    parser.add_argument('--serial', required=True)
    parser.add_argument('--out', help='Output directory; single selected action only')
    parser.add_argument('--action')
    parser.add_argument('--dry', action='store_true')
    args, extra = parser.parse_known_args(argv)
    command = [args.skill_dir, '--device', args.serial] + extra
    if args.action:
        command.extend(['--action', args.action])
    if args.out:
        if not args.action:
            parser.error('--out requires --action')
        command.extend(['--out', str(Path(args.out) / f'{args.action}.webm')])
    if args.dry:
        command.append('--dry')
    return cmd_demo(command)


if __name__ == '__main__':
    raise SystemExit(main())
