#!/usr/bin/env python3
"""Run a skill action or workflow from the job queue."""
import argparse
import json
import sys
import time as _time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gitd.bots.common.adb import Device


# ── Skill run tracking ──────────────────────────────────────────────────

def _record_start(device: str, skill: str, target_type: str, target_name: str,
                  params: dict, is_verify: bool = False) -> int | None:
    """Insert a skill_runs row at start. Returns row id or None on error."""
    try:
        from gitd.models.base import SessionLocal
        from gitd.models.skill_compat import SkillRun
        db = SessionLocal()
        # Try to get app version
        app_ver = None
        try:
            import yaml
            meta_path = Path(__file__).parent / skill / 'skill.yaml'
            if meta_path.exists():
                meta = yaml.safe_load(meta_path.read_text()) or {}
                pkg = meta.get('app_package')
                if pkg:
                    app_ver = Device(device).get_app_version(pkg)
        except Exception:
            pass
        row = SkillRun(
            device_serial=device, skill_name=skill,
            target_type=target_type, target_name=target_name,
            app_version=app_ver, status='running',
            params_json=json.dumps(params) if params else None,
            is_verify=1 if is_verify else 0,
        )
        db.add(row)
        db.commit()
        rid = row.id
        db.close()
        return rid
    except Exception as e:
        print(f'[tracking] start failed: {e}', file=sys.stderr)
        return None


def _record_finish(run_id: int | None, success: bool, duration_ms: float,
                   error: str | None = None):
    """Update skill_runs row and upsert skill_compat aggregate."""
    if run_id is None:
        return
    try:
        from sqlalchemy import text as sql_text
        from gitd.models.base import SessionLocal
        from gitd.models.skill_compat import SkillRun
        db = SessionLocal()
        row = db.get(SkillRun, run_id)
        if row:
            row.status = 'ok' if success else 'fail'
            row.duration_ms = duration_ms
            row.error_msg = error[:500] if error else None
            row.finished_at = db.execute(sql_text("SELECT datetime('now')")).scalar()
            db.commit()
            # Upsert skill_compat aggregate
            _upsert_compat(db, row)
        db.close()
    except Exception as e:
        print(f'[tracking] finish failed: {e}', file=sys.stderr)


def _upsert_compat(db, run):
    """Update the skill_compat aggregate row for this device+skill+target."""
    from sqlalchemy import text as sql_text
    from gitd.models.skill_compat import SkillCompat
    row = db.query(SkillCompat).filter_by(
        device_serial=run.device_serial, skill_name=run.skill_name,
        target_type=run.target_type, target_name=run.target_name,
    ).first()
    now = db.execute(sql_text("SELECT datetime('now')")).scalar()
    if row:
        row.run_count += 1
        if run.status == 'ok':
            row.ok_count += 1
        else:
            row.fail_count += 1
        row.status = run.status
        row.app_version = run.app_version
        row.last_run_at = now
        row.last_error = run.error_msg if run.status == 'fail' else row.last_error
    else:
        row = SkillCompat(
            device_serial=run.device_serial, skill_name=run.skill_name,
            target_type=run.target_type, target_name=run.target_name,
            app_version=run.app_version, status=run.status,
            last_run_at=now,
            last_error=run.error_msg if run.status == 'fail' else None,
            run_count=1,
            ok_count=1 if run.status == 'ok' else 0,
            fail_count=1 if run.status == 'fail' else 0,
        )
        db.add(row)
    db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skill', required=True)
    parser.add_argument('--workflow', default='')
    parser.add_argument('--action', default='')
    parser.add_argument('--device', required=True)
    parser.add_argument('--params', default='{}')
    parser.add_argument('--verify', action='store_true', help='Mark as verification run')
    # Engine config overrides
    parser.add_argument('--back-count', type=int, default=None, help='Back presses during reset (default: 10)')
    parser.add_argument('--no-launch', action='store_true', help='Skip wake/home/launch startup')
    parser.add_argument('--no-popup', action='store_true', help='Skip popup detection between steps')
    parser.add_argument('--step-settle', type=float, default=None, help='Extra sleep after each step (seconds)')
    parser.add_argument('--launch-settle', type=float, default=None, help='Sleep after app launch (seconds)')
    args = parser.parse_args()

    import importlib
    import time

    params = json.loads(args.params)
    dev = Device(args.device)

    # Build engine config from CLI flags
    from gitd.skills.base import EngineConfig
    engine_overrides = {}
    if args.back_count is not None:
        engine_overrides['back_count'] = args.back_count
    if args.no_launch:
        engine_overrides['auto_launch'] = False
    if args.no_popup:
        engine_overrides['skip_popup_detect'] = True
    if args.step_settle is not None:
        engine_overrides['step_settle'] = args.step_settle
    if args.launch_settle is not None:
        engine_overrides['launch_settle'] = args.launch_settle
    engine_cfg = EngineConfig(**engine_overrides) if engine_overrides else None

    target_type = 'workflow' if args.workflow else 'action'
    target_name = args.workflow or args.action
    run_id = _record_start(args.device, args.skill, target_type, target_name, params, is_verify=args.verify)
    t0 = _time.time()

    # Check for recorded skill (has workflows/recorded.json instead of Python classes)
    skill_dir = Path(__file__).parent / args.skill
    recorded_path = skill_dir / 'workflows' / 'recorded.json'
    if args.workflow == 'recorded' and recorded_path.exists():
        from gitd.skills.base import RecordedWorkflow
        import yaml

        steps = json.loads(recorded_path.read_text())
        print(f'Running {len(steps)} recorded steps for {args.skill} through execution engine')

        wf = RecordedWorkflow(dev, steps, params)
        # Load popup detectors + app_package from skill.yaml
        meta_path = skill_dir / 'skill.yaml'
        if meta_path.exists():
            meta = yaml.safe_load(meta_path.read_text()) or {}
            wf.app_package = meta.get('app_package', '') or ''
            wf._popup_detectors = meta.get('popup_detectors') or None
        if engine_cfg:
            wf.engine = engine_cfg

        result = wf.run()
        dur = (_time.time() - t0) * 1000
        _record_finish(run_id, result.success, dur, result.error)
        print(f'Result: success={result.success} duration={result.duration_ms:.0f}ms')
        if result.error:
            print(f'Error: {result.error}')
        sys.exit(0 if result.success else 1)

    # Load skill dynamically
    try:
        mod = importlib.import_module(f'gitd.skills.{args.skill}')
        s = mod.load()
    except (ImportError, AttributeError) as e:
        dur = (_time.time() - t0) * 1000
        _record_finish(run_id, False, dur, str(e))
        print(f'Cannot load skill "{args.skill}": {e}', file=sys.stderr)
        sys.exit(1)

    print(f'Loaded skill: {s.name}')

    if args.workflow:
        wf = s.get_workflow(args.workflow, dev, **params)
        if not wf:
            dur = (_time.time() - t0) * 1000
            _record_finish(run_id, False, dur, f'Workflow not found: {args.workflow}')
            print(f'Workflow not found: {args.workflow}', file=sys.stderr)
            sys.exit(1)
        if engine_cfg:
            wf.engine = engine_cfg
        print(f'Running workflow: {args.workflow} (back_count={wf.engine.back_count})')
        result = wf.run()
        dur = (_time.time() - t0) * 1000
        _record_finish(run_id, result.success, dur, result.error)
        print(f'Result: success={result.success} duration={result.duration_ms}ms')
        if result.error:
            print(f'Error: {result.error}')
        if result.data:
            print(f'Data: {json.dumps(result.data, default=str)}')
        sys.exit(0 if result.success else 1)

    elif args.action:
        action_cls = s.get_action(args.action)
        if not action_cls:
            dur = (_time.time() - t0) * 1000
            _record_finish(run_id, False, dur, f'Action not found: {args.action}')
            print(f'Action not found: {args.action}', file=sys.stderr)
            sys.exit(1)
        print(f'Running action: {args.action}')
        action = action_cls(dev, s.elements, **params)
        result = action.run()
        dur = (_time.time() - t0) * 1000
        _record_finish(run_id, result.success, dur, result.error)
        print(f'Result: success={result.success} duration={result.duration_ms}ms')
        if result.error:
            print(f'Error: {result.error}')
        sys.exit(0 if result.success else 1)

    else:
        print('Must specify --workflow or --action', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
