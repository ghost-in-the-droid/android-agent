"""The ``ghost`` CLI entry point — task-first dispatch.

Grammar: a **bare positional** is an agent task (``ghost "check reddit" --device
asus``); a **reserved first token** is a subcommand (``ghost devices``, ``ghost
skill run …``). Reserved wins, so quote a task whose first word is a reserved verb
(``ghost "record my day"``). ``--`` forces prompt mode.

Kept thin: legacy subcommands (``up``/``doctor``/``login``/``skill``) delegate to
the existing ``gitd.cli`` handlers; the prompt path delegates to
``agent_chat.chat_turn`` via :mod:`gitd.ghostcli.run`.
"""

from __future__ import annotations

import argparse
import sys

from gitd.ghostcli import config as gcfg
from gitd.ghostcli import devices as gdev
from gitd.ghostcli import mcp as gmcp
from gitd.ghostcli import resolve as gres
from gitd.ghostcli import run as grun
from gitd.ghostcli import wizard as gwiz

# Subcommands whose first token routes away from the prompt path.
_LEGACY = ("up", "doctor", "login", "skill")  # handled by gitd.cli
_LOCAL = ("devices", "setup", "configure", "config", "mcp")  # handled here
RESERVED = (*_LEGACY, *_LOCAL, "help")


def _split_leading(argv: list[str]) -> list[str]:
    """Tokens before the first ``-``-prefixed flag."""
    out: list[str] = []
    for tok in argv:
        if tok.startswith("-"):
            break
        out.append(tok)
    return out


# ── local subcommand handlers ────────────────────────────────────────────────


def _cmd_devices(_rest: list[str]) -> int:
    rows = gdev.list_for_display()
    if not rows:
        print("No devices connected.")
        return 0
    aliases = gcfg.load_devices()
    width = max((len(r["ref"]) for r in rows), default=0)
    for r in rows:
        alias = f"  ({r['alias']})" if r["alias"] else ""
        model = f"  {r['model']}" if r["model"] else ""
        print(f"{r['ref']:<{width}}{model}{alias}  [{r['platform']}]")
    if aliases:
        print(f"\nAliases in {gcfg.devices_path()}: " + ", ".join(f"{k}→{v}" for k, v in aliases.items()))
    return 0


def _cmd_setup(rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ghost setup", add_help=True)
    p.add_argument("--backend")
    p.add_argument("--model", default="")
    p.add_argument("--mode", default="fast")
    p.add_argument("--device", default="")
    args = p.parse_args(rest)
    if args.backend:  # non-interactive
        cfg = gwiz.apply_noninteractive(backend=args.backend, model=args.model, mode=args.mode, device=args.device)
        print(f"✓ Wrote {gcfg.config_path()} (backend={cfg['backend']['name']}, mode={cfg['defaults']['mode']}).")
        return 0
    if not gwiz.is_interactive():
        print("ghost setup needs a terminal, or pass --backend (see 'ghost setup --help').", file=sys.stderr)
        return 2
    return 0 if gwiz.run_interactive() is not None else 0


def _cmd_config(rest: list[str]) -> int:
    if not rest:
        print("usage: ghost config <get <key> | set <key>=<val> | path>", file=sys.stderr)
        return 2
    sub, *tail = rest
    if sub == "path":
        print(gcfg.config_path())
        return 0
    if sub == "get":
        if not tail:
            print("usage: ghost config get <key>", file=sys.stderr)
            return 2
        try:
            val = gcfg.get_value(tail[0])
        except KeyError:
            print(f"Unknown key '{tail[0]}'. Known: {', '.join(gcfg.known_keys())}", file=sys.stderr)
            return 2
        print("" if val is None else val)
        return 0
    if sub == "set":
        if not tail or "=" not in tail[0]:
            print("usage: ghost config set <key>=<value>", file=sys.stderr)
            return 2
        key, value = tail[0].split("=", 1)
        try:
            gcfg.set_value(key, value)
        except KeyError:
            print(f"Unknown key '{key}'. Known: {', '.join(gcfg.known_keys())}", file=sys.stderr)
            return 2
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"{key} = {value}")
        return 0
    print(f"Unknown config subcommand '{sub}'.", file=sys.stderr)
    return 2


def _cmd_mcp(rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ghost mcp install")
    p.add_argument("action", choices=["install"])
    p.add_argument("--client", required=True, choices=list(gmcp.SUPPORTED_CLIENTS))
    args = p.parse_args(rest)
    try:
        print(gmcp.install(args.client))
    except gmcp.McpInstallError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def _delegate_legacy(argv: list[str]) -> int:
    from gitd import cli as legacy

    return int(legacy.main(argv) or 0)


# ── prompt path ──────────────────────────────────────────────────────────────


def _run_prompt(prompt: str, flag_argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ghost", add_help=False)
    p.add_argument("--device", "-d", "--udid", dest="device", default=None)
    p.add_argument("--mode", default=None)
    p.add_argument("--backend", default=None)
    p.add_argument("--model", default=None)
    try:
        args, _unknown = p.parse_known_args(flag_argv)
    except SystemExit:
        return 2

    # First run with no config + no env + no explicit backend → wizard, then resume.
    if gres.unconfigured() and not args.backend and gwiz.is_interactive():
        gwiz.run_interactive()

    try:
        provider, model = gres.resolve_backend_or_error(args.backend, args.model)
        mode = gres.resolve_mode(args.mode)
        device = gdev.resolve_device(args.device)
        picked = gdev.auto_picked(args.device)
    except (gres.GhostConfigError, gdev.DeviceError) as e:
        print(str(e), file=sys.stderr)
        return 2
    return grun.run_task(prompt, device, provider, model, mode, auto_picked=picked)


_HELP = """ghost — give any AI agent an Android/iOS body.

  ghost "<task>" [--device D] [--mode fast|vision|reason] [--backend B]
      Run an agent task on a device. Quote the task.

  ghost devices                 List connected devices + aliases
  ghost setup                   First-run wizard (or --backend for non-interactive)
  ghost config get|set|path     Read/write ~/.ghost/config.toml
  ghost mcp install --client claude-code|cursor|codex|opencode
  ghost up | doctor | login | skill …    (existing commands)
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0

    # `--` forces prompt mode for a task that starts with a reserved word.
    if argv[0] == "--":
        rest = argv[1:]
        leading = _split_leading(rest)
        return _run_prompt(" ".join(leading), rest[len(leading) :])

    first = argv[0]
    if first in _LEGACY:
        return _delegate_legacy(argv)
    if first == "devices":
        return _cmd_devices(argv[1:])
    if first in ("setup", "configure"):
        return _cmd_setup(argv[1:])
    if first == "config":
        return _cmd_config(argv[1:])
    if first == "mcp":
        return _cmd_mcp(argv[1:])

    # Bare positional → agent task.
    leading = _split_leading(argv)
    if not leading:
        print(_HELP)
        return 0
    return _run_prompt(" ".join(leading), argv[len(leading) :])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
