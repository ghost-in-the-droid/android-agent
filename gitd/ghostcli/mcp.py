"""``ghost mcp install --client <name>`` — register Ghost's MCP server with a client.

All clients register the same stdio server (``android-agent-mcp``, name
``android-agent``), so the tool surface is identical everywhere. JSON clients are
merged (never clobbered); claude-code prefers its own ``claude mcp add`` CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

SERVER_NAME = "android-agent"
SERVER_CMD = "android-agent-mcp"  # console-script from pyproject; == `python3 -m gitd.mcp_server`

SUPPORTED_CLIENTS = ("claude-code", "cursor", "codex", "opencode")


class McpInstallError(Exception):
    pass


def _home() -> Path:
    override = os.environ.get("GHOST_HOME_OVERRIDE")  # tests point this at a tmp home
    return Path(override) if override else Path.home()


def _merge_json(path: Path, mutate) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError as e:
            raise McpInstallError(f"{path} is not valid JSON ({e}); fix or remove it first.") from e
    mutate(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _install_cursor() -> str:
    path = _home() / ".cursor" / "mcp.json"

    def mutate(data: dict) -> None:
        data.setdefault("mcpServers", {})[SERVER_NAME] = {"command": SERVER_CMD}

    _merge_json(path, mutate)
    return f"Registered '{SERVER_NAME}' in {path} (Cursor)."


def _install_opencode() -> str:
    path = _home() / ".config" / "opencode" / "opencode.json"

    def mutate(data: dict) -> None:
        data.setdefault("$schema", "https://opencode.ai/config.json")
        data.setdefault("mcp", {})[SERVER_NAME] = {
            "type": "local",
            "command": [SERVER_CMD],
            "enabled": True,
        }

    _merge_json(path, mutate)
    return f"Registered '{SERVER_NAME}' in {path} (OpenCode)."


def _install_codex() -> str:
    # Codex CLI reads ~/.codex/config.toml with a [mcp_servers.<name>] table.
    path = _home() / ".codex" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if f"[mcp_servers.{SERVER_NAME}]" in existing:
        return f"'{SERVER_NAME}' already present in {path} (Codex) — left unchanged."
    block = f'\n[mcp_servers.{SERVER_NAME}]\ncommand = "{SERVER_CMD}"\n'
    path.write_text(existing.rstrip("\n") + "\n" + block if existing else block.lstrip("\n"), encoding="utf-8")
    return f"Registered '{SERVER_NAME}' in {path} (Codex)."


def _install_claude_code() -> str:
    # Prefer the official CLI; fall back to a project-local .mcp.json.
    if shutil.which("claude"):
        try:
            subprocess.run(
                ["claude", "mcp", "add", SERVER_NAME, "--", SERVER_CMD],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return f"Registered '{SERVER_NAME}' with Claude Code (claude mcp add)."
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass  # fall through to file
    path = Path.cwd() / ".mcp.json"

    def mutate(data: dict) -> None:
        data.setdefault("mcpServers", {})[SERVER_NAME] = {"command": SERVER_CMD}

    _merge_json(path, mutate)
    return f"'claude' CLI unavailable — wrote project-local {path} instead (Claude Code / any .mcp.json reader)."


_INSTALLERS = {
    "claude-code": _install_claude_code,
    "cursor": _install_cursor,
    "codex": _install_codex,
    "opencode": _install_opencode,
}


def install(client: str) -> str:
    if client not in _INSTALLERS:
        raise McpInstallError(f"Unknown client '{client}'. Supported: {', '.join(SUPPORTED_CLIENTS)}.")
    return _INSTALLERS[client]()
