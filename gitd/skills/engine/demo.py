"""Skill-action specs for the existing Ghost showcase recording pipeline.

Planning is read-only. Real capture is supplied by scripts/record_demo.py;
this module orchestrates its helpers without introducing a replacement split layout.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import sys
from pathlib import Path

from gitd.skills.engine.context import RunContext
from gitd.skills.engine.interpolate import interpolate
from gitd.skills.engine.runner import _resolve_params

REPO_ROOT = Path(__file__).resolve().parents[3]


def parser():
    result = argparse.ArgumentParser(prog="ghost skill demo")
    result.add_argument("ref")
    result.add_argument(
        "legacy_action", metavar="action", nargs="?", help="Action to record; omit to record all actions"
    )
    result.add_argument("--mode", choices=("hard", "soft"), help="Deterministic replay or a live Claude session")
    result.add_argument("--spec", type=Path, help="YAML overrides: cards and app-scoped seed broadcasts")
    result.add_argument("--trim-idle", action="store_true", help="Drop static frames from the final composite")
    result.add_argument("--max-tokens", type=int, default=12000, help="Live Claude session token cap")
    for flag in ("header", "eyebrow", "title", "byline", "subheader", "outro-title", "outro-cmd", "outro-url"):
        result.add_argument("--" + flag)
    result.add_argument("--actions", help="Comma-separated action subset")
    result.add_argument(
        "--render-host",
        default=os.environ.get("GHOST_DEMO_RENDER_HOST"),
        help="SSH host for phone capture and every encoding operation",
    )
    result.add_argument(
        "--render-root",
        default=os.environ.get("GHOST_DEMO_RENDER_ROOT", "~/ghost-in-the-droid"),
        help="Checkout path on the render host",
    )
    result.add_argument("--render-python", default=os.environ.get("GHOST_DEMO_RENDER_PYTHON", "python3"))
    result.add_argument("--action", help="Record one action; default records every action")
    result.add_argument("--param", action="append", default=[])
    result.add_argument("--device", required=True)
    result.add_argument("--out")
    result.add_argument("--prompt")
    result.add_argument(
        "--phone-offset",
        type=float,
        default=3.0,
        help="Compensate phone lead relative to the terminal, in seconds (default 3)",
    )
    result.add_argument("--record-size", help="adb screenrecord WxH")
    result.add_argument("--layout", choices=("split", "phone"), default="split")
    result.add_argument("--agent", choices=("claude", "cli", "engine"), default="claude")
    result.add_argument(
        "--long-side", type=int, default=720, help="Long side of the final clip in px (hub default 720)"
    )
    result.add_argument(
        "--crf", type=int, default=41, help="VP9 constant quality for the final clip (lower = better, bigger)"
    )
    result.add_argument("--dry", action="store_true")
    result.add_argument("--no-ocr", action="store_true")
    result.add_argument("--i-know", action="store_true")
    return result


def app_name(skill):
    """Human app name: skill.yaml `app_name`, else the description's lead before ':' or the slug."""
    import yaml

    try:
        raw = yaml.safe_load((Path(skill.skill_dir) / "skill.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    if raw.get("app_name"):
        return str(raw["app_name"])
    lead = re.split(r":| \u2014 | - ", skill.description or "", maxsplit=1)[0].strip()
    return (
        lead if lead and len(lead) <= 40 and lead != skill.description.strip() else skill.name.replace("_", " ").title()
    )


def intro_fields(skill, action):
    """Opener card for skill demos: SKILL DEMO / @author / '<App name>: <Action title>'."""
    title = action.name.replace("_", " ").strip()
    return {
        "kicker": "SKILL DEMO",
        "byline": "@" + skill.author,
        "title": f"{app_name(skill)}: {title[:1].upper() + title[1:]}",
    }


def build_plan(skill, args, params):
    """Generate record_demo.py's existing spec schema plus capture metadata."""
    mode = getattr(args, "mode", None)
    if mode:
        args.agent = "engine" if mode == "hard" else "claude"
    if not 1 <= getattr(args, "max_tokens", 12000) <= 100000:
        raise ValueError("--max-tokens must be 1..100000")
    import yaml

    overrides = yaml.safe_load(args.spec.read_text()) if getattr(args, "spec", None) else {}
    if not isinstance(overrides, dict):
        raise ValueError("--spec must contain a mapping")
    cards = overrides.get("cards", {})
    if not isinstance(cards, dict) or not all(isinstance(value, str) for value in cards.values()):
        raise ValueError("cards must map names to text")
    cards = dict(cards)
    for key in ("header", "eyebrow", "title", "byline", "subheader", "outro_title", "outro_cmd", "outro_url"):
        if getattr(args, key, None) is not None:
            cards[key] = getattr(args, key)
    if skill.fingerprint.os != "android" or args.device.startswith(("ios:", "fake:")):
        raise ValueError("Showcase screenrecord requires an Android adb device")
    if Path(args.out or "demo.webm").suffix.lower() != ".webm":
        raise ValueError("--out must end in .webm")
    try:
        action = skill.action(args.action)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    if any(p.secret for a in skill.actions for p in a.params):
        raise ValueError(
            "Secret-bearing skills cannot be screen-recorded; use a human recording with credential entry excluded"
        )
    resolved = _resolve_params(action.params, params, skill.name, action.name)
    context = RunContext(action_name=action.name)
    context.params = resolved
    prompt = str(interpolate(args.prompt or action.ref_prompt, context))
    # Migrated prompts often lack placeholders. Preserve the canonical phrase,
    # then supply all resolved params explicitly rather than silently omit them.
    if resolved:
        prompt += "\nParameters: " + json.dumps(resolved, sort_keys=True, ensure_ascii=False)
    timeline = []
    if args.agent == "claude":
        command = shlex.join(["claude", "--mcp-config", "<workdir>/mcp.json", prompt])
    elif args.agent == "cli":
        command = shlex.join(["ghost", prompt])
    else:
        command_args = [
            "python3",
            "-m",
            "gitd.ghost_cli",
            "skill",
            "run",
            os.path.relpath(skill.skill_dir.resolve(), REPO_ROOT),
            action.name,
            "--live-trace",
            "--record",
        ]
        for key, value in resolved.items():
            if value is None:
                continue
            command_args.extend(
                ["--param", f"{key}={value}" if isinstance(value, str) else f"{key}={json.dumps(value)}"]
            )
        command = shlex.join(command_args)
    timeline.append({"t": 0, "caption": prompt, "action": "terminal_type", "args": {"cmd": command}})
    for index, step in enumerate(action.steps):
        primitive = step.get("action") or next(iter(step), "step")
        key_args = {key: value for key, value in step.items() if key not in {"action", "caption"}}
        step_caption = step.get("caption") or f"Step {index + 1}: {primitive} " + json.dumps(
            key_args, ensure_ascii=False, default=str
        )
        timeline.append(
            {
                "t": round(2 + index * 20 / max(len(action.steps), 1), 2),
                "caption": step_caption,
                "action": "sleep",
                "args": {"seconds": 0},
            }
        )
    timeline.append(
        {"t": 24, "caption": "The phone shows the resulting state", "action": "wait_for_phone", "args": {"seconds": 2}}
    )
    intro = intro_fields(skill, action)
    spec = {
        "demo": f"skill-{skill.name}-{action.name}",
        "title": intro["title"],
        "cards": {"skill": f"{skill.author}/{skill.name}", "action": action.name, **cards},
        "demo_app": skill.fingerprint.app_package,
        "seed": overrides.get("seed", []),
        "intro": intro,
        "device": "android",
        "duration_target_s": 30,
        "record_size": args.record_size,
        "_phone_only": args.layout == "phone",
        **({"layout": "phone_only"} if args.layout == "phone" else {}),
        "platform_notes": "Use a clean demo device. Never expose personal accounts.",
        "setup": [
            {"step": "kill_all_apps"},
            {"step": "wake_unlock"},
            {"step": "shell", "args": {"cmd": "am force-stop " + shlex.quote(skill.fingerprint.app_package)}},
            {"step": "launch_app", "args": {"package": skill.fingerprint.app_package}},
        ],
        "timeline": timeline,
        "env": {"ANDROID_SERIAL": args.device, "DEFAULT_DEVICE": args.device, "GHOST_DEVICE": args.device},
        "outro": {"cta_line": f"ghost skill install {skill.author}/{skill.name}", "cta_link": "/skills/"},
        "highlight_window": {"start_s": 2, "end_s": 10},
    }
    if not math.isfinite(getattr(args, "phone_offset", 3.0)) or getattr(args, "phone_offset", 3.0) < 0:
        raise ValueError("--phone-offset must be a finite nonnegative number")
    if args.record_size and not re.fullmatch(r"[1-9][0-9]*x[1-9][0-9]*", args.record_size):
        raise ValueError("--record-size must be WxH")
    long_side, crf = int(getattr(args, "long_side", 720)), int(getattr(args, "crf", 41))
    if not 240 <= long_side <= 1920 or long_side % 2 or not 0 <= crf <= 63:
        raise ValueError("--long-side must be an even 240..1920 and --crf 0..63")
    mcp_env = {
        "ANDROID_SERIAL": args.device,
        "DEFAULT_DEVICE": args.device,
        "GHOST_DEVICE": args.device,
        # The checkout's own gitd, not whatever android-agent-mcp is installed on PATH.
        "PYTHONPATH": str(REPO_ROOT),
    }
    if mode == "soft":
        mcp_env["GHOST_MCP_PROFILE"] = "soft-only"
    render_host = getattr(args, "render_host", None)
    if render_host and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,252}", render_host):
        raise ValueError("--render-host must be an SSH hostname or alias without shell syntax")
    socket = "tcp:" + render_host + ":5037" if render_host else os.environ.get("ADB_SERVER_SOCKET")
    if socket:
        mcp_env["ADB_SERVER_SOCKET"] = socket
        spec["env"]["ADB_SERVER_SOCKET"] = socket
    engine_args = [
        "python3",
        "-m",
        "gitd.ghost_cli",
        "skill",
        "run",
        os.path.relpath(skill.skill_dir.resolve(), REPO_ROOT),
        action.name,
        "--live-trace",
        "--record",
    ]
    for key, value in resolved.items():
        if value is None:
            continue
        engine_args.extend(["--param", f"{key}={value}" if isinstance(value, str) else f"{key}={json.dumps(value)}"])
    engine_cmd = shlex.join(engine_args)
    agent_prompt = (
        prompt
        + "\nRun this action exactly once using this command to retain its signed evidence: "
        + engine_cmd
        + "\nUse Ghost MCP to inspect the resulting phone state, then answer in one or two sentences."
    )
    if mode == "soft":
        agent_prompt = (
            prompt + "\nRead this skill's SOFT.md reference notes with get_skill_notes before acting. "
            "Use live Ghost MCP tools to complete the task and inspect the result; do not replay an action."
        )
    if args.agent == "claude":
        spec["timeline"][0]["args"]["cmd"] = shlex.join(["claude", "--mcp-config", "<workdir>/mcp.json", agent_prompt])
    elif args.agent == "cli":
        spec["timeline"][0]["args"]["cmd"] = shlex.join(["ghost", agent_prompt])
    return {
        "spec": spec,
        "serial": args.device,
        "out": str(Path(args.out) if args.out else skill.skill_dir / "demos" / f"{action.name}.webm"),
        "artifact_dir": str(skill.skill_dir / "runs"),
        "action": action.name,
        "demos_dir": str(skill.skill_dir / "demos"),
        "spec_out": str(skill.skill_dir / "demos" / f"{action.name}.spec.yaml"),
        "legacy_out": str(skill.skill_dir / "demo.webm") if action.name == skill.action_names()[0] else None,
        "engine_command": engine_cmd,
        "agent_prompt": agent_prompt,
        "params": resolved,
        "copy_entry": {"id": spec["demo"], "title": spec["title"], "ctas": [{"url": "/skills/"}]},
        "mcp_config": {
            "mcpServers": {
                "android-agent": {"command": sys.executable, "args": ["-m", "gitd.mcp_server"], "env": mcp_env}
            }
        },
        "agent": args.agent,
        "mode": mode,
        "max_tokens": getattr(args, "max_tokens", 12000),
        "trim_idle": getattr(args, "trim_idle", False),
        "layout": args.layout,
        "prompt": prompt,
        "ocr": not args.no_ocr,
        "physical_account_override": args.i_know,
        "render_host": render_host,
        "render_root": getattr(args, "render_root", "~/ghost-in-the-droid"),
        "render_python": getattr(args, "render_python", "python3"),
        "recorder": str(REPO_ROOT / "scripts/showcase/record_skill_demo.py"),
        "claude_auth": "Soft mode requires authentication; legacy agent selection may fall back to engine",
        "terminal_columns": 60,
        "phone_offset_s": getattr(args, "phone_offset", 3.0),
        "limits": {
            "codec": "vp9",
            "long_side_px": long_side,
            "crf": crf,
            "audio": False,
            "max_duration_s": 30,
            "warn_bytes": 1_500_000,
            "max_bytes": 3_000_000,
        },
    }


def print_plan(plan):
    """Print the full generated spec and explicit post-processing contract."""
    output = dict(plan)
    from gitd.skills.engine.split_demo import dry_commands

    output["commands"] = dry_commands(plan)

    print(json.dumps(output, indent=2, ensure_ascii=False))


def load_recorder():
    import importlib.util

    path = REPO_ROOT / "scripts" / "record_demo.py"
    module_spec = importlib.util.spec_from_file_location("_ghost_skill_record_demo", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def tool_check(plan):
    import shutil

    tools = ["adb", "asciinema", "ssh", "scp"]
    tools.append({"claude": "claude", "cli": "ghost", "engine": "python3"}[plan["agent"]])
    hints = {
        "ssh": "Linux: install openssh-client; macOS: built-in ssh; Windows: enable OpenSSH Client.",
        "scp": "Linux: install openssh-client; macOS: built-in scp; Windows: enable OpenSSH Client.",
        "adb": "Linux: install android-tools-adb; macOS: brew install --cask android-platform-tools; Windows: install Android platform-tools.",
        "asciinema": "Linux: install asciinema; macOS: brew install asciinema; Windows: use WSL and install asciinema.",
        "agg": "Linux/macOS/WSL: cargo install --git https://github.com/asciinema/agg; Windows: use WSL.",
        "ffmpeg": "Linux: install ffmpeg; macOS: brew install ffmpeg; Windows: install ffmpeg and add it to PATH.",
        "tesseract": "Linux: install tesseract-ocr; macOS: brew install tesseract; Windows: install Tesseract and add it to PATH.",
        "claude": "Linux/macOS/Windows: install Claude Code using the official installer.",
        "ghost": "Linux/macOS/Windows: python3 -m pip install ghost-in-the-droid.",
        "python3": "Linux/macOS/Windows: install Python 3.11 or newer.",
    }
    return [(tool, hints[tool]) for tool in tools if not shutil.which(tool)]


def capture_command(plan, workdir):
    cast = str(Path(workdir) / "terminal.cast")
    if plan["agent"] == "claude":
        command = [
            sys.executable,
            str(REPO_ROOT / "scripts/showcase/claude_tui_driver.py"),
            "--prompt",
            plan["agent_prompt"],
            "--mcp-config",
            str(Path(workdir) / "mcp.json"),
            "--cast",
            cast,
            "--cols",
            "60",
            "--rows",
            "28",
            "--max-run",
            "120",
            "--model",
            "haiku",
            "--max-tokens",
            str(plan.get("max_tokens", 12000)),
        ]
        if plan.get("mode") == "soft":
            command.append("--notes-only")
        for key, value in plan["spec"]["env"].items():
            command.extend(["--env", f"{key}={value}"])
        return command
    command = shlex.join(["ghost", plan["agent_prompt"]]) if plan["agent"] == "cli" else plan["engine_command"]
    return ["asciinema", "rec", "--overwrite", "--cols", "60", "--rows", "28", "-c", command, cast]


def transcode_command(source, destination, long_side=720, crf=41, speed=1.0):
    """speed > 1 plays the composite faster (uniformly) so a long agent session fits 30 s."""
    tempo = f"setpts=PTS/{speed:.4f}," if speed > 1.0 else ""
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-t",
        "30",
        "-vf",
        f"{tempo}scale=w='if(gte(iw,ih),{long_side},-2)':h='if(gte(iw,ih),-2,{long_side})',setsar=1",
        "-c:v",
        "libvpx-vp9",
        "-crf",
        str(crf),
        "-b:v",
        "0",
        "-deadline",
        "good",
        "-cpu-used",
        "2",
        "-row-mt",
        "1",
        "-an",
        str(destination),
    ]


def check_size(path):
    size = Path(path).stat().st_size
    if size > 3_000_000:
        raise ValueError("Demo exceeds 3 MB; reduce duration or content complexity")
    if size > 1_500_000:
        print("Warning: demo exceeds 1.5 MB", flush=True)


def require_clean_device(dev, override):
    emulator = dev.adb("shell", "getprop", "ro.kernel.qemu", timeout=5).strip() == "1"
    if emulator or override:
        return
    # AccountManager cannot establish whether an account is personal. Refuse
    # any physical device with accounts, or an unreadable account report.
    import re

    report = dev.adb_soft("shell", "dumpsys", "account", timeout=5)
    counts = re.findall(r"Accounts:\s*(\d+)", report.stdout or "")
    if report.returncode != 0 or not counts or any(int(n) for n in counts):
        raise RuntimeError(
            "Physical phone has accounts or account state is unknown; use a clean demo device or --i-know"
        )


def load_skill_recorder():
    import importlib.util

    path = REPO_ROOT / "scripts/showcase/record_skill_demo.py"
    spec = importlib.util.spec_from_file_location("_ghost_seed_skill_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(plan, recorder):
    import subprocess

    from gitd.skills.engine.split_demo import record_split

    try:
        return record_split(plan, recorder)
    except subprocess.SubprocessError as exc:
        raise RuntimeError(f"Split-host recording stage failed ({type(exc).__name__}); no clip published") from exc


def render_commands(plan):
    """Build exact agg/ffmpeg argv using the showcase functions without running tools."""
    import tempfile

    recorder = load_recorder()
    recorder.TERM_COLS = 60
    commands = []
    recorder.run = lambda command, *args, **kwargs: commands.append(command)
    with tempfile.TemporaryDirectory(prefix="ghost-demo-plan-") as temporary:
        workdir = Path(temporary)
        # Planning only: the recorder pre-processes the cast text, so give it an empty one.
        (workdir / "terminal_scrubbed.cast").write_text("")
        recorder.render_terminal(workdir / "terminal_scrubbed.cast", workdir / "terminal.mp4", workdir)
        preview_spec = dict(plan["spec"])
        preview_spec["demo"] = "mcp-claude-code"
        recorder.composite(
            preview_spec,
            workdir,
            workdir / "terminal.mp4",
            workdir / "phone.mp4",
            -plan["phone_offset_s"],
            workdir / "composite.webm",
        )
        return [
            [
                value.replace(temporary, "<workdir>")
                .replace(str(recorder.BRAND_DIR), "<workdir>/showcase/_brand")
                .replace("intro-mcp-claude-code.png", f"intro-{plan['spec']['demo']}.png")
                for value in command
            ]
            for command in commands
        ]


def build_plans(skill, args, params):
    from copy import copy

    selected = getattr(args, "action", None)
    legacy = getattr(args, "legacy_action", None)
    subset = getattr(args, "actions", None)
    if subset and (selected or legacy):
        raise ValueError("--actions cannot be combined with --action or a positional action")
    if selected and legacy:
        raise ValueError("Use --action or the legacy positional action, not both")
    selected = selected or legacy
    names = [name.strip() for name in subset.split(",")] if subset else [selected] if selected else skill.action_names()
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("--actions must contain unique, nonempty action names")
    if not names:
        raise ValueError("Skill has no actions to record")
    if args.out and len(names) != 1:
        raise ValueError("--out requires --action when recording multiple actions")
    try:
        actions = [skill.action(name) for name in names]
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    accepted = {param.name for action in actions for param in action.params}
    unknown = set(params) - accepted
    if unknown:
        raise ValueError(f"Unknown demo params: {sorted(unknown)}")
    plans = []
    for action in actions:
        single = copy(args)
        single.action = action.name
        # skill.yaml demo_params are per-action defaults (all-actions mode needs no flags);
        # an explicit --param overrides them.
        action_params = {
            **(getattr(action, "demo_params", None) or {}),
            **{key: value for key, value in params.items() if action.param(key)},
        }
        plans.append(build_plan(skill, single, action_params))
    return plans


def warn_folder_size(directory):
    size = sum(path.stat().st_size for path in Path(directory).rglob("*") if path.is_file())
    if size > 10_000_000:
        print("Warning: demos/ folder exceeds 10 MB", flush=True)


def validate_plan(plan, recorder):
    spec = dict(plan["spec"])
    spec["demo"] = "mcp-claude-code"
    return recorder.validate_spec(spec)


def select_agent(args):
    """Claude auth is checked only for real recordings, never during dry planning."""
    if getattr(args, "mode", None):
        args.agent = "engine" if args.mode == "hard" else "claude"
    if args.agent != "claude" or args.dry:
        return
    import shutil
    import subprocess

    authenticated = False
    if shutil.which("claude"):
        try:
            result = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, timeout=5)
            authenticated = result.returncode == 0 and json.loads(result.stdout).get("loggedIn") is True
        except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
            pass
    if not authenticated:
        if getattr(args, "mode", None) == "soft":
            raise ValueError("Soft mode requires an authenticated Claude Code session; no replay fallback")
        print("Claude authentication unavailable; using the deterministic engine pane.", flush=True)
        args.agent = "engine"
