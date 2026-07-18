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
import argparse
import os
import shlex
import sys
import time

import pexpect


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--mcp-config", required=True)
    ap.add_argument("--cast", required=True)
    ap.add_argument("--cols", type=int, default=100)
    ap.add_argument("--rows", type=int, default=30)
    ap.add_argument("--claude", default="claude")
    ap.add_argument("--idle-done", type=float, default=8.0,
                    help="seconds of no output (after work began) = finished")
    ap.add_argument("--min-run", type=float, default=14.0)
    ap.add_argument("--max-run", type=float, default=240.0)
    ap.add_argument("--env", action="append", default=[],
                    help="KEY=VAL injected into the claude/MCP env (repeatable)")
    args = ap.parse_args()

    # Env for the inner claude process: no TMUX, clean TERM, iOS gate on.
    inner_env = {
        "TERM": "xterm-256color",
        "GITD_ENABLE_IOS": "1",
        "COLUMNS": str(args.cols),
        "LINES": str(args.rows),
    }
    for kv in args.env:
        k, _, v = kv.partition("=")
        inner_env[k] = v
    env_prefix = "env -u TMUX " + " ".join(
        f"{k}={shlex.quote(v)}" for k, v in inner_env.items()
    )

    inner = (
        f"{env_prefix} {args.claude} --mcp-config {shlex.quote(args.mcp_config)} "
        f"--strict-mcp-config --dangerously-skip-permissions "
        f"{shlex.quote(args.prompt)}"
    )
    rec = (
        f"asciinema rec --overwrite --window-size {args.cols}x{args.rows} "
        f"{shlex.quote(args.cast)} -c {shlex.quote(inner)}"
    )

    spawn_env = dict(os.environ)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
