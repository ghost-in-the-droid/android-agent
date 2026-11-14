"""Mini eval: does Codex call find_skill before its first input action, with vs without the base ghost skill.

Run on the host that has the emulator. Env: ADB_SERVER_SOCKET, ANDROID_SERIAL, GHOST_EVAL_PY (python with gitd installed).
Usage: skill_first_eval.py OUT_DIR [--only N] [--arms with,without]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNIPPET = (ROOT / "skillhub/_guides/ghost-base/AGENTS.snippet.md").read_text()
INPUT_TOOLS = {"tap", "tap_element", "long_press", "swipe", "type_text", "type_unicode", "press_key", "paste_text"}
PROMPTS = [
    "Calculate 2345 times 7",
    "Set an alarm for 6:45 called Run",
    "Start a 3 minute timer for eggs",
    "Add Grace Hopper to my contacts with number +1 555 010 0000",
    "Find Grace in my contacts",
    "Make a note called Ideas{n} with milk and eggs",
    "Add 'call dentist' to my to-do list in Markor",
    "Add a task to buy stamps",
    "What alarms do I have set?",
    "Convert 100 Fahrenheit to Celsius",
]
MODEL, EFFORT, TIMEOUT_S = "gpt-6-luna", "low", 300


def tool_calls(jsonl: str) -> list[str]:
    names = []
    for line in jsonl.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        item = e.get("item") or {}
        if e.get("type") == "item.started" and item.get("type") == "mcp_tool_call":
            names.append(item.get("tool"))
    return names


def score(names: list[str]) -> dict:
    first_input = next((i for i, n in enumerate(names) if n in INPUT_TOOLS), None)
    first_find = names.index("find_skill") if "find_skill" in names else None
    return {
        "calls": names,
        "find_skill_called": first_find is not None,
        "first_input_idx": first_input,
        "find_before_first_tap": first_find is not None and (first_input is None or first_find < first_input),
        "run_skill_called": "run_skill" in names,
    }


def run_one(arm: str, prompt: str, out: Path) -> dict:
    py = os.environ["GHOST_EVAL_PY"]
    cwd = Path(tempfile.mkdtemp(prefix="ghost-eval-"))
    (cwd / "AGENTS.md").write_text(SNIPPET if arm == "with" else "")
    env = dict(os.environ)
    env.pop("CCT_AGENT_NAME", None)
    mcp_env = {k: os.environ[k] for k in ("ADB_SERVER_SOCKET", "ANDROID_SERIAL") if k in os.environ}
    cmd = [
        "codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "-C", str(cwd),
        "-m", MODEL, "-c", f'model_reasoning_effort="{EFFORT}"', "-c", 'approval_policy="never"',
        "-c", 'sandbox_mode="danger-full-access"',
        "-c", f'mcp_servers.ghost.command="{py}"', "-c", 'mcp_servers.ghost.args=["-m","gitd.mcp_server"]',
        "-c", "mcp_servers.ghost.env={" + ",".join(f'{k}="{v}"' for k, v in mcp_env.items()) + "}", "-c", f'mcp_servers.ghost.cwd="{ROOT}"',
        "-c", "mcp_servers.ghost.tool_timeout_sec=90", "-c", "features.shell_tool=false",
        prompt + " (on my phone)",
    ]
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, env=env, stdin=subprocess.DEVNULL)
        stdout, rc = r.stdout, r.returncode
    except subprocess.TimeoutExpired as ex:
        stdout, rc = (ex.stdout or b"").decode(errors="replace") if isinstance(ex.stdout, bytes) else (ex.stdout or ""), "timeout"
    out.write_text(stdout)
    out.with_suffix(".err").write_text(getattr(r, "stderr", "") if rc != "timeout" else "")
    subprocess.run(["adb", "-s", os.environ["ANDROID_SERIAL"], "shell", "input", "keyevent", "KEYCODE_HOME"], check=False)
    return {"arm": arm, "prompt": prompt, "rc": rc, "elapsed_s": round(time.monotonic() - t0), **score(tool_calls(stdout))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--only", type=int)
    ap.add_argument("--arms", default="without,with")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, p in enumerate(PROMPTS):
        if a.only is not None and i != a.only:
            continue
        for arm in a.arms.split(","):
            row = run_one(arm, p.format(n=f"{arm[0]}{i}"), out / f"{i:02d}-{arm}.jsonl")
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "calls"}), flush=True)
            (out / "results.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    sys.exit(main())
