#!/usr/bin/env python3
"""AndroidWorld agent arms: ``before`` (agent with Ghost MCP, skill tools hidden) and ``after_mcp``
(same agent, skill tools visible, the hub skill installed). One non-interactive agent turn per seed,
scored by AndroidWorld's own evaluator through ``tools/bench/aw_bridge.py``.

Per seed: stop the app, bridge ``init`` (seeded params, Markor file, database), run ONE ``claude -p``
(or another CLI given with ``--agent-cmd``) with the task goal on stdin and the Ghost MCP server
attached, stop the app, bridge ``score``, ``teardown``. Each run leaves the CLI transcript as JSONL
(paths and account strings scrubbed), a signed run artifact with the nested ``bench`` block under
``<skill>/bench/agent-runs/`` (outside ``runs/`` and ``verifications/``: an agent episode is bench
evidence, never a skill run the registry scores), and a row in ``bench/androidworld.json``.

Cost rules: subscription CLIs only, one attempt per seed, the arm stops on the first rate limit.

Example:
    ADB_SERVER_SOCKET=tcp:127.0.0.1:6037 python3 tools/bench/agent_arm.py skillhub/androidworld/pro-expense \\
      --androidworld ExpenseAddMultipleFromMarkor --arms before,after_mcp --n 3 --device emulator-5554 \\
      --model haiku --bridge-cmd "ssh agent-host.example docker exec -i -e PYTHONPATH=/ aw-emu-f1 python3 /work/aw_bridge.py ..."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from gitd.skills.engine import bench as bench_mod  # noqa: E402
from gitd.skills.engine.androidworld import action_name as aw_action_name  # noqa: E402
from gitd.skills.engine.loader import load_skill  # noqa: E402
from gitd.skills.engine.runner import RunResult  # noqa: E402

ARMS = ("before", "after_mcp", "after_replay")
MCP_SERVER = "ghost"
# Everything that runs or finds a skill; the rest of the MCP surface is identical in both arms.
SKILL_TOOLS = (
    "run_skill,run_skill_resume,find_skill,list_skills,run_action,run_workflow,run_flow,create_skill,explore_app"
)
FIXED_SENTENCE = (
    "The phone is an Android device with serial {serial}; it is already connected and unlocked. "
    "Use your tools to do this on the phone. When the task is complete, reply with the single word DONE."
)
RATE_LIMIT_RE = re.compile(r"rate.?limit|usage limit|quota|\b429\b|overloaded", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def install_local(skill_dir: Path, skills_dir: Path) -> str:
    """Lay the skill out the way ``ghost skill install`` does (``<author>/<slug>/<version>/`` + ``@latest``).
    ``demos/`` stays: the schema check refuses a skill whose ``demo:`` file is missing."""
    raw = yaml.safe_load((skill_dir / "skill.yaml").read_text()) or {}
    author, slug, version = str(raw["author"]), str(raw["name"]), str(raw["version"])
    dest = skills_dir / author / slug / version
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(skill_dir, dest, ignore=shutil.ignore_patterns("__pycache__", "runs", "verifications", "bench"))
    latest = dest.parent / "@latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(version)
    return f"{author}/{slug}"


def mcp_config(path: Path, *, worktree: Path, serial: str, skills_dir: Path, hide: str, mcp_host: str = "") -> Path:
    """MCP config for the agent; with ``mcp_host`` the server is started over ssh on that host (the agent
    CLI runs elsewhere, the device tools stay next to the adb tunnel)."""
    env = {
        "GHOST_DEVICE": serial,
        "DEFAULT_DEVICE": serial,
        "ANDROID_SERIAL": serial,
        "GHOST_SKILLS_DIR": str(skills_dir),
        "PYTHONPATH": str(worktree),
        "GHOST_MCP_HIDE_TOOLS": hide,
    }
    if os.environ.get("ADB_SERVER_SOCKET"):
        env["ADB_SERVER_SOCKET"] = os.environ["ADB_SERVER_SOCKET"]
    if mcp_host:
        remote = (
            f"cd {shlex.quote(str(worktree))} && env {' '.join(f'{k}={shlex.quote(v)}' for k, v in env.items())} "
            f"{shlex.quote(sys.executable)} -m gitd.mcp_server"
        )
        server = {"command": "ssh", "args": ["-o", "BatchMode=yes", mcp_host, remote]}
    else:
        server = {"command": sys.executable, "args": ["-m", "gitd.mcp_server"], "cwd": str(worktree), "env": env}
    path.write_text(json.dumps({"mcpServers": {MCP_SERVER: server}}))
    return path


def claude_command(agent_cmd: str, *, model: str, max_turns: int, config: Path, agent_host: str = "") -> list[str]:
    """The prompt goes on stdin, so the variadic tool flags cannot swallow it. The agent runs in an empty
    directory with project settings only, so no CLAUDE.md, user hook or memory enters its context; with
    ``agent_host`` the CLI runs on that host over ssh and the MCP config travels inline."""
    mcp_arg = config.read_text() if agent_host else str(config)
    args = [
        *agent_cmd.split(),
        "-p",
        "--model",
        model,
        "--max-turns",
        str(max_turns),
        "--mcp-config",
        mcp_arg,
        "--strict-mcp-config",
        "--tools",
        "",
        "--allowedTools",
        f"mcp__{MCP_SERVER}",
        f"mcp__{MCP_SERVER}__*",
        "--setting-sources",
        "project",
        "--no-session-persistence",
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if agent_host:
        return ["ssh", "-o", "BatchMode=yes", agent_host, f'cd "$(mktemp -d)" && {shlex.join(args)}']
    return args


def missing_packages(device: str, packages: list[str]) -> list[str]:
    """Packages from ``packages`` that are not installed on ``device`` (fake devices have everything)."""
    if not device or device.startswith(("fake:", "ios:")):
        return []
    missing = []
    for package in packages:
        proc = subprocess.run(
            ["adb", "-s", device, "shell", "pm", "path", package],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if "package:" not in proc.stdout:
            missing.append(package)
    return missing


def scrub(text: str) -> str:
    text = text.replace(str(Path.home()), "~")
    return EMAIL_RE.sub("<email>", text)


def parse_transcript(lines: list[str]) -> dict:
    """Tool calls, model, usage and verdict out of ``--output-format stream-json`` lines."""
    out = {
        "tool_calls": 0,
        "model": None,
        "num_turns": None,
        "is_error": None,
        "subtype": None,
        "result": None,
        "usage": {},
        "rate_limited": False,
        "tool_names": [],
        "cli_version": None,
        "tool_errors": 0,
    }
    message_ids: set[str] = set()
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            out["cli_version"] = event.get("claude_code_version") or out["cli_version"]
        elif event.get("type") == "assistant":
            message = event.get("message") or {}
            out["model"] = message.get("model") or out["model"]
            if message.get("id"):
                message_ids.add(str(message["id"]))  # one API response may stream as several events
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    out["tool_calls"] += 1
                    out["tool_names"].append(str(block.get("name")))
        elif event.get("type") == "user":
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and tool_failed(block):
                    out["tool_errors"] += 1
        elif event.get("type") == "result":
            out["num_turns"] = event.get("num_turns")
            out["is_error"] = bool(event.get("is_error"))
            out["subtype"] = event.get("subtype")
            out["result"] = event.get("result")
            out["usage"] = event.get("usage") or {}
            # Only the error text can name a rate limit; token counts in `usage` contain any digits.
            text = " ".join(str(event.get(k) or "") for k in ("result", "error", "subtype"))
            if out["is_error"] and RATE_LIMIT_RE.search(text):
                out["rate_limited"] = True
    usage = out["usage"]
    out["tokens"] = int(
        sum(
            int(usage.get(k) or 0)
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
        )
    )
    out["token_breakdown"] = {
        k: int(usage.get(k) or 0)
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    }
    out["llm_calls"] = len(message_ids)
    out["ui_actions"] = ui_actions(out["tool_names"])
    out["skill_calls"] = [n for n in out["tool_names"] if n.split("__")[-1] in SKILL_RUN_TOOLS]
    return out


# Tool name (after the mcp__ghost__ prefix) -> UI action kind; reads, waits and skill calls are not UI actions.
UI_ACTION_KINDS = {
    "tap": "tap",
    "tap_element": "tap",
    "long_press": "tap",
    "type_text": "type",
    "paste_text": "type",
    "swipe": "swipe",
    "scroll": "swipe",
    "press_back": "key",
    "press_home": "key",
    "press_key": "key",
    "launch_app": "launch",
    "launch_intent": "launch",
    "open_url": "launch",
    "force_stop": "launch",
}
# run_flow is a batch of plain UI tool calls, not a skill, so it does not count as one.
SKILL_RUN_TOOLS = ("run_skill", "run_action", "run_workflow")


def ui_actions(tool_names: list[str]) -> dict:
    counts = {"tap": 0, "type": 0, "swipe": 0, "key": 0, "launch": 0}
    for name in tool_names:
        kind = UI_ACTION_KINDS.get(name.split("__")[-1])
        if kind:
            counts[kind] += 1
    counts["total"] = sum(counts.values())
    return counts


def tool_failed(block: dict) -> bool:
    if block.get("is_error"):
        return True
    content = block.get("content")
    text = content if isinstance(content, str) else json.dumps(content)[:400]
    return bool(re.search(r'"result":\s*"(ERROR|FAILED)|^(ERROR|FAILED)', text))


def running_tokens(line: str, seen: dict[str, int]) -> None:
    """Fold one stream-json line into ``seen`` (message id -> tokens that API call processed)."""
    try:
        event = json.loads(line)
    except ValueError:
        return
    if isinstance(event, dict) and event.get("type") == "assistant":
        message = event.get("message") or {}
        usage = message.get("usage") or {}
        if message.get("id"):
            seen[str(message["id"])] = sum(
                int(usage.get(k) or 0)
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
            )


def run_agent(command: list[str], prompt: str, transcript: Path, timeout_s: float, token_cap: int = 0) -> dict:
    """One agent episode; killed (``timed_out`` / ``over_cap``) past ``timeout_s`` or ``token_cap`` tokens."""
    started = time.monotonic()
    lines: list[str] = []
    seen: dict[str, int] = {}
    timed_out = over_cap = False
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=tempfile.mkdtemp(prefix="aw-agent-cwd-"),
    )
    stderr_chunks: list[str] = []
    reader = threading.Thread(target=lambda: stderr_chunks.append(proc.stderr.read()), daemon=True)
    reader.start()
    proc.stdin.write(prompt)
    proc.stdin.close()
    deadline = started + timeout_s
    stdout_done = threading.Event()

    def pump():
        for line in proc.stdout:
            lines.append(line.rstrip("\n"))
            running_tokens(line, seen)
        stdout_done.set()

    threading.Thread(target=pump, daemon=True).start()
    while not stdout_done.wait(1.0):
        if time.monotonic() > deadline:
            timed_out = True
        elif token_cap and sum(seen.values()) > token_cap:
            over_cap = True
        if timed_out or over_cap:
            proc.kill()
            break
    returncode = proc.wait()
    reader.join(5)
    stderr = "timeout" if timed_out else "".join(stderr_chunks)
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("\n".join(scrub(line) for line in lines) + "\n")
    parsed = parse_transcript(lines)
    if over_cap or timed_out:
        parsed["tokens"] = max(parsed["tokens"], sum(seen.values()))  # no result event after a kill
    parsed.update(
        {
            "wall_ms": int((time.monotonic() - started) * 1000),
            "returncode": returncode,
            "timed_out": timed_out,
            "over_cap": over_cap,
            "stderr_tail": scrub(stderr[-800:]) if stderr else "",
        }
    )
    if returncode != 0 and RATE_LIMIT_RE.search(parsed["stderr_tail"] or ""):
        parsed["rate_limited"] = True
    return parsed


def run_arm(
    arm: str,
    *,
    skill,
    task: str,
    seeds: list[int],
    device: str,
    bridge,
    agent_cmd: str,
    model: str,
    max_turns: int,
    worktree: Path,
    out_dir: Path,
    timeout_s: float,
    run_id: str = "",
    agent_host: str = "",
    mcp_host: str = "",
    require: list[str] = (),
    token_cap: int = 0,
    budget: dict | None = None,
    cap_is_fail: bool = False,
    progress=print,
) -> tuple[list[dict], str | None]:
    """Cells for one arm; returns (cells, blocker). A blocker (rate limit, token cap, a task app missing
    before or after an episode) stops the arm: later seeds would not be measurements."""
    action = aw_action_name(task)
    skills_dir = Path(tempfile.mkdtemp(prefix=f"aw-{arm}-skills-"))
    hide = SKILL_TOOLS if arm == "before" else ""
    installed = install_local(skill.skill_dir, skills_dir) if arm == "after_mcp" else None
    config = mcp_config(
        Path(tempfile.mkdtemp(prefix="aw-mcp-")) / "mcp.json",
        worktree=worktree,
        serial=device,
        skills_dir=skills_dir,
        hide=hide,
        mcp_host=mcp_host,
    )
    from gitd.skills.engine.evidence import collect_fingerprint

    fingerprint = collect_fingerprint(skill, device)
    packages = sorted({skill.fingerprint.app_package, *require} - {None, ""})
    run_dir = out_dir / run_id if run_id else out_dir
    cells, blocker = [], None
    for seed in seeds:
        # A run-level budget shrinks each episode's cap to what is left, so the total can never pass it.
        cap = token_cap
        if budget is not None:
            left = budget["limit"] - budget["spent"]
            if left <= 0:
                blocker = f"{arm} seed {seed}: run budget of {budget['limit']} tokens spent; stopped"
                progress("BLOCKER " + blocker)
                break
            cap = min(cap, left) if cap else left
        gone = missing_packages(device, packages)
        if gone:
            blocker = f"{arm} seed {seed}: task app(s) not installed before the episode: {gone}; arm stopped"
            progress("BLOCKER " + blocker)
            break
        cell = {
            "suite": bench_mod.SUITE,
            "task_id": task,
            "arm": arm,
            "seed": seed,
            "action": action,
            "installed": installed,
            "hidden_tools": hide,
            "run_id": run_id,
            "agent_host": agent_host or "local",
            "required_packages": packages,
            "device_fingerprint": fingerprint.as_dict() if hasattr(fingerprint, "as_dict") else fingerprint,
        }
        started = time.monotonic()
        bench_mod.force_stop(device, skill.fingerprint.app_package)
        try:
            init = bridge.request("init", task=task, seed=seed)
            cell["instance_seed"] = init.get("instance_seed")
            prompt = f"{init.get('goal')}\n\n{FIXED_SENTENCE.format(serial=device)}\n"
            cell["prompt"] = prompt
            transcript = run_dir / f"{arm}-{seed}.jsonl"
            command = claude_command(agent_cmd, model=model, max_turns=max_turns, config=config, agent_host=agent_host)
            agent = run_agent(command, prompt, transcript, timeout_s, token_cap=cap)
            if budget is not None:
                budget["spent"] += int(agent.get("tokens") or 0)
            cell.update(
                {
                    k: agent.get(k)
                    for k in (
                        "tool_calls",
                        "tool_names",
                        "model",
                        "num_turns",
                        "is_error",
                        "subtype",
                        "result",
                        "usage",
                        "tokens",
                        "token_breakdown",
                        "llm_calls",
                        "ui_actions",
                        "skill_calls",
                        "tool_errors",
                        "cli_version",
                        "returncode",
                        "timed_out",
                        "over_cap",
                        "rate_limited",
                        "stderr_tail",
                    )
                }
            )
            cell["agent_wall_ms"] = agent.get("wall_ms")
            cell["transcript"] = (
                str(transcript.relative_to(worktree)) if transcript.is_relative_to(worktree) else str(transcript)
            )
            cell["said_done"] = bool(agent.get("result")) and "DONE" in str(agent.get("result"))
            bench_mod.force_stop(device, skill.fingerprint.app_package)
            if agent.get("over_cap") and cap_is_fail and cap == token_cap:
                # Protocol v3: the per-episode cap is the same in both arms and a capped episode is a fail in its
                # arm, counted, with no score taken. A cut by the run budget (a smaller cap) is never this.
                cell.update(
                    {
                        "success": False,
                        "is_successful": 0.0,
                        "capped": True,
                        "counted_as": f"fail (per-episode cap {token_cap} tokens)",
                    }
                )
            elif agent.get("rate_limited") or agent.get("timed_out") or agent.get("over_cap"):
                # An episode the CLI or the cap cut short is not a measurement: no score, no artifact.
                reason = (
                    "rate limit"
                    if agent.get("rate_limited")
                    else "timeout"
                    if agent.get("timed_out")
                    else f"token cap {cap}"
                )
                cell.update({"success": False, "is_successful": 0.0, "error": f"agent: {reason}"})
            else:
                score = bridge.request("score")
                cell["is_successful"] = float(score["is_successful"])
                cell["success"] = cell["is_successful"] == 1.0
        except bench_mod.BridgeError as exc:
            cell.update({"success": False, "is_successful": 0.0, "error": f"bridge: {exc}"})
        finally:
            try:
                bridge.request("teardown")
            except bench_mod.BridgeError as exc:
                cell.setdefault("error", f"teardown: {exc}")
        cell["wall_ms"] = int((time.monotonic() - started) * 1000)
        cell["steps"] = int(cell.get("tool_calls") or 0)
        cell["tokens"] = int(cell.get("tokens") or 0)
        # The agent's own damage (an uninstalled task app) is its failure, but it poisons every later seed.
        cell["packages_lost"] = missing_packages(device, packages)
        if fingerprint is not None and "error" not in cell:
            from gitd.skills.engine.evidence import write_evidence

            result = RunResult(
                success=cell["success"],
                skill=f"{skill.author}/{skill.name}",
                action=action,
                duration_ms=float(cell["wall_ms"]),
                data={
                    "agent": {
                        k: cell.get(k)
                        for k in (
                            "model",
                            "num_turns",
                            "tool_calls",
                            "usage",
                            "said_done",
                            "subtype",
                            "llm_calls",
                            "ui_actions",
                            "skill_calls",
                            "tool_errors",
                        )
                    }
                },
            )
            block = {
                k: cell[k]
                for k in (
                    "suite",
                    "task_id",
                    "arm",
                    "seed",
                    "instance_seed",
                    "steps",
                    "tokens",
                    "wall_ms",
                    "is_successful",
                )
                if k in cell
            }
            block["trace_path"] = cell.get("transcript") or ""
            artifact_dir = (
                skill.skill_dir / "bench" / "agent-runs" / run_id
                if run_id
                else skill.skill_dir / "bench" / "agent-runs"
            )
            written = write_evidence(
                skill,
                [result],
                fingerprint,
                artifact_dir=artifact_dir,
                simulated=device.startswith("fake:"),
                bench=block,
                model=str(cell.get("model") or model),
            )
            final = artifact_dir / f"{arm}-{seed}.json"
            if final.exists():
                final.unlink()
            written.rename(final)
            cell["artifact"] = str(final)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / f"{arm}-{seed}.cell.json").write_text(json.dumps(cell, indent=2, default=str) + "\n")
        verdict = "PASS" if cell.get("success") else "FAIL"
        progress(
            f"{task} arm={arm} seed={seed} androidworld={verdict} turns={cell.get('num_turns')} llm_calls={cell.get('llm_calls')} "
            f"ui_actions={(cell.get('ui_actions') or {}).get('total')} skill_calls={len(cell.get('skill_calls') or [])} "
            f"tokens={cell.get('tokens')} {cell['wall_ms']} ms model={cell.get('model')}"
        )
        cells.append(cell)
        if cell.get("rate_limited"):
            blocker = f"{arm} seed {seed}: rate limit from the agent CLI, arm stopped (no retries by rule)"
        elif cell.get("over_cap") and not cell.get("capped"):
            blocker = f"{arm} seed {seed}: episode passed the {cap}-token cap, arm stopped"
        elif cell["packages_lost"]:
            blocker = f"{arm} seed {seed}: the episode removed task app(s) {cell['packages_lost']}; arm stopped"
        if blocker:
            progress("BLOCKER " + blocker)
            break
    return cells, blocker


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("skill", help="Skill dir or hub ref (installed for the after_mcp arm)")
    ap.add_argument("--androidworld", required=True, metavar="TASK")
    ap.add_argument("--arms", default="before,after_mcp")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--seed-base", type=int, default=30)
    ap.add_argument("--device", default=os.environ.get("GHOST_DEVICE", ""))
    ap.add_argument("--bridge-cmd", required=True)
    ap.add_argument("--agent-cmd", default="claude", help="CLI to run (default claude); tests pass a fake")
    ap.add_argument(
        "--model", default="haiku", help="Cheapest subscription model; the transcript records what answered"
    )
    ap.add_argument("--max-turns", type=int, default=25)
    ap.add_argument("--timeout-s", type=float, default=1500)
    ap.add_argument("--out-dir", default="bench-out/agent-arm")
    ap.add_argument("--worktree", default=str(REPO))
    ap.add_argument("--upstream-commit")
    ap.add_argument("--run-id", default="", help="Subdir for transcripts, cells and artifacts (default: none)")
    ap.add_argument("--agent-host", default="", help="ssh alias to run the agent CLI on (its own login there)")
    ap.add_argument(
        "--mcp-host", default="", help="ssh alias, as seen from --agent-host, that starts the MCP server here"
    )
    ap.add_argument(
        "--require-packages", default="", help="Comma list of task apps that must be installed (besides the skill app)"
    )
    ap.add_argument(
        "--token-cap", type=int, default=3_000_000, help="Kill an episode past this many tokens; 0 = no cap"
    )
    ap.add_argument(
        "--budget-tokens", type=int, default=0, help="Hard limit on agent tokens for the whole run; 0 = none"
    )
    ap.add_argument(
        "--cap-is-fail", action="store_true", help="Protocol v3: a capped episode counts as a fail and the arm goes on"
    )
    ap.add_argument("--no-summary", action="store_true", help="Leave bench/androidworld.json alone")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    bad = [a for a in arms if a not in ARMS]
    if bad:
        print(f"unknown arms {bad}; choose from {ARMS}", file=sys.stderr)
        return 2
    if not args.device:
        print("--device required", file=sys.stderr)
        return 2
    worktree = Path(args.worktree).resolve()
    skill = load_skill(args.skill)
    seeds = [args.seed_base + i for i in range(args.n)]
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = worktree / out_dir
    cells, blockers = [], []
    budget = {"limit": args.budget_tokens, "spent": 0} if args.budget_tokens else None
    with bench_mod.AWBridge(bench_mod.bridge_command(args.bridge_cmd)) as bridge:
        hello = bridge.request("hello")
        if hello.get("tasks") and args.androidworld not in hello["tasks"]:
            print(f"{args.androidworld}: not an AndroidWorld task on this bridge", file=sys.stderr)
            return 2
        for arm in arms:
            if arm == "after_replay":
                # Same bridge and seeds, no model; cells persist next to the agent arms (no registry runs/).
                run_dir = out_dir / args.run_id if args.run_id else out_dir
                run_dir.mkdir(parents=True, exist_ok=True)
                arm_cells = bench_mod.replay_task(
                    skill, args.androidworld, seeds=seeds, device=args.device, bridge=bridge, record=False
                )
                for cell in arm_cells:
                    cell.update(
                        {
                            "run_id": args.run_id,
                            "llm_calls": 0,
                            "model": None,
                            "ui_actions": {"total": cell.get("steps", 0)},
                        }
                    )
                    (run_dir / f"after_replay-{cell['seed']}.cell.json").write_text(
                        json.dumps(cell, indent=2, default=str) + "\n"
                    )
                cells += arm_cells
                continue
            arm_cells, blocker = run_arm(
                arm,
                skill=skill,
                task=args.androidworld,
                seeds=seeds,
                device=args.device,
                bridge=bridge,
                agent_cmd=args.agent_cmd,
                model=args.model,
                max_turns=args.max_turns,
                worktree=worktree,
                out_dir=out_dir,
                timeout_s=args.timeout_s,
                run_id=args.run_id,
                agent_host=args.agent_host,
                mcp_host=args.mcp_host,
                require=[p.strip() for p in args.require_packages.split(",") if p.strip()],
                token_cap=args.token_cap,
                budget=budget,
                cap_is_fail=args.cap_is_fail,
            )
            cells += arm_cells
            if blocker:
                blockers.append(blocker)
                break
    measured = [c for c in cells if "error" not in c]  # a cut-short episode is not a measurement
    if args.json:
        print(json.dumps(cells, indent=2, default=str))
    if not args.no_summary:
        print(f"Bench summary: {bench_mod.write_summary(skill, measured, upstream_commit=args.upstream_commit)}")
    for arm in arms:
        arm_cells = [c for c in cells if c["arm"] == arm]
        if arm_cells:
            print(f"{arm}: {sum(1 for c in arm_cells if c.get('success'))}/{len(arm_cells)} passed")
    if blockers:
        print("BLOCKER: " + "; ".join(blockers))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
