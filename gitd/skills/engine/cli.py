"""ghost skill CLI — subcommand handlers for the skill lifecycle.

Wired from gitd/ghost_cli.py (top-level `ghost` binary):
    ghost skill scaffold <user>/<slug> [--app PKG] [--actions a,b,c]
    ghost skill validate <path>
    ghost skill test <path> [--live] [--action <name>] [--param k=v ...]
    ghost skill run <path> <action> [--param k=v ...] [--device SERIAL]
    ghost skill migrate <v1-path>
    ghost skill submit <path>              # gh fork + branch + PR
    ghost skill list-registered            # show all step + validator kinds
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from gitd.skills import hub
from gitd.skills.engine import load_skill, run_action
from gitd.skills.engine.dispatch import registered_steps
from gitd.skills.engine.errors import SchemaError, SkillError
from gitd.skills.engine.validators import registered_kinds
from gitd.skills.hub import HubError


def _print_ok(msg: str) -> None:
    print(f"\033[32m✓\033[0m {msg}")


def _print_err(msg: str) -> None:
    print(f"\033[31m✗\033[0m {msg}", file=sys.stderr)


def _print_warn(msg: str) -> None:
    print(f"\033[33m⚠\033[0m {msg}")


# ── scaffold ────────────────────────────────────────────────────────────────


def cmd_scaffold(argv: list[str]) -> int:
    """Create a new skill dir skeleton at skillhub/<user>/<slug>/."""
    p = argparse.ArgumentParser(prog="ghost skill scaffold", add_help=True)
    p.add_argument("ref", help="<user>/<slug> — e.g. alice/whatsapp-messaging")
    p.add_argument("--app", default="", help="Android package name")
    p.add_argument("--skill-class", default="hard", choices=["hard", "soft"])
    p.add_argument("--actions", default="", help="Comma-separated action names")
    p.add_argument("--official", action="store_true", help="Create under skillhub/ghost/ (maintainer only)")
    args = p.parse_args(argv)

    if "/" not in args.ref:
        _print_err(f"ref must be <user>/<slug>, got {args.ref!r}")
        return 2
    user, slug = args.ref.split("/", 1)

    base = Path("skillhub") / ("ghost" if args.official else user) / slug
    if base.exists():
        _print_err(f"Path already exists: {base}")
        return 2

    # v2 layout: everything the skill needs in a flat `helpers.py` next to skill.yaml.
    # No actions/ or workflows/ dirs — those were v1 conventions. `helpers.py` holds
    # `python_action:` targets (regular Python functions with signature
    # (device, params, context) -> dict | ActionResult).
    action_names = [a.strip() for a in args.actions.split(",") if a.strip()] or ["main"]

    base.mkdir(parents=True)
    (base / "helpers.py").write_text(_render_helpers_stub(slug, action_names))
    (base / "skill.yaml").write_text(
        _render_skill_yaml(args.ref, slug, args.app, args.skill_class, action_names, args.official)
    )
    (base / "SOFT.md").write_text(_render_soft_md(slug, args.app, action_names))
    (base / "README.md").write_text(_render_readme(args.ref, slug, action_names))

    _print_ok(f"Scaffolded {base}/")
    print(f"  Next: edit skill.yaml, then `ghost skill validate {base}` + `ghost skill test {base} --live`")
    return 0


def _render_skill_yaml(ref: str, slug: str, app: str, sk_class: str, actions: list[str], official: bool) -> str:
    user = "ghost" if official else ref.split("/", 1)[0]
    action_yaml = "\n".join(
        f"""  - name: {a}
    description: "TODO: what does {a} do"
    ref_prompt: "TODO: canonical natural-language phrase that triggers this action"
    params: []
    steps:
      - {{action: launch_app, package: {app or "com.example"}}}
      - {{action: sleep, duration_s: 2}}
      # TODO: real steps
    end_state_validator:
      all_of:
        - {{kind: text_visible, text: "TODO: expected terminal-state text"}}
    test_case:
      ref_prompt_variants:
        - "TODO: variant 1"
        - "TODO: variant 2"
      expected_success: true
"""
        for a in actions
    )
    return f"""name: {slug}
version: 0.1.0
author: {user}
description: "TODO: 1-line what this skill does"
skill_class: {sk_class}
license: MIT             # SPDX id (required)
generated_with: "TODO: human, or the model/tool that authored this skill"   # required
side_effects: []         # sends_message | posts_content | makes_payment | modifies_account | deletes_data | none
destructive: false       # true requires a confirm_before: gate or a dry_run param
tos_risk: low            # low | medium | high
locale: []               # BCP-47 tags tested, e.g. [en-US]
data_access: []          # TODO: declare (contacts, sms, camera, mic, location, notifications, clipboard, files, storage)

fingerprint:
  os: android
  os_version: ">=13"
  hardware: "*"
  app_package: {app or "com.example.app"}
  app_version: ">=1.0.0"

repo_url: "https://github.com/ghost-in-the-droid/android-agent"
skill_path: "skillhub/{user}/{slug}"

popup_detectors: []      # add app-specific popups as you discover them

actions:
{action_yaml}
"""


def _render_helpers_stub(slug: str, actions: list[str]) -> str:
    stubs = "\n\n".join(
        f'''def {a}_helper(device, params, context):
    """python_action target for the {a!r} action. Delete if not needed."""
    # TODO: implement — scrape / parse / prepare state that YAML primitives can't express.
    # See docs/skill-schema-v2.md for python_action contract.
    from gitd.skills.base import ActionResult
    return ActionResult(success=True, data={{}})'''
        for a in actions
    )
    return f'''"""python_action target functions for the {slug} skill.

Each function has signature (device, params, context) -> dict | ActionResult.
Return a plain payload dict to merge its keys into context.result, or return
ActionResult(success=True, data=payload). Dicts containing success, error or data
are result envelopes: put payload fields (including reserved names) under data.
Referenced from skill.yaml as `python_action: helpers:<fn>` (resolved by file
path relative to the skill dir).
"""
from __future__ import annotations


{stubs}
'''


def _render_soft_md(slug: str, app: str, actions: list[str]) -> str:
    lines = [
        f"# {slug} — SOFT skill (LLM-adaptable narrative)",
        "",
        "This document describes the skill at a semantic level — what each action does,",
        "what it depends on, and how to recognize success. LLMs use this to adapt the",
        "skill to a device/app-version the shipped hard-skill doesn't match.",
        "",
        f"**Package**: `{app or 'com.example.app'}`",
        "",
        "## Actions",
        "",
    ]
    for a in actions:
        lines.append(f"### `{a}()`")
        lines.append("")
        lines.append("TODO: describe the semantic goal, expected UI landmarks, success signals.")
        lines.append("")
    return "\n".join(lines)


def _render_readme(ref: str, slug: str, actions: list[str]) -> str:
    actions_bullets = "\n".join(f"- `{a}` — TODO" for a in actions)
    return f"""# {slug}

Ghost in the Droid skill: TODO 1-line summary.

## Actions

{actions_bullets}

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # For an unpublished checkout, use `pip install -e .` instead.
ghost skill install {ref}
```

## Use

```bash
ghost skill run {ref} <action> --device <serial>
```
"""


# ── validate ────────────────────────────────────────────────────────────────


def cmd_validate(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ghost skill validate", add_help=True)
    p.add_argument("path", help="Skill directory (containing skill.yaml)")
    args = p.parse_args(argv)

    try:
        skill = load_skill(args.path)
    except SchemaError as e:
        _print_err(f"Schema error: {e.message}")
        if e.hint:
            print(f"  hint: {e.hint}")
        return 1
    except FileNotFoundError as e:
        _print_err(str(e))
        return 1

    _print_ok("skill.yaml parses + validates Schema v2")
    _print_ok(f"  name: {skill.name} v{skill.version} ({skill.skill_class})")
    _print_ok(f"  actions ({len(skill.actions)}): {skill.action_names()}")
    _print_ok(f"  popup_detectors: {len(skill.popup_detectors)}")
    for w in skill.warnings:
        _print_warn(w)

    # Import checks for python_action targets
    problems = 0
    for a in skill.actions:
        for step in a.steps + a.pre_hooks:
            ref = step.get("python_action") if isinstance(step, dict) else None
            if ref:
                if not _check_import(ref, skill):
                    _print_err(f"  action {a.name!r}: python_action {ref!r} — cannot import")
                    problems += 1
        # end_state_validator custom_python
        for v in _iter_validator_leaves(a.end_state_validator):
            if v.get("kind") == "custom_python":
                ref = v.get("function", "")
                if ref and not _check_import(ref, skill):
                    _print_err(f"  action {a.name!r}: end_state_validator custom_python {ref!r} — cannot import")
                    problems += 1
    if problems:
        _print_err(f"{problems} import problem(s)")
        return 1
    _print_ok("all python_action + custom_python refs resolve")
    return 0


def _iter_validator_leaves(spec):
    if not spec:
        return
    if isinstance(spec, list):
        for s in spec:
            yield from _iter_validator_leaves(s)
        return
    if not isinstance(spec, dict):
        return
    if "all_of" in spec:
        yield from _iter_validator_leaves(spec["all_of"])
    elif "any_of" in spec:
        yield from _iter_validator_leaves(spec["any_of"])
    elif "not" in spec:
        yield from _iter_validator_leaves(spec["not"])
    elif "kind" in spec:
        yield spec


def _check_import(ref: str, skill) -> bool:
    """Verify skill-local `<file>:<fn>` resolves (file path import, see engine/pyimport.py)."""
    from gitd.skills.engine.pyimport import resolve_for_skill

    try:
        resolve_for_skill(ref, skill)
        return True
    except Exception:
        return False


# ── test / run ──────────────────────────────────────────────────────────────


def cmd_test(argv: list[str]) -> int:
    """Dry-run validate + optional live run against a device."""
    p = argparse.ArgumentParser(prog="ghost skill test", add_help=True)
    p.add_argument("path", help="Skill directory")
    p.add_argument("--live", action="store_true", help="Actually run against a device (default: dry)")
    p.add_argument("--action", default="", help="Just this one action (default: all)")
    p.add_argument("--param", action="append", default=[], help="k=v param for the action (repeatable)")
    p.add_argument(
        "--device",
        default=os.environ.get("GHOST_DEVICE") or os.environ.get("DEFAULT_DEVICE", ""),
        help="Device serial, ios:<udid>, or fake:<fixture-dir>",
    )
    p.add_argument("--fingerprint", help="Concrete device fingerprint JSON file (required for iOS recording)")
    p.add_argument(
        "--record", action="store_true", help="Write signed evidence for the live runs (default: no artifacts)"
    )
    args = p.parse_args(argv)

    # Dry run — schema + imports
    rc = cmd_validate([args.path])
    if rc != 0:
        return rc
    if not args.live:
        _print_ok("dry-run complete. Use --live to run on device.")
        return 0

    if not args.device:
        _print_err("--live requires --device <serial>")
        return 2

    skill = load_skill(args.path)
    actions = [args.action] if args.action else skill.action_names()
    params = _parse_params(args.param)

    from gitd.skills.engine.evidence import collect_fingerprint, write_evidence

    fingerprint = collect_fingerprint(skill, args.device, args.fingerprint) if args.record else None
    failed = 0
    results = []
    for name in actions:
        print(f"Running {name}")
        action_params = dict(params)
        try:
            r = run_action(skill, name, params=action_params, device_serial=args.device)
        except Exception as e:
            _print_err(f"{name}: crashed: {e}")
            failed += 1
            continue
        results.append(r)
        if r.success:
            _print_ok(f"{name} ({r.duration_ms:.0f}ms): {json.dumps(r.data, default=str)[:200]}")
        else:
            _print_err(f"{name} ({r.duration_ms:.0f}ms): {r.error['kind']}: {r.error['message']}")
            failed += 1
    if results and args.record:
        from gitd.skills.engine.evidence import detect_emulator

        artifact = write_evidence(
            skill,
            results,
            fingerprint,
            simulated=args.device.startswith("fake:"),
            emulator=detect_emulator(args.device),
        )
        print(f"Run artifact: {artifact}")
    return 1 if failed else 0


def cmd_demo(argv: list[str]) -> int:
    """Record a skill action using the original Ghost agent showcase format."""
    from gitd.skills.engine import demo

    args = demo.parser().parse_args(argv)
    if any("=" not in item for item in args.param):
        raise ValueError("--param must be k=v")
    if not args.dry and not args.render_host:
        raise ValueError("--render-host or GHOST_DEMO_RENDER_HOST is required; local encoding is disabled")
    demo.select_agent(args)
    plans = demo.build_plans(load_skill(args.ref), args, _parse_params(args.param))
    recorder = demo.load_recorder()
    for plan in plans:
        errors = demo.validate_plan(plan, recorder)
        if errors:
            raise ValueError("; ".join(errors))
    missing = demo.tool_check(plans[0])
    for tool, hint in missing:
        _print_warn(f"Missing {tool}: {hint}")
    if args.dry:
        for plan in plans:
            demo.print_plan(plan)
        return 0
    if missing:
        raise RuntimeError("Required recording tools are missing; use --dry to inspect the plan")
    for plan in plans:
        print(f"Recording action: {plan['action']}", flush=True)
        code = demo.record(plan, recorder)
        if code:
            return code
    return 0


def cmd_run(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ghost skill run", add_help=True)
    p.add_argument("path", help="Skill dir OR skill slug like ghost/tiktok")
    p.add_argument("action", help="Action name")
    p.add_argument("--param", action="append", default=[])
    p.add_argument(
        "--secret-env",
        action="append",
        default=[],
        metavar="PARAM=ENV",
        help="Read a secret from a local environment variable",
    )
    p.add_argument("--state-param", action="append", default=[], metavar="ACTION.PARAM=VALUE")
    p.add_argument("--state-secret-env", action="append", default=[], metavar="ACTION.PARAM=ENV")
    p.add_argument(
        "--device", default=os.environ.get("GHOST_DEVICE") or os.environ.get("DEFAULT_DEVICE", ""), help="Device serial"
    )
    p.add_argument("--live-trace", action="store_true", help="Print each step as it completes")
    p.add_argument("--record", action="store_true", help="Write locally signed evidence in the skill runs directory")
    p.add_argument("--fingerprint", help="Concrete device fingerprint JSON file (required for iOS recording)")
    p.add_argument(
        "--strict-fingerprint",
        action="store_true",
        help="Require fingerprint distance 0 (default: warn at 1-2, refuse at 3+)",
    )
    p.add_argument("--force-fingerprint", action="store_true", help="Run even at fingerprint distance 3+")
    p.add_argument("--no-fingerprint-check", action="store_true", help="Skip the device fingerprint probe")
    args = p.parse_args(argv)

    if not args.device:
        _print_err("--device required (or set DEFAULT_DEVICE env)")
        return 2

    skill = load_skill(args.path)
    params = _parse_params(args.param)
    secret_params = _env_params(args.secret_env)
    if any(
        not skill.action(args.action).param(k) or not skill.action(args.action).param(k).secret for k in secret_params
    ):
        raise ValueError("--secret-env requires a param declared secret: true")
    params.update(secret_params)
    state_values = _parse_params(args.state_param)
    state_secrets = _env_params(args.state_secret_env)
    state_values.update(state_secrets)
    state_params = {}
    for key, value in state_values.items():
        if "." not in key:
            raise ValueError("State params require ACTION.PARAM")
        provider, param = key.split(".", 1)
        if skill.action(provider).param(param) is None:
            raise ValueError("Unknown provider parameter")
        if key in state_secrets and not skill.action(provider).param(param).secret:
            raise ValueError("--state-secret-env requires a param declared secret: true")
        state_params.setdefault(provider, {})[param] = value
    fingerprint = None
    if args.record:
        from gitd.skills.engine.evidence import collect_fingerprint

        fingerprint = collect_fingerprint(skill, args.device, args.fingerprint)
    run_options = {"state_params": state_params} if state_params else {}
    if args.live_trace:
        action_def = skill.action(args.action)
        print(f"Prompt: {action_def.ref_prompt}", flush=True)
        print(
            "Parameters: "
            + json.dumps(
                {
                    k: "[REDACTED]" if action_def.param(k) and action_def.param(k).secret else v
                    for k, v in params.items()
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        def progress(entry):
            step = entry.step
            primitive = step.get("action") or next(iter(step), "unknown")
            arguments = {key: value for key, value in step.items() if key != "action"}
            print(
                f"{entry.step_index}: {primitive} {json.dumps(arguments, default=str, ensure_ascii=False)} "
                f"{entry.duration_ms:.0f} ms {'✗' if entry.error else '✓'}",
                flush=True,
            )

        run_options["progress_callback"] = progress
    report = None
    if not args.no_fingerprint_check:
        from gitd.skills.engine.fingerprint import check as check_fingerprint

        try:
            supplied = json.loads(Path(args.fingerprint).read_text()) if args.fingerprint else None
            report = check_fingerprint(
                skill,
                args.device,
                strict=args.strict_fingerprint,
                force=args.force_fingerprint,
                device_fingerprint=supplied,
            )
        except ValueError as exc:
            _print_err(str(exc))
            return 2
        if report is not None and report.distance:
            _print_err(f"Warning: {report.summary()}; proceeding, the skill may fail.")
    r = run_action(skill, args.action, params=params, device_serial=args.device, **run_options)
    if report is not None:
        r.fingerprint = report.as_dict()
    if args.live_trace:
        validator_failed = (r.error or {}).get("kind") == "validator_failed"
        validator_status = "passed" if r.success else "failed" if validator_failed else "not reached"
        print(f"End-state validator: {validator_status}", flush=True)

    if args.record:
        from gitd.skills.engine.evidence import detect_emulator, write_evidence

        artifact = write_evidence(
            skill, [r], fingerprint, simulated=args.device.startswith("fake:"), emulator=detect_emulator(args.device)
        )
        print(f"Run artifact: {artifact}")
        from gitd.ghostcli.telemetry_transport import send_run

        send_run(skill, r, fingerprint, simulated=args.device.startswith("fake:"))

    if getattr(r, "status", "") in {"needs_input", "needs_state"}:
        print(json.dumps(r.as_dict(), indent=2, default=str))
        return 0 if r.status == "needs_input" else 1
    if r.success:
        _print_ok(f"{args.action} ({r.duration_ms:.0f}ms)")
        print(json.dumps(r.data, indent=2, default=str))
        return 0
    else:
        _print_err(f"{r.error['kind']}: {r.error['message']}")
        if r.error.get("hint"):
            print(f"  hint: {r.error['hint']}")
        print("\nTrace:")
        for t in r.trace:
            mark = "✗" if t.error else "✓"
            print(f"  {mark} step[{t.step_index}] {t.duration_ms:6.0f}ms  {list(t.step.keys())[:2]}")
            if t.error:
                print(f"    → {t.error}")
        return 1


def _env_params(items):
    """Explicit environment lookups only: no prompt and no secret values in argv."""
    values = {}
    for item in items:
        if "=" not in item:
            raise ValueError("Secret environment bindings require PARAM=ENV")
        param, variable = item.split("=", 1)
        if not variable or not os.environ.get(variable):
            raise ValueError("Required secret environment variable is missing or empty")
        values[param] = os.environ[variable]
    return values


def cmd_probe(argv):
    """Read a deterministic skill state: true, false, or unknown."""
    from .runner import _get_device
    from .state import probe_state

    parser = argparse.ArgumentParser(prog="ghost skill probe")
    parser.add_argument("skill")
    parser.add_argument("state")
    parser.add_argument("--device", default=os.environ.get("GHOST_DEVICE") or os.environ.get("DEFAULT_DEVICE", ""))
    args = parser.parse_args(argv)
    skill = load_skill(args.skill)
    try:
        value = probe_state(skill, args.state, _get_device(args.device))
    except Exception:
        value = None
    print("unknown" if value is None else str(value).lower())
    return 0


def _parse_params(args: list[str]) -> dict:
    """Keep CLI values lossless; the runner coerces each action's declared type."""
    out = {}
    for arg in args:
        if "=" not in arg:
            continue
        k, v = arg.split("=", 1)
        out[k] = v
    return out


# ── list-registered ─────────────────────────────────────────────────────────


def cmd_list_registered(argv: list[str]) -> int:
    print("Step primitives:")
    for s in registered_steps():
        print(f"  - {s}")
    print("\nValidator kinds:")
    for k in registered_kinds():
        print(f"  - {k}")
    return 0


# ── submit (gh wrapper) ─────────────────────────────────────────────────────


def _parser(command, path=False):
    parser = argparse.ArgumentParser(prog=f"ghost skill {command}")
    if path:
        parser.add_argument("path")
    return parser


def _plain(value):
    from dataclasses import asdict, is_dataclass

    if isinstance(value, hub.InstalledSkill):
        return value.as_dict()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return vars(value)
    return value


def _show_rows(rows):
    print("REF  VERSION  TRUST  PATH")
    for row in rows:
        row = _plain(row)
        if isinstance(row, dict):
            ref = row.get("ref") or f"{row.get('author', '')}/{row.get('slug', row.get('name', ''))}"
            print(
                f"{ref}  {row.get('version', row.get('latest', ''))}  {row.get('trust', 'unknown')}  {row.get('path', row.get('skill_dir', ''))}"
            )
        else:
            print(row)


def _confirm_install(prompt):
    try:
        return input(prompt).strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def cmd_install(argv):
    """Install an author/slug reference from the hub."""
    p = _parser("install")
    p.add_argument("ref")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--url")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    _show_rows([hub.install(args.ref, source=args.url, force=args.force, yes=args.yes, confirm=_confirm_install)])
    return 0


def cmd_uninstall(argv):
    """Uninstall an installed skill reference."""
    p = _parser("uninstall")
    p.add_argument("ref")
    args = p.parse_args(argv)
    hub.uninstall(args.ref)
    print(f"Uninstalled {args.ref}")
    return 0


def cmd_update(argv):
    """Update one skill or all installed skills."""
    p = _parser("update")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("ref", nargs="?")
    group.add_argument("--all", action="store_true")
    p.add_argument("--yes", action="store_true")
    args = p.parse_args(argv)
    refs = [args.ref]
    if args.all:
        refs = []
        for item in hub.list_installed():
            row = _plain(item)
            ref = row.get("ref") or f"{row['author']}/{row.get('slug', row.get('name'))}"
            ref = ref.split("@")[0]
            if ref not in refs:
                refs.append(ref)
    for ref in refs:
        updated = hub.update(ref, yes=args.yes, confirm=_confirm_install)
        if updated is None:
            print(f"{ref}: up to date")
        else:
            _show_rows([updated])
    return 0


def cmd_outdated(argv):
    """Show installed skills with newer hub versions."""
    _parser("outdated").parse_args(argv)
    print("REF  INSTALLED  LATEST")
    for row in hub.outdated():
        print(f"{row['ref']}  {row['installed']}  {row['latest']}")
    return 0


def cmd_list(argv):
    """List installed skill versions, trust, and paths."""
    _parser("list").parse_args(argv)
    _show_rows(hub.list_installed())
    return 0


def _registry():
    """Read a checkout registry, otherwise fetch the published registry."""
    override = os.environ.get("GHOST_HUB_REGISTRY")
    if override:
        return json.loads(Path(override).read_text())
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "skillhub" / "registry.json"
        if candidate.is_file():
            return json.loads(candidate.read_text())
    from urllib.request import urlopen

    repo = os.environ.get("GHOST_HUB_REPO", "ghost-in-the-droid/android-agent")
    last = None
    for url in (
        f"https://cdn.jsdelivr.net/gh/{repo}@main/skillhub/registry.json",
        f"https://raw.githubusercontent.com/{repo}/main/skillhub/registry.json",
    ):
        try:
            with urlopen(url, timeout=20) as response:
                return json.load(response)
        except (OSError, ValueError) as exc:
            last = exc
    raise RuntimeError(f"Cannot fetch Skill Hub registry: {last}")


def cmd_search(argv):
    """Search hub names, descriptions, actions, and app packages."""
    p = _parser("search")
    p.add_argument("query")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    matches = {}
    for ref, entry in _registry()["skills"].items():
        values = [ref, entry.get("name", ""), entry.get("description", "")]
        for version in entry.get("versions", {}).values():
            values.extend(version.get("actions", []))
            values.append(version.get("fingerprint", {}).get("app_package", ""))
        if args.query.casefold() in " ".join(values).casefold():
            matches[ref] = entry
    if args.json:
        print(json.dumps(matches, indent=2))
    else:
        print("REF  VERSION  TRUST  TIER  DESCRIPTION")
        for ref, entry in matches.items():
            print(
                f"{ref}  {entry.get('latest', '')}  {entry.get('trust', '')}  {entry.get('quality', {}).get('tier', '')}  {entry.get('description', '')}"
            )
    return 0


def cmd_find(argv):
    """Find the skill action for an intent (BM25 over names, descriptions, ref prompts, app package)."""
    from gitd.skills.engine.find import as_dict, docs_from_dirs, docs_from_registry, rank
    from gitd.skills.hub import list_installed
    from gitd.skills.locations import find_skillhub_root

    p = _parser("find")
    p.add_argument("intent")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-hub", action="store_true", help="search only installed and checkout skills")
    args = p.parse_args(argv)
    latest = {}
    for installed in list_installed():
        latest[installed.key] = installed  # list_installed is version-sorted, so the last one wins
    docs = docs_from_dirs([(key, s.path) for key, s in latest.items()], "installed")
    hub = find_skillhub_root(Path.cwd())
    if hub is not None:
        checkout = []
        for author_dir in sorted(d for d in hub.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))):
            for slug_dir in sorted(d for d in author_dir.iterdir() if d.is_dir() and (d / "skill.yaml").is_file()):
                ref = f"{author_dir.name}/{slug_dir.name}"
                if ref not in latest:
                    checkout.append((ref, slug_dir))
        docs.extend(docs_from_dirs(checkout, "checkout"))
    if not args.no_hub:
        try:
            docs.extend(docs_from_registry(_registry(), exclude={d.skill for d in docs}))
        except RuntimeError as exc:
            _print_err(f"Hub registry unavailable, searching local skills only: {exc}")
    hits = [as_dict(score, doc) for score, doc in rank(args.intent, docs, args.top)]
    if args.json:
        print(json.dumps(hits, indent=2))
        return 0
    if not hits:
        print("No matching skill action. Try other words, or `ghost skill search <app>`.")
        return 1
    print("SCORE  SKILL  ACTION  SOURCE  PROMPT")
    for hit in hits:
        print(
            f"{hit['score']:>5}  {hit['skill']}  {hit['action']}  {hit['source']}  {hit['prompt'] or hit['description']}"
        )
    return 0


def _set_top_level(text: str, key: str, value) -> str:
    """Replace or insert one top-level scalar in skill.yaml text, keeping comments and order."""
    import re as _re

    import yaml as _yaml

    rendered = _yaml.safe_dump({key: value}, default_flow_style=False, allow_unicode=True).strip()
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if _re.match(rf"^{_re.escape(key)}:", line):
            lines[i] = rendered
            return "\n".join(lines)
    for i, line in enumerate(lines):
        if _re.match(r"^(version|author|status):", line):
            anchor = i
    lines.insert(anchor + 1, rendered)
    return "\n".join(lines)


def cmd_fork(argv):
    """Copy a skill under a new author/slug with forked_from lineage; runs, verifications and demos stay behind."""
    import shutil

    from gitd.skills.locations import find_skillhub_root
    from gitd.skills.refs import parse_ref

    p = _parser("fork")
    p.add_argument("source", help="skill dir or <author>/<slug>[@<version>]")
    p.add_argument("--as", dest="target", required=True, help="<author>/<slug> of the fork")
    p.add_argument("--out", help="parent directory for the fork (default: skillhub/ of the checkout)")
    p.add_argument("--force", action="store_true", help="overwrite an existing target directory")
    args = p.parse_args(argv)
    source = load_skill(args.source)
    target = parse_ref(args.target)
    if target.pinned:
        raise ValueError("--as takes <author>/<slug> without a version")
    if (target.author, target.slug) == (source.author, source.name):
        raise ValueError("The fork needs a different author or slug")
    parent = Path(args.out) if args.out else find_skillhub_root(Path.cwd())
    if parent is None:
        raise ValueError("Not inside a checkout with skillhub/; pass --out <dir>")
    dest = Path(parent) / target.author / target.slug
    if dest.exists():
        if not args.force:
            raise ValueError(f"{dest} exists; pass --force to overwrite")
        shutil.rmtree(dest)
    shutil.copytree(
        source.skill_dir,
        dest,
        ignore=shutil.ignore_patterns(
            "runs", "verifications", "demos", "bench", "__pycache__", "*.pyc", "demo.webm", "demo.mp4", "demo.gif"
        ),
    )
    text = (dest / "skill.yaml").read_text(encoding="utf-8")
    for key, value in (
        ("name", target.slug),
        ("author", target.author),
        ("version", "0.1.0"),
        ("forked_from", f"{source.author}/{source.name}@{source.version}"),
        ("status", "active"),
        ("generated_with", f"ghost skill fork of {source.author}/{source.name}@{source.version}"),
    ):
        text = _set_top_level(text, key, value)
    for key in ("demo", "superseded_by", "deprecated_reason"):
        text = "\n".join(line for line in text.split("\n") if not line.startswith(key + ":"))
    (dest / "skill.yaml").write_text(text, encoding="utf-8")
    forked = load_skill(dest)
    print(
        f"Forked {source.author}/{source.name}@{source.version} -> {dest} ({forked.author}/{forked.name}@{forked.version}, forked_from {forked.forked_from})"
    )
    print("Evidence does not carry over: record your own runs with `ghost skill run ... --record`.")
    return 0


def cmd_deprecate(argv):
    """Mark a skill deprecated with a reason and, optionally, the ref that replaces it."""
    p = _parser("deprecate", True)
    p.add_argument("--reason", required=True)
    p.add_argument("--superseded-by", dest="superseded_by")
    p.add_argument("--undo", action="store_true", help="set status back to active and drop the reason")
    args = p.parse_args(argv)
    skill = load_skill(args.path)
    path = skill.skill_dir / "skill.yaml"
    text = path.read_text(encoding="utf-8")
    if args.undo:
        text = _set_top_level(text, "status", "active")
        text = "\n".join(
            line for line in text.split("\n") if not line.startswith(("deprecated_reason:", "superseded_by:"))
        )
    else:
        text = _set_top_level(text, "status", "deprecated")
        text = _set_top_level(text, "deprecated_reason", args.reason)
        if args.superseded_by:
            text = _set_top_level(text, "superseded_by", args.superseded_by)
    path.write_text(text, encoding="utf-8")
    updated = load_skill(skill.skill_dir)
    print(
        f"{updated.author}/{updated.name}: status {updated.status}"
        + (f", superseded by {updated.superseded_by}" if updated.superseded_by else "")
        + (f" ({updated.deprecated_reason})" if updated.deprecated_reason else "")
    )
    return 0


def cmd_info(argv):
    """Show registry metadata and installed versions."""
    p = _parser("info")
    p.add_argument("ref")
    args = p.parse_args(argv)
    ref, _, version = args.ref.partition("@")
    entry = _registry()["skills"].get(ref)
    if entry is None:
        raise ValueError(f"Skill not found in registry: {ref}")
    if version and version not in {"latest", "main"} and version not in entry.get("versions", {}):
        raise ValueError(f"Unknown version: {args.ref}")
    print(json.dumps({"ref": ref, **entry}, indent=2))
    try:
        installed = [_plain(x) for x in hub.list_installed()]
        installed = [
            x
            for x in installed
            if (x.get("ref", "").split("@")[0] == ref or f"{x.get('author')}/{x.get('slug', x.get('name'))}" == ref)
        ]
        print("Install state: " + json.dumps(installed, default=str))
    except RuntimeError as exc:
        print(f"Install state unavailable: {exc}")
    return 0


def _analysis(path):
    from gitd.skills.engine.analyze import analyze_skill

    return [f.as_dict() for f in analyze_skill(path)]


def _analysis_table(findings):
    print("SEVERITY  FILE:LINE  RULE  MESSAGE")
    for f in findings:
        print(f"{f['severity']}  {f['file']}:{f['line']}  {f['rule']}  {f['message']}")


def cmd_analyze(argv):
    """Statically analyze skill Python; high findings exit 2."""
    p = _parser("analyze", True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    findings = _analysis(args.path)
    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        _analysis_table(findings)
        if not findings:
            print(
                "No findings. Static review signals only; this is not a sandbox, a maintainer still reads submitted Python."
            )
    return 2 if any(f["severity"] == "high" for f in findings) else 0


def _walk(value):
    if isinstance(value, dict):
        yield value
        for key, child in value.items():
            # Retained importer source is provenance, not executable YAML.
            if key != "import_unmapped":
                yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _target_exists(ref, root):
    """Resolve local Python definitions statically, including legacy fixture refs."""
    import ast

    module, separator, function = ref.partition(":")
    if not separator:
        return False
    if module.startswith("gitd.skills."):
        module = module.rsplit(".", 1)[-1]
    candidate = (root / (module.replace(".", "/") + ".py")).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        return False
    try:
        tree = ast.parse(candidate.read_text())
    except (SyntaxError, UnicodeError):
        return False
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function for n in tree.body)


def _forwards_python_params(ref: str, root: Path, *, custom_python: bool = False) -> bool:
    """Recognize whole-params forwarding in the referenced function, without imports."""
    import ast

    module, separator, function = ref.partition(":")
    if not separator:
        return False
    if module.startswith("gitd.skills."):
        module = module.rsplit(".", 1)[-1]
    source = (root / (module.replace(".", "/") + ".py")).resolve()
    if not source.is_relative_to(root.resolve()) or not source.is_file():
        return False
    try:
        tree = ast.parse(source.read_text())
    except (SyntaxError, UnicodeError):
        return False
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function
        ),
        None,
    )
    if target is None:
        return False
    arguments = [arg.arg for arg in target.args.posonlyargs + target.args.args]
    params_name = arguments[1] if not custom_python and len(arguments) > 1 else None
    context_index = 1 if custom_python else 2
    context_name = arguments[context_index] if len(arguments) > context_index else None

    def forwarded(value):
        if isinstance(value, ast.Name):
            return value.id == params_name or (custom_python and value.id == context_name)
        if isinstance(value, ast.Attribute):
            return value.attr == "params" and isinstance(value.value, ast.Name) and value.value.id == context_name
        if isinstance(value, ast.Starred):
            return forwarded(value.value)
        if isinstance(value, ast.BoolOp):
            return any(forwarded(child) for child in value.values)
        if isinstance(value, ast.Dict):
            return any(key is None and forwarded(child) for key, child in zip(value.keys, value.values))
        return False

    return any(
        isinstance(node, ast.Call)
        and any(forwarded(value) for value in [*node.args, *(keyword.value for keyword in node.keywords)])
        for node in ast.walk(target)
    )


def _leftover_todos(root, limit=8):
    """`TODO` lines in skill.yaml, SOFT.md and README.md (the scaffold writes them; the author must replace them)."""
    hits = []
    for name in ("skill.yaml", "SOFT.md", "README.md"):
        f = root / name
        if not f.exists():
            continue
        for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if "TODO" in line:
                hits.append(f"{name}:{n}: leftover TODO ({line.strip()[:60]})")
    if len(hits) > limit:
        hits = hits[:limit] + [f"... {len(hits) - limit} more leftover TODO line(s)"]
    return hits


def cmd_lint(argv):
    """Check skill authoring errors and portability warnings."""
    import re
    import xml.etree.ElementTree as ET

    import yaml

    from gitd.skills.engine.interpolate import _PLACEHOLDER

    args = _parser("lint", True).parse_args(argv)
    skill = load_skill(args.path)
    root = skill.skill_dir.resolve()
    raw = yaml.safe_load((root / "skill.yaml").read_text())
    errors = []
    warnings = []
    soft = (root / "SOFT.md").read_text() if (root / "SOFT.md").exists() else ""
    headings = re.findall(r"^#{1,6}\s+(.+)$", soft, re.M)
    described_text = set()
    for dump in (root / "data").rglob("*.xml"):
        try:
            for element in ET.parse(dump).iter():
                if element.get("text") and element.get("content-desc"):
                    described_text.add(element.get("text"))
        except ET.ParseError:
            warnings.append(f"Cannot parse data dump {dump.name}")
    if not skill.description.strip():
        errors.append("Empty skill description")
    if not skill.icon:
        warnings.append("No app icon (icon.webp); run tools/fetch_app_icons.py")
    warnings.extend(_demo_warnings(skill))
    # Scaffold and importer placeholders: lint warns (imports carry them by design), submit refuses them unless draft.
    warnings.extend(_leftover_todos(root))
    for a in skill.actions:
        if a.name not in skill.demos:
            warnings.append(f"{a.name}: no demo clip (demos/{a.name}.webm)")
    for rel in skill._demo_duplicates:
        warnings.append(f"{rel}: duplicate clip for the same action; the webm/mp4 one is used")
    subroutines = {s["name"]: s["steps"] for s in raw.get("subroutines", [])}

    def expanded(value, seen=()):
        for node in _walk(value):
            yield node
            ref = node.get("subroutine")
            if ref in subroutines and ref not in seen:
                yield from expanded(subroutines[ref], (*seen, ref))

    for action in raw["actions"]:
        name = action["name"]
        declared = {p["name"] for p in action.get("params", [])}
        executable = {k: v for k, v in action.items() if k not in {"params", "test_case", "ref_prompt", "description"}}
        used = set()
        for node in expanded(executable):
            for value in node.values():
                if isinstance(value, str):
                    used.update(
                        m.group(1)
                        for m in _PLACEHOLDER.finditer(value)
                        if m.group(1) and not m.group(1).startswith("context.")
                    )
        for param in sorted(used - declared):
            errors.append(f"{name}: undeclared param {param}")
        # Account for literal params reads in helper code without importing it.
        import ast

        for source in root.rglob("*.py"):
            try:
                tree = ast.parse(source.read_text())
            except (SyntaxError, UnicodeError):
                continue
            for node in ast.walk(tree):
                key = None
                if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "params":
                    key = node.slice
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "params"
                    and node.func.attr == "get"
                    and node.args
                ):
                    key = node.args[0]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    used.add(key.value)
        # Python adapters may forward the complete params mapping to v1 code.
        # Only the target referenced by this action can consume its params.
        for node in expanded(executable):
            ref = node.get("python_action")
            custom_python = node.get("kind") == "custom_python"
            if custom_python:
                ref = node.get("function")
            if ref and _forwards_python_params(ref, root, custom_python=custom_python):
                used.update(declared)
                break
        for param in sorted(declared - used):
            warnings.append(f"{name}: unused param {param}")
        for field in ("description", "ref_prompt"):
            if not str(action.get(field, "")).strip():
                errors.append(f"{name}: empty {field}")
        variants = action.get("test_case", {}).get("ref_prompt_variants", [])
        if len(set(variants)) != len(variants):
            errors.append(f"{name}: duplicate ref_prompt_variants")
        if not any(re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", h) for h in headings):
            warnings.append(f"{name}: missing SOFT.md section")
    for node in _walk(raw):
        if "import_unmapped" in node:
            warnings.append(
                "Unmapped imported node: " + str(node["import_unmapped"].get("reason", "manual translation required"))
            )
        if str(node.get("note", "")).startswith("TODO imported node:") and "import_unmapped" not in node:
            warnings.append(str(node["note"]))
        for value in node.values():
            if isinstance(value, list):
                for index, step in enumerate(value[:-1]):
                    if (
                        isinstance(step, dict)
                        and step.get("action") == "press_key"
                        and str(step.get("key")).upper() == "HOME"
                    ):
                        errors.append("Steps after terminal press_key HOME")
        if node.get("action") == "tap" and not node.get("note"):
            # YAML compose retains source marks, allowing adjacent comments.
            composed = yaml.compose((root / "skill.yaml").read_text())

            def marked(n):
                if isinstance(n, yaml.MappingNode):
                    if (
                        dict((k.value, v.value) for k, v in n.value if isinstance(v, yaml.ScalarNode)).get("action")
                        == "tap"
                    ):
                        yield n
                    for _, v in n.value:
                        yield from marked(v)
                elif isinstance(n, yaml.SequenceNode):
                    for v in n.value:
                        yield from marked(v)

            text_lines = (root / "skill.yaml").read_text().splitlines()
            commented = False
            for mapping in marked(composed):
                data = dict((k.value, v.value) for k, v in mapping.value if isinstance(v, yaml.ScalarNode))
                if str(node.get("x")) == data.get("x") and str(node.get("y")) == data.get("y"):
                    line = mapping.start_mark.line
                    commented = "#" in text_lines[line]
                    for previous in reversed(text_lines[:line]):
                        if not previous.strip():
                            continue
                        commented = commented or previous.lstrip().startswith("#")
                        break
                    if commented:
                        break
            if not commented:
                warnings.append("Coordinate tap lacks comment or note")
        if (
            node.get("text") in described_text
            and not node.get("desc")
            and node.get("action") in {"tap_element", "wait_for_element"}
        ):
            warnings.append(f"Prefer desc locator for {node['text']!r}")
        ref = node.get("python_action") or (node.get("function") if node.get("kind") == "custom_python" else None)
        if ref and not _target_exists(ref, root):
            errors.append(f"Python target does not resolve: {ref}")
    findings = _analysis(root)
    _analysis_table(findings)
    errors.extend(f"{f['file']}:{f['line']}: {f['message']}" for f in findings if f["severity"] == "high")
    for message in warnings:
        _print_warn(message)
    for message in errors:
        _print_err(message)
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def cmd_diff(argv):
    """Compare actions, params, steps, fingerprints, and validators."""
    from dataclasses import asdict
    from itertools import zip_longest

    p = _parser("diff")
    p.add_argument("a")
    p.add_argument("b")
    args = p.parse_args(argv)
    a, b = load_skill(args.a), load_skill(args.b)
    aa = {x.name: x for x in a.actions}
    bb = {x.name: x for x in b.actions}
    result = {
        "actions_added": sorted(bb.keys() - aa.keys()),
        "actions_removed": sorted(aa.keys() - bb.keys()),
        "actions_changed": {},
        "fingerprint_changed": asdict(a.fingerprint) != asdict(b.fingerprint),
    }
    for name in sorted(aa.keys() & bb.keys()):
        old, new = aa[name], bb[name]
        changes = {}
        if old.params != new.params:
            changes["params"] = {"before": [asdict(p) for p in old.params], "after": [asdict(p) for p in new.params]}
        if old.steps != new.steps:
            index = next(i for i, (x, y) in enumerate(zip_longest(old.steps, new.steps)) if x != y)
            changes["steps"] = {
                "before_count": len(old.steps),
                "after_count": len(new.steps),
                "first_differing_step": index,
                "before": old.steps[index] if index < len(old.steps) else None,
                "after": new.steps[index] if index < len(new.steps) else None,
            }
        if old.end_state_validator != new.end_state_validator:
            changes["validator"] = {"before": old.end_state_validator, "after": new.end_state_validator}
        if changes:
            result["actions_changed"][name] = changes
    if result["fingerprint_changed"]:
        result["fingerprint"] = {"before": asdict(a.fingerprint), "after": asdict(b.fingerprint)}
    print(json.dumps(result, indent=2))
    return 0


def cmd_keys(argv):
    """Show the local run-signing public key and the skillhub/SIGNERS line that makes it count."""
    p = _parser("keys")
    p.add_argument("--principal", help="Hub author name (self-runs) or your GitHub login (verifications)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    from gitd.skills.engine.evidence import signers_line, signing_public_key

    public_key = signing_public_key()
    line = signers_line(args.principal, public_key).rstrip("\n") if args.principal else None
    if args.json:
        print(json.dumps({"public_key": public_key, "signers_line": line}))
        return 0
    print(f"Run-signing public key: {public_key}")
    print("1. Add it to GitHub > Settings > SSH and GPG keys (authentication key); CI checks keys there.")
    if line:
        print("2. Append this line to skillhub/SIGNERS in the PR that carries your first run artifact:")
        print(f"   {line}")
    else:
        print("2. Run `ghost skill keys --principal <author-or-login>` for the skillhub/SIGNERS line.")
    print(
        "Registry rule: only artifacts that verify against SIGNERS (or verifier-keys.yml) count; "
        "fake-device runs never count."
    )
    return 0


def _doctor_skill(ref, device):
    """`ghost skill doctor <ref>`: authored fingerprint, tested fingerprints from runs/, distance to a device."""
    from datetime import datetime, timezone

    from gitd.skills.engine.fingerprint import check as check_fingerprint
    from gitd.skills.engine.fingerprint import distance

    skill = load_skill(ref)
    authored = {
        k: getattr(skill.fingerprint, k) for k in ("os", "os_version", "hardware", "app_package", "app_version")
    }
    print(f"{skill.author}/{skill.name} v{skill.version}")
    print("Authored for: " + json.dumps(authored))
    tested = {}
    for artifact in sorted((skill.skill_dir / "runs").glob("*.json")):
        try:
            payload = json.loads(artifact.read_text())
        except (OSError, ValueError):
            continue
        fp = payload.get("fingerprint") or {}
        if payload.get("simulation") or not isinstance(fp, dict):
            continue
        key = (fp.get("os_version", ""), fp.get("hardware", ""), fp.get("app_version", ""))
        row = tested.setdefault(key, {"passed": 0, "total": 0, "last_pass": ""})
        row["total"] += 1
        if payload.get("success"):
            row["passed"] += 1
            row["last_pass"] = max(row["last_pass"], str(payload.get("finished_at") or payload.get("timestamp") or ""))
    if tested:
        print("Tested on:")
        now = datetime.now(timezone.utc)
        for (os_version, hardware, app_version), row in sorted(tested.items()):
            age = ""
            if row["last_pass"]:
                try:
                    age = f", last pass {(now - datetime.fromisoformat(row['last_pass'].replace('Z', '+00:00'))).days} days ago"
                except ValueError:
                    age = ""
            print(f"  {hardware} Android {os_version} app {app_version}: {row['passed']}/{row['total']} passed{age}")
    else:
        print("Tested on: no device runs recorded")
    if not device:
        return 0
    try:
        report = check_fingerprint(skill, device, force=True)
    except ValueError as exc:
        _print_err(str(exc))
        return 2
    if report is None:
        print(f"Your device {device}: cannot be probed (iOS or adb unreachable)")
        return 1
    print(f"Your device {device}: " + json.dumps(report.device))
    print(
        f"Distance {report.distance} ({report.tier})"
        + (": " + ", ".join(report.mismatches) if report.mismatches else "")
    )
    if tested:
        nearest = min(
            tested,
            key=lambda key: (
                distance(
                    skill.fingerprint, dict(authored, os_version=key[0], hardware=key[1], app_version=key[2])
                ).distance
            ),
        )
        print(f"Nearest tested fingerprint: {nearest[1]} Android {nearest[0]} app {nearest[2]}")
    return 0 if report.tier != "refuse" else 2


def cmd_doctor(argv):
    """Diagnose local tools, registries, storage, hub connectivity; with <ref>, fingerprint fit of one skill."""
    import shutil
    import tempfile
    from urllib.request import urlopen

    p = _parser("doctor")
    p.add_argument(
        "ref", nargs="?", help="skill ref or path: report authored/tested fingerprints and the distance to --device"
    )
    p.add_argument("--device", default=os.environ.get("GHOST_DEVICE") or os.environ.get("DEFAULT_DEVICE", ""))
    args = p.parse_args(argv)
    if args.ref:
        return _doctor_skill(args.ref, args.device)
    checks = []

    def check(name, operation):
        try:
            detail = operation()
            checks.append((name, True, str(detail)))
        except Exception as exc:
            checks.append((name, False, str(exc)))

    def command(tool, *args):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool} not found")
        return subprocess.run([tool, *args], check=True, capture_output=True, text=True, timeout=20).stdout.strip()

    def devices():
        output = command("adb", "devices")
        if not any(line.endswith("\tdevice") for line in output.splitlines()):
            raise RuntimeError("No authorized adb devices")
        return output

    check("adb devices", devices)
    check(
        "python version",
        lambda: (
            sys.version.split()[0]
            if sys.version_info >= (3, 10)
            else (_ for _ in ()).throw(RuntimeError("Python >=3.10 required"))
        ),
    )
    check("gh authenticated", lambda: command("gh", "auth", "status"))

    def writable():
        path = Path(os.environ.get("GHOST_SKILLS_DIR", "~/.ghost/skills")).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
        return path

    check("skills writable", writable)
    check(
        "engine registries",
        lambda: (
            f"{len(registered_steps())} steps, {len(registered_kinds())} validators"
            if registered_steps() and registered_kinds()
            else (_ for _ in ()).throw(RuntimeError("Empty registries"))
        ),
    )
    for host in ("https://cdn.jsdelivr.net", "https://raw.githubusercontent.com"):

        def reach(url=host):
            with urlopen(url, timeout=20) as response:
                return response.status

        check(host, reach)
    for name, ok, detail in checks:
        print(f"{'OK' if ok else 'FAIL'} {name}: {detail}")
    return 0 if all(ok for _, ok, _ in checks) else 1


def cmd_import(argv):
    """Import Maestro/Automate flows, or AndroidWorld tasks, into schema v2 skills."""
    import yaml

    from gitd.skills.engine.importers import action_name, parse_automate, parse_maestro, render_skill
    from gitd.skills.refs import parse_ref

    p = _parser("import")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--maestro", metavar="FLOW.yaml")
    group.add_argument("--automate", metavar="FILE.flo")
    group.add_argument(
        "--androidworld",
        metavar="CHECKOUT",
        help="google-research/android_world checkout, read statically (nothing executed)",
    )
    p.add_argument(
        "--out",
        help="Output skill directory; default skillhub/local/<source-name> "
        "(--androidworld: parent dir, default skillhub/androidworld)",
    )
    p.add_argument("--force", action="store_true", help="--androidworld: overwrite skills without the generated marker")
    args = p.parse_args(argv)
    if args.androidworld:
        from gitd.skills.engine.androidworld import import_android_world

        results = import_android_world(args.androidworld, args.out or "skillhub/androidworld", force=args.force)
        for r in results:
            line = f"{r['slug']}: {r['tasks']} task(s), {r['status']}"
            (_print_ok if r["status"] == "written" else _print_warn)(line)
        total = sum(r["tasks"] for r in results if r["status"] == "written")
        print(
            f"{total} task(s) in {sum(r['status'] == 'written' for r in results)} draft skill(s). "
            "Next: author steps + port validators, then ghost skill validate / lint."
        )
        return 0 if all(r["status"] == "written" for r in results) else 1
    source = Path(args.maestro or args.automate)
    format_name = "maestro" if args.maestro else "automate"
    flows = parse_maestro(source) if args.maestro else parse_automate(source)
    output = Path(args.out) if args.out else Path("skillhub/local") / action_name(source.stem)
    ref = parse_ref(f"{output.parent.name}/{output.name}")
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    if len({flow.app_package for flow in flows}) != 1:
        raise ValueError("Flows target different apps; import each flow into a separate skill")
    names = [flow.name for flow in flows]
    template = _render_skill_yaml(ref.key, ref.slug, flows[0].app_package, "hard", names, False)
    raw = yaml.safe_load(template)
    raw["description"] = f"Imported {format_name} flows from {source.name}; review before replay"
    raw["generated_with"] = f"ghost skill import --{format_name}"
    raw["skill_path"] = output.as_posix()
    for action, flow in zip(raw["actions"], flows):
        action["description"] = f"Imported flow {flow.name}"
        action["ref_prompt"] = f"Run {flow.name.replace('_', ' ')}"
        action["steps"] = flow.steps
        action["test_case"]["ref_prompt_variants"] = [action["ref_prompt"], f"Execute {flow.name} flow"]
        terminal = flow.steps[-1] if flow.steps[-1].get("action") in {"wait_for_text", "wait_for_element"} else None
        if terminal and not any("import_unmapped" in step for step in flow.steps):
            action["end_state_validator"] = (
                {"kind": "text_visible", "text": terminal["text"]}
                if "text" in terminal
                else {"kind": "element_present", "id": terminal["id"]}
            )
        else:
            action["end_state_validator"] = {
                "kind": "text_visible",
                "text": "TODO: define and verify the imported flow end state",
            }
            flow.warnings.append("Terminal validator requires manual authoring")
    output.mkdir(parents=True)
    original_name = "imported-source.yaml" if args.maestro else "imported-source.flo"
    (output / original_name).write_bytes(source.read_bytes())
    (output / "skill.yaml").write_text(render_skill(raw), encoding="utf-8")
    (output / "helpers.py").write_text(_render_helpers_stub(ref.slug, names), encoding="utf-8")
    (output / "SOFT.md").write_text(
        _render_soft_md(ref.slug, flows[0].app_package, names).replace("—", "-"), encoding="utf-8"
    )
    (output / "README.md").write_text(
        _render_readme(ref.key, ref.slug, names).replace("—", "-")
        + f"\nImported from `{source.name}`. Original source: `{original_name}`. Review TODOs, fingerprint, data access, side effects, and validators before replay.\n",
        encoding="utf-8",
    )
    for flow in flows:
        for warning in flow.warnings:
            _print_warn(f"{flow.name}: {warning}")
    _print_ok(f"Imported {len(flows)} flow(s) into {output}")
    return 0


def cmd_verify(argv):
    """Run verification; preview by default, create a real PR only with --push."""
    from gitd.skills.engine.evidence import collect_fingerprint, github_login, write_evidence
    from gitd.skills.engine.submission import checkout_root, push_verification, target_repo, verification_dir

    p = _parser("verify")
    p.add_argument("ref")
    p.add_argument("--action", help="Verify one action; default is every action")
    p.add_argument("--param", action="append", default=[])
    p.add_argument("--device", default=os.environ.get("GHOST_DEVICE") or os.environ.get("DEFAULT_DEVICE", ""))
    p.add_argument("--fingerprint", help="Concrete device fingerprint JSON file")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Preview PR submission after the verification run (default)"
    )
    mode.add_argument(
        "--push", action="store_true", help="Commit only the artifact, push to the target URL, and create a PR"
    )
    p.add_argument("--repo", help="Target owner/repo; defaults to GHOST_HUB_REPO or the public Android Agent repository")
    args = p.parse_args(argv)
    if not args.device:
        raise ValueError("--device required (or set DEFAULT_DEVICE env)")
    repo = target_repo(args.repo)
    skill = load_skill(args.ref)
    actions = [skill.action(args.action)] if args.action else skill.actions
    login = github_login()
    if login.casefold() == skill.author.casefold():
        raise ValueError("Independent verification requires an account other than the skill author")
    root = checkout_root(skill.skill_dir)
    artifact_dir = verification_dir(root, skill)
    fingerprint = collect_fingerprint(skill, args.device, args.fingerprint)
    params = _parse_params(args.param)
    results = [
        run_action(
            skill,
            action.name,
            params={key: value for key, value in params.items() if action.param(key)},
            device_serial=args.device,
        )
        for action in actions
    ]
    from gitd.skills.engine.evidence import detect_emulator

    artifact = write_evidence(
        skill,
        results,
        fingerprint,
        login=login,
        artifact_dir=artifact_dir,
        simulated=args.device.startswith("fake:"),
        emulator=detect_emulator(args.device),
    )
    print(f"Verification artifact: {artifact}")
    payload = json.loads(artifact.read_text())
    timestamp = artifact.stem.rsplit("-", 1)[-1]
    plan = {
        "title": f"[verification] {skill.author}/{skill.name} by {login}",
        "repo": repo,
        "branch": f"verify/{login}-{skill.author}-{skill.name}-{timestamp}",
        "files": [artifact.relative_to(root).as_posix()],
        "body": f"Independent run by @{login} for {skill.author}/{skill.name}@{skill.version}.\n\n"
        f"Fingerprint: {payload['fingerprint_hash']}\nApp version: {fingerprint['app_version']}\n"
        f"Finished: {payload['finished_at']}\nSuccess: {all(r.success for r in results)}\n\n"
        "Local signatures establish artifact integrity; account identity and device independence require CI/reviewer checks.",
    }
    print(json.dumps(plan, indent=2))
    if args.push:
        print("Verification PR: " + push_verification(root, artifact, plan))
    else:
        print("PR preview only. Pass --push to submit the artifact to the target repository.")
    return 0 if all(result.success for result in results) else 1


def cmd_submit(argv):
    """Print the submission plan; --push forks, commits the skill dir on an isolated index and opens the PR."""
    import re
    from dataclasses import asdict

    import yaml

    from gitd.skills.engine.submission import checkout_root, push_skill, skill_submission_files, target_repo

    p = _parser("submit", True)
    p.add_argument(
        "--push",
        action="store_true",
        help="fork the hub repo, push skill/<author>-<slug> and open the PR (needs gh auth)",
    )
    p.add_argument("--dry-run", action="store_true", help="accepted for compatibility; the plan is the default")
    p.add_argument(
        "--repo", default=None, help="<owner>/<repo> hub repository (default: GHOST_HUB_REPO or the built-in hub)"
    )
    args = p.parse_args(argv)
    if args.push and args.dry_run:
        raise ValueError("--push and --dry-run are mutually exclusive")
    repo = target_repo(args.repo)
    skill = load_skill(args.path)
    todos = _leftover_todos(skill.skill_dir.resolve())
    if todos and skill.status != "draft":
        _print_err("Leftover TODO placeholders from the scaffold; replace them before submitting:")
        for t in todos:
            print("  " + t)
        return 1
    findings = _analysis(skill.skill_dir)
    _analysis_table(findings)
    if any(f["severity"] == "high" for f in findings):
        return 2
    # Resolve references without executing submitted Python.
    raw = yaml.safe_load((skill.skill_dir / "skill.yaml").read_text())
    for node in _walk(raw):
        ref = node.get("python_action") or (node.get("function") if node.get("kind") == "custom_python" else None)
        if ref and not _target_exists(ref, skill.skill_dir.resolve()):
            raise ValueError(f"Python target does not resolve: {ref}")
    files = sorted(
        str(f.relative_to(skill.skill_dir))
        for f in skill.skill_dir.rglob("*")
        if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"
    )
    body = [skill.description, "", "| Action | Description | Params |", "| --- | --- | --- |"]
    for action in skill.actions:
        body.append(f"| {action.name} | {action.description} | {', '.join(p.name for p in action.params)} |")
    body.extend(
        [
            "",
            "Fingerprint: " + json.dumps(asdict(skill.fingerprint)),
            "data_access: " + json.dumps(skill.data_access),
            "has_python: " + str(any(f.endswith(".py") for f in files)).lower(),
            "Static analysis: " + json.dumps(findings),
        ]
    )
    bench = skill.skill_dir / "bench.yaml"
    if bench.exists():
        body.append("Bench summary: " + json.dumps(yaml.safe_load(bench.read_text()), default=str))
    demo = skill.demo if skill.demo and (skill.skill_dir / skill.demo).exists() else None
    if demo:
        body.append("Demo: ![Demo](demo.gif)" if demo.endswith(".gif") else f"Demo: [{demo}]({demo})")
    checklist = []
    for parent in Path(__file__).resolve().parents:
        doc = parent / "docs/contributing-skills.md"
        if doc.exists():
            text = doc.read_text()
            section = text.split("## 5. Review process", 1)[-1].split("## 6.", 1)[0]
            checklist = re.findall(r"^- (.+)$", section, re.M)
            break
    body.extend(
        [
            "",
            "Contribution checklist ([contributing guide](https://github.com/"
            + repo
            + "/blob/main/docs/contributing-skills.md)):",
        ]
    )
    body.extend(
        "- [ ] " + item
        for item in checklist
        or [
            "Fingerprint tested",
            "Validators gate success",
            "data_access declared honestly",
            "README and SOFT.md complete",
            "Prompt variants are distinct",
        ]
    )
    plan = {
        "title": f"[skill] {skill.author}/{skill.name} v{skill.version}",
        "branch": f"skill/{skill.author}-{skill.name}",
        "repo": repo,
        "files": [f"skillhub/{skill.author}/{skill.name}/{f}" for f in files],
        "body": "\n".join(body),
    }
    print(json.dumps(plan, indent=2))
    if not args.push:
        print("Plan only. Pass --push to fork the hub repository, push the branch and open the PR.")
        return 0
    root = checkout_root(skill.skill_dir)
    plan["files"] = skill_submission_files(root, skill.skill_dir)
    if skill.author.casefold() == "ghost":
        print("Note: skillhub/ghost/ is the official namespace; CI accepts it only from a maintainer.")
    print("Skill PR: " + push_skill(root, skill.skill_dir, plan))
    return 0


# ── entry point ─────────────────────────────────────────────────────────────


def _probe_media(path):
    """(duration_s, width, height) via ffprobe, or None when ffprobe is missing or fails.

    Read-only metadata probe; nothing is decoded or rendered. Tests replace this function.
    """
    import shutil

    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "format=duration:stream=width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        ).stdout
        data = json.loads(out)
        stream = (data.get("streams") or [{}])[0]
        return (
            float(data.get("format", {}).get("duration") or 0),
            int(stream.get("width") or 0),
            int(stream.get("height") or 0),
        )
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return None


def _demo_warnings(skill) -> list[str]:
    from gitd.skills.engine.loader import DEMO_WARN_BYTES, DEMO_WARN_LONG_SIDE, DEMO_WARN_SECONDS

    if not skill.demo:
        return []
    f = skill.skill_dir / skill.demo
    out = []
    size = f.stat().st_size
    if size > DEMO_WARN_BYTES:
        out.append(f"Demo {skill.demo} is {size} bytes; keep it under {DEMO_WARN_BYTES} (1.5 MB)")
    if f.suffix.lower() == ".gif":
        out.append(f"Demo {skill.demo} is a GIF: prefer webm/mp4")
    probe = _probe_media(f)
    if probe:
        duration, width, height = probe
        if duration > DEMO_WARN_SECONDS:
            out.append(f"Demo {skill.demo} runs {duration:.0f} s; keep it to {DEMO_WARN_SECONDS} s or less")
        if max(width, height) > DEMO_WARN_LONG_SIDE:
            out.append(f"Demo {skill.demo} is {width}x{height}; keep the long side to {DEMO_WARN_LONG_SIDE} px or less")
    return out


def cmd_migrate(argv: list[str]) -> int:
    """Wrap v1 skills as Schema v2 in place (v1 files kept)."""
    from gitd.skills.engine.migrate import migrate_skill

    p = argparse.ArgumentParser(prog="ghost skill migrate", add_help=True)
    p.add_argument("paths", nargs="+", help="v1 skill dir(s)")
    p.add_argument("--author", default=None, help="GitHub handle when skill.yaml/path does not imply one")
    p.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing")
    args = p.parse_args(argv)

    rc = 0
    for path in args.paths:
        r = migrate_skill(path, author=args.author, dry_run=args.dry_run)
        if r.status == "legacy":
            _print_err(f"{path}: legacy, not migrated: {r.reason}")
            rc = 1
            continue
        verb = "would migrate" if args.dry_run and r.status == "migrated" else r.status.replace("_", " ")
        _print_ok(f"{path}: {verb} ({len(r.actions)} actions: {', '.join(r.actions)})")
        for name in r.skipped:
            _print_warn(f"  exported but no v1 class found, skipped: {name}")
    return rc


# ── bench (AndroidWorld replay arm) ──────────────────────────────────────────


def cmd_bench(argv: list[str]) -> int:
    """Replay a skill against AndroidWorld tasks and let AndroidWorld's own evaluator score it."""
    from gitd.skills.engine import bench as bench_mod

    p = argparse.ArgumentParser(
        prog="ghost skill bench",
        description="AndroidWorld before/after bench, replay arm: deterministic skill replay, "
        "scored by task.is_successful through tools/bench/aw_bridge.py.",
    )
    p.add_argument("path", help="Skill dir OR hub ref like androidworld/pro-expense")
    p.add_argument(
        "--androidworld",
        action="append",
        required=True,
        metavar="TASK",
        help="AndroidWorld task name (repeatable), e.g. ExpenseAddMultipleFromMarkor",
    )
    p.add_argument("--action", help="Skill action to replay (default: derived from the task name)")
    p.add_argument("--arms", default=bench_mod.ARM_REPLAY, help='Comma list; only "replay" exists in this version')
    p.add_argument("--n", type=int, default=5, help="Seeds per task (AndroidWorld task_random_seed base + i)")
    p.add_argument("--seed-base", type=int, default=30, help="First task_random_seed (AndroidWorld run.py default 30)")
    p.add_argument(
        "--device",
        default=os.environ.get("GHOST_DEVICE") or os.environ.get("DEFAULT_DEVICE", ""),
        help="adb serial of the AndroidWorld emulator as seen by this adb server (set ADB_SERVER_SOCKET for a remote one)",
    )
    p.add_argument(
        "--bridge-cmd",
        required=True,
        help="Command that starts tools/bench/aw_bridge.py next to the emulator, e.g. "
        '"ssh <emulator-host> docker exec -i <container> python3 /work/aw_bridge.py --console-port 5554"',
    )
    p.add_argument("--no-record", action="store_true", help="Do not write signed run artifacts")
    p.add_argument(
        "--verifier",
        default=None,
        help="Signing principal for the artifacts (default: ghost-aw-replay on a real device, written to "
        "verifications/; fake devices write self-runs). The principal's key must be listed in "
        "skillhub/verifier-keys.yml for the registry to count the run.",
    )
    p.add_argument("--out", help="Artifact directory override (default: the skill runs/ or verifications/ dir)")
    p.add_argument("--upstream-commit", help="AndroidWorld commit to stamp into bench/androidworld.json")
    p.add_argument("--json", action="store_true", help="Print the per-seed cells as JSON")
    args = p.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if arms != [bench_mod.ARM_REPLAY]:
        _print_err(f"only the {bench_mod.ARM_REPLAY} arm is implemented; the agent arms need the AndroidWorld harness")
        return 2
    if not args.device:
        _print_err("--device required (or set GHOST_DEVICE)")
        return 2
    skill = load_skill(args.path)
    seeds = [args.seed_base + i for i in range(args.n)]
    verifier = args.verifier
    if verifier is None and not args.device.startswith("fake:"):
        verifier = bench_mod.REPLAY_PRINCIPAL
    cells: list[dict] = []
    with bench_mod.AWBridge(bench_mod.bridge_command(args.bridge_cmd)) as bridge:
        hello = bridge.request("hello")
        known = set(hello.get("tasks") or [])
        for task in args.androidworld:
            if known and task not in known:
                _print_err(f"{task}: not an AndroidWorld task on this bridge")
                return 2
            cells += bench_mod.replay_task(
                skill,
                task,
                seeds=seeds,
                device=args.device,
                bridge=bridge,
                action=args.action,
                record=not args.no_record,
                login=verifier,
                artifact_dir=Path(args.out) if args.out else None,
            )
    summary = bench_mod.write_summary(skill, cells, upstream_commit=args.upstream_commit)
    passed = sum(1 for c in cells if c["success"])
    if args.json:
        print(json.dumps(cells, indent=2, default=str))
    print(f"Bench summary: {summary}")
    if passed == len(cells):
        _print_ok(f"androidworld replay {passed}/{len(cells)} passed")
        return 0
    _print_err(f"androidworld replay {passed}/{len(cells)} passed")
    return 1


_SUBCOMMANDS = {
    "scaffold": cmd_scaffold,
    "validate": cmd_validate,
    "test": cmd_test,
    "run": cmd_run,
    "probe": cmd_probe,
    "demo": cmd_demo,
    "list-registered": cmd_list_registered,
    "submit": cmd_submit,
    "analyze": cmd_analyze,
    "verify": cmd_verify,
    "import": cmd_import,
    "lint": cmd_lint,
    "doctor": cmd_doctor,
    "keys": cmd_keys,
    "diff": cmd_diff,
    "install": cmd_install,
    "uninstall": cmd_uninstall,
    "update": cmd_update,
    "outdated": cmd_outdated,
    "list": cmd_list,
    "info": cmd_info,
    "search": cmd_search,
    "find": cmd_find,
    "fork": cmd_fork,
    "deprecate": cmd_deprecate,
    "migrate": cmd_migrate,
    "bench": cmd_bench,
}

# Legacy subcommands routed to gitd.cli (install / list / update / remove / search)


def cmd_resume(argv):
    """Resume a parent-agent ask with a JSON answer."""
    import json

    from .ask_resume import resume_action

    parser = argparse.ArgumentParser(prog="ghost skill resume")
    parser.add_argument("token")
    parser.add_argument("--answer", required=True)
    parser.add_argument("--secret-env", action="append", default=[])
    args = parser.parse_args(argv)
    result = resume_action(args.token, json.loads(args.answer), secrets=_env_params(args.secret_env))
    print(json.dumps(result.as_dict(), default=str))
    return 0 if result.success or result.status == "needs_input" else 1


_SUBCOMMANDS["resume"] = cmd_resume
_SUBCOMMANDS["remove"] = cmd_uninstall  # v1 spelling kept as an alias


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("Usage: ghost skill <subcommand> [args]\n")
        print("Schema v2 subcommands:")
        for name, fn in _SUBCOMMANDS.items():
            doc = (fn.__doc__ or "Manage skills").splitlines()[0]
            print(f"  {name:<18} {doc}")
        return 0
    sub = argv[0]
    handler = _SUBCOMMANDS.get(sub)
    if not handler:
        _print_err(f"Unknown subcommand: {sub!r}. Try 'ghost skill --help'.")
        return 2
    try:
        return handler(argv[1:])
    except (SkillError, HubError, OSError, ValueError, RuntimeError) as exc:
        _print_err(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
