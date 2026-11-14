#!/usr/bin/env python3
"""Record a real Claude Code TUI session driving a task, cleanly.

Architecture (avoids the nested-PTY width corruption): pexpect spawns
`asciinema rec --window-size CxR` which runs the real `claude` TUI *directly*
(prompt passed as a positional arg so it auto-runs). Because claude renders into
asciinema's single PTY at the forced size, there's no width mismatch. pexpect
watches the output and, once the agent goes idle, sends the exit keystrokes to
claude so asciinema finalizes the cast.

TMUX is stripped from the child env (else claude prints tmux hints), and TERM is
forced to xterm-256color for clean rendering.

Usage:
    python claude_tui_driver.py --prompt '<task>' --mcp-config <cfg> \
        --cast out.cast [--cols 100] [--rows 30] [--env KEY=VAL ...]
"""
import json
from pathlib import Path
import uuid

import argparse
import os
import shlex
import sys
import time

import pexpect


def session_tokens(path: Path) -> int:
    """Count final usage per assistant message, deduplicating streaming updates."""
    messages = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return 0
    for line in lines:
        try:
            entry = json.loads(line)
            message = entry.get('message', {})
            if entry.get('type') != 'assistant' or not message.get('id'):
                continue
            usage = message.get('usage', {})
            messages[message['id']] = sum(int(usage.get(key, 0) or 0) for key in (
                'input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
        except (ValueError, TypeError, AttributeError):
            continue  # writer may still be appending the current line
    return sum(messages.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--mcp-config", required=True)
    ap.add_argument("--cast", required=True)
    ap.add_argument("--cols", type=int, default=100)
    ap.add_argument("--rows", type=int, default=30)
    ap.add_argument("--claude", default="claude")
    ap.add_argument("--notes-only", action="store_true", help="Use only live Ghost MCP tools, without built-in shell tools")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--max-tokens", type=int, default=12000)

    ap.add_argument("--idle-done", type=float, default=8.0,
                    help="seconds of no output (after work began) = finished")
    ap.add_argument("--min-run", type=float, default=14.0)
    ap.add_argument("--max-run", type=float, default=240.0)
    ap.add_argument("--env", action="append", default=[],
                    help="KEY=VAL injected into the claude/MCP env (repeatable)")
    args = ap.parse_args()

    if not 1 <= args.max_tokens <= 100000:
        ap.error('--max-tokens must be 1..100000')
    session_id = str(uuid.uuid4())
    config_root = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude')).expanduser().resolve()
    # Claude writes usage after a model response; the output cap bounds the
    # response in flight, while the transcript cap stops subsequent turns.
    # Cached input counts too. A single response may cross the session threshold.
    project_root = config_root / 'projects'
    # Env for the inner claude process: no TMUX, clean TERM, iOS gate on.
    inner_env = {
        "TERM": "xterm-256color",
        "GITD_ENABLE_IOS": "1",
        "COLUMNS": str(args.cols),
        "LINES": str(args.rows),
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(min(args.max_tokens, 4096)),
    }
    if 'CLAUDE_CONFIG_DIR' in os.environ:
        inner_env['CLAUDE_CONFIG_DIR'] = str(config_root)
    for kv in args.env:
        k, _, v = kv.partition("=")
        inner_env[k] = v
    # Never let the recording session inherit the operator's own Claude Code session
    # (CLAUDECODE, CLAUDE_CODE_* incl. its messaging token, CLAUDE_EFFORT ... make the TUI print "inherited ..." banners and change
    # behaviour). Only variables passed with --env reach the recorded claude.
    inherited = sorted(k for k in os.environ if k.startswith("CLAUDE"))
    env_prefix = "env -u TMUX " + "".join(f"-u {k} " for k in inherited) + " ".join(
        f"{k}={shlex.quote(v)}" for k, v in inner_env.items()
    )

    tool_options = ("--tools '' --allowedTools 'mcp__android-agent__*' " if args.notes_only
                    else "--dangerously-skip-permissions ")
    inner = (
        f"{env_prefix} {shlex.quote(args.claude)} --mcp-config {shlex.quote(args.mcp_config)} "
        f"--strict-mcp-config {tool_options}--model {shlex.quote(args.model)} --session-id {session_id} "
        f"{shlex.quote(args.prompt)}"
    )
    # asciinema 3.x takes --window-size CxR; 2.x (pip, distro packages) takes --cols/--rows.
    import subprocess
    version = subprocess.run(["asciinema", "--version"], capture_output=True, text=True).stdout
    size_flag = (f"--window-size {args.cols}x{args.rows}" if version.split()[-1:] and
                 version.split()[-1].split(".")[0].isdigit() and int(version.split()[-1].split(".")[0]) >= 3
                 else f"--cols {args.cols} --rows {args.rows}")
    rec = (
        f"asciinema rec --overwrite {size_flag} "
        f"{shlex.quote(args.cast)} -c {shlex.quote(inner)}"
    )

    spawn_env = {k: v for k, v in os.environ.items() if k not in inherited}
    spawn_env.pop("TMUX", None)
    spawn_env["TERM"] = "xterm-256color"
    child = pexpect.spawn(
        "/bin/bash", ["-lc", rec], env=spawn_env, encoding="utf-8",
        dimensions=(args.rows, args.cols), timeout=args.max_run,
    )
    child.logfile_read = sys.stdout

    start = time.time()
    last_output = time.time()
    saw_work = False
    capped = False
    while time.time() - start < args.max_run:
        try:
            chunk = child.read_nonblocking(size=4096, timeout=1.0)
            if chunk:
                last_output = time.time()
                if len(chunk.strip()) > 2:
                    saw_work = True
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
        transcripts = list(project_root.glob(f'*/{session_id}.jsonl'))
        if sum(session_tokens(path) for path in transcripts) >= args.max_tokens:
            capped = True
            break
        idle = time.time() - last_output
        if saw_work and idle >= args.idle_done and time.time() - start > args.min_run:
            break

    # Exit the claude TUI so asciinema finalizes the cast.
    time.sleep(1.2)
    for keys in ("\x1b", "\x03", "\x03"):   # esc, then Ctrl-C twice
        try:
            child.send(keys)
            time.sleep(0.4)
        except Exception:
            break
    try:
        child.expect(pexpect.EOF, timeout=10)
    except Exception:
        child.close(force=True)
    if capped:
        print('Claude session reached its token cap; review the captured result.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
