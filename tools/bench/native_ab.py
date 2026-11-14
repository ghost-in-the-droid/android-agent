#!/usr/bin/env python3
"""Ghost-native A/B: one phone task, three arms, scored by a device-state check the skill never sees.

Arms per episode: ``before`` (agent, skill tools hidden), ``after_mcp`` (agent, skill installed and
findable), ``after_replay`` (the skill action run by the engine, no model). Reset, run, score, persist one
``<run>/<task>-<arm>-<seed>.cell.json`` per episode with the same metrics as ``agent_arm.py``.

The scorers read device state directly (UI tree, ContactsProvider, AlarmManager), never the skill's own
validator, so a skill that reports success without doing the task fails here.

Example:
    ADB_SERVER_SOCKET=tcp:127.0.0.1:6038 python3 tools/bench/native_ab.py --task calc_3plus3 \\
      --arms before,after_mcp,after_replay --n 5 --device emulator-5554 --agent-host agent-host.example --mcp-host mcp-host.example --run-id nat1
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools" / "bench"))

import agent_arm  # noqa: E402

from gitd.skills.engine.loader import load_skill  # noqa: E402

ARMS = ("before", "after_mcp", "after_replay")


def adb(device: str, *args: str, timeout: float = 30) -> str:
    proc = subprocess.run(["adb", "-s", device, *args], capture_output=True, text=True, timeout=timeout, check=False)
    return proc.stdout


def ui_texts(device: str) -> dict[str, str]:
    """resource-id -> text for every node in a fresh uiautomator dump."""
    adb(device, "shell", "uiautomator", "dump", "/sdcard/native_ab.xml", timeout=60)
    xml = adb(device, "shell", "cat", "/sdcard/native_ab.xml")
    return {m.group(2): m.group(1) for m in re.finditer(r'text="([^"]*)"[^>]*resource-id="([^"]+)"', xml)}


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


@dataclass
class Task:
    name: str
    skill: str
    action: str
    params: dict
    goal: str
    reset: Callable[[str], None]
    score: Callable[[str], tuple[bool, dict]]
    packages: list[str] = field(default_factory=list)


# ── calculator: "Calculate 3+3" ───────────────────────────────────────────────


def calc_reset(device: str) -> None:
    adb(device, "shell", "am", "force-stop", "org.fossify.math")
    adb(device, "shell", "input", "keyevent", "KEYCODE_HOME")


def calc_score(device: str) -> tuple[bool, dict]:
    """Pass when the Fossify display shows 6 at the end of the episode."""
    shown = ui_texts(device).get("org.fossify.math:id/result", "")
    return shown.replace(",", "").strip() in ("6", "6.0"), {"display": shown}


# ── contacts: create Ada Lovelace ─────────────────────────────────────────────

CONTACT_NAME, CONTACT_PHONE = "Ada Lovelace", "+1 555 0100"


def contacts_rows(device: str) -> list[str]:
    out = adb(
        device,
        "shell",
        "content",
        "query",
        "--uri",
        "content://com.android.contacts/data",
        "--projection",
        "raw_contact_id:display_name:mimetype:data1",
    )
    return [line for line in out.splitlines() if CONTACT_NAME in line]


def contacts_reset(device: str) -> None:
    adb(device, "shell", "am", "force-stop", "com.google.android.contacts")
    ids = {m.group(1) for line in contacts_rows(device) for m in [re.search(r"raw_contact_id=(\d+)", line)] if m}
    for raw_id in ids:
        adb(
            device,
            "shell",
            "content",
            "delete",
            "--uri",
            "content://com.android.contacts/raw_contacts",
            "--where",
            f"_id={raw_id}",
        )
    adb(device, "shell", "input", "keyevent", "KEYCODE_HOME")


def contacts_score(device: str) -> tuple[bool, dict]:
    """Pass when exactly one contact named Ada Lovelace exists and carries the phone number."""
    rows = contacts_rows(device)
    raw_ids = {m.group(1) for line in rows for m in [re.search(r"raw_contact_id=(\d+)", line)] if m}
    phones = [line for line in rows if "phone_v2" in line and digits(CONTACT_PHONE) in digits(line.split("data1=")[-1])]
    return len(raw_ids) == 1 and bool(phones), {"contacts": len(raw_ids), "phone_rows": len(phones)}


# ── clock: alarm 07:30 "Gym" ──────────────────────────────────────────────────


def clock_reset(device: str) -> None:
    adb(device, "shell", "pm", "clear", "com.google.android.deskclock")
    adb(device, "shell", "input", "keyevent", "KEYCODE_HOME")


def clock_score(device: str) -> tuple[bool, dict]:
    """Pass when the alarm manager holds a deskclock alarm clock for 07:30 (the one the Clock app shows)."""
    out = adb(device, "shell", "dumpsys", "alarm")
    shown = sorted(set(re.findall(r"Alarm clock:\s+triggerTime=\d{4}-\d\d-\d\d (\d\d:\d\d)", out)))
    return "07:30" in shown, {"alarm_clocks": shown}


TASKS = {
    "calc_3plus3": Task(
        "calc_3plus3",
        "skillhub/ghost/calculator",
        "calculate",
        {"expression": "3+3"},
        "Calculate 3+3 in the Calculator app.",
        calc_reset,
        calc_score,
        ["org.fossify.math"],
    ),
    "contacts_create": Task(
        "contacts_create",
        "skillhub/ghost/contacts",
        "create_contact",
        {"name": CONTACT_NAME, "phone": CONTACT_PHONE},
        f"Create a new contact named {CONTACT_NAME} with the phone number {CONTACT_PHONE}.",
        contacts_reset,
        contacts_score,
        ["com.google.android.contacts"],
    ),
    "clock_alarm": Task(
        "clock_alarm",
        "skillhub/ghost/clock",
        "set_alarm",
        {"hour": 7, "minute": 30, "label": "Gym"},
        "Set an alarm for 7:30 AM labeled Gym in the Clock app.",
        clock_reset,
        clock_score,
        ["com.google.android.deskclock"],
    ),
}


def run_episode(
    task: Task,
    skill,
    arm: str,
    seed: int,
    *,
    device: str,
    agent_cmd: str,
    model: str,
    max_turns: int,
    worktree: Path,
    run_dir: Path,
    timeout_s: float,
    agent_host: str,
    mcp_host: str,
    token_cap: int,
    configs: dict,
) -> dict:
    cell = {
        "suite": "ghost-native",
        "task_id": task.name,
        "arm": arm,
        "seed": seed,
        "skill": f"{skill.author}/{skill.name}",
        "action": task.action,
        "goal": task.goal,
        "agent_host": agent_host or "local",
        "required_packages": task.packages,
    }
    gone = agent_arm.missing_packages(device, task.packages)
    if gone:
        cell.update({"success": False, "error": f"env: missing {gone}"})
        return cell
    task.reset(device)
    started = time.monotonic()
    if arm == "after_replay":
        from gitd.skills.engine.runner import run_action

        result = run_action(skill, task.action, params=dict(task.params), device_serial=device)
        cell.update(
            {
                "skill_success": bool(result.success),
                "skill_error": result.error,
                "steps": len(result.trace),
                "tokens": 0,
                "llm_calls": 0,
                "model": None,
                "token_breakdown": {},
                "skill_calls": [],
                "ui_actions": {"total": len(result.trace)},
                "tool_errors": 0,
            }
        )
    else:
        prompt = f"{task.goal}\n\n{agent_arm.FIXED_SENTENCE.format(serial=device)}\n"
        cell["prompt"] = prompt
        transcript = run_dir / f"{task.name}-{arm}-{seed}.jsonl"
        command = agent_arm.claude_command(
            agent_cmd, model=model, max_turns=max_turns, config=configs[arm], agent_host=agent_host
        )
        agent = agent_arm.run_agent(command, prompt, transcript, timeout_s, token_cap=token_cap)
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
        cell["steps"] = int(agent.get("tool_calls") or 0)
        cell["transcript"] = (
            str(transcript.relative_to(worktree)) if transcript.is_relative_to(worktree) else str(transcript)
        )
        cell["said_done"] = "DONE" in str(agent.get("result") or "")
        if agent.get("rate_limited") or agent.get("timed_out") or agent.get("over_cap"):
            cell["error"] = "agent: " + (
                "rate limit" if agent.get("rate_limited") else "timeout" if agent.get("timed_out") else "token cap"
            )
    cell["wall_ms"] = int((time.monotonic() - started) * 1000)
    if "error" not in cell:
        ok, evidence = task.score(device)
        cell.update({"success": ok, "score_evidence": evidence})
    else:
        cell["success"] = False
    cell["packages_lost"] = agent_arm.missing_packages(device, task.packages)
    return cell


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--task", required=True, choices=sorted(TASKS))
    ap.add_argument("--arms", default="before,after_mcp,after_replay")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--seed-base", type=int, default=0)
    ap.add_argument("--device", required=True)
    ap.add_argument("--agent-cmd", default="claude")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--max-turns", type=int, default=25)
    ap.add_argument("--timeout-s", type=float, default=900)
    ap.add_argument("--agent-host", default="")
    ap.add_argument("--mcp-host", default="")
    ap.add_argument("--token-cap", type=int, default=3_000_000)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out-dir", default="bench-out/native-ab")
    args = ap.parse_args(argv)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if any(a not in ARMS for a in arms):
        print(f"arms must be from {ARMS}", file=sys.stderr)
        return 2
    task = TASKS[args.task]
    skill = load_skill(str(REPO / task.skill))
    run_dir = REPO / args.out_dir / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    configs = {}
    for arm in ("before", "after_mcp"):
        skills_dir = Path(tempfile.mkdtemp(prefix=f"native-{arm}-skills-"))
        if arm == "after_mcp":
            agent_arm.install_local(skill.skill_dir, skills_dir)
        configs[arm] = agent_arm.mcp_config(
            Path(tempfile.mkdtemp(prefix="native-mcp-")) / "mcp.json",
            worktree=REPO,
            serial=args.device,
            skills_dir=skills_dir,
            hide=agent_arm.SKILL_TOOLS if arm == "before" else "",
            mcp_host=args.mcp_host,
        )
    blocker = None
    # Interleave arms per seed so drift in the device or the model service hits every arm alike.
    for seed in range(args.seed_base, args.seed_base + args.n):
        for arm in arms:
            cell = run_episode(
                task,
                skill,
                arm,
                seed,
                device=args.device,
                agent_cmd=args.agent_cmd,
                model=args.model,
                max_turns=args.max_turns,
                worktree=REPO,
                run_dir=run_dir,
                timeout_s=args.timeout_s,
                agent_host=args.agent_host,
                mcp_host=args.mcp_host,
                token_cap=args.token_cap,
                configs=configs,
            )
            (run_dir / f"{task.name}-{arm}-{seed}.cell.json").write_text(json.dumps(cell, indent=2, default=str) + "\n")
            print(
                f"{task.name} arm={arm} seed={seed} pass={cell.get('success')} tokens={cell.get('tokens')} "
                f"llm_calls={cell.get('llm_calls')} ui_actions={(cell.get('ui_actions') or {}).get('total')} "
                f"wall_ms={cell.get('wall_ms')} evidence={cell.get('score_evidence')} error={cell.get('error')}",
                flush=True,
            )
            if (
                cell.get("rate_limited")
                or cell.get("over_cap")
                or cell.get("packages_lost")
                or str(cell.get("error", "")).startswith("env")
            ):
                blocker = f"{arm} seed {seed}: {cell.get('error') or 'packages lost ' + str(cell.get('packages_lost'))}"
                break
        if blocker:
            print("BLOCKER " + blocker)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
