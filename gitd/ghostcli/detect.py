"""Backend / environment detection for the first-run wizard and ``ghost doctor``.

Print-free probes — each returns data so callers (wizard, tests) render it.
"""

from __future__ import annotations

import os
import shutil


def _claude_available() -> tuple[bool, str]:
    path = shutil.which("claude")
    if not path:
        return False, "not installed"
    try:
        from gitd.cli import _claude_auth_state

        state = _claude_auth_state()
    except Exception:
        state = "unknown"
    if state == "logged_in":
        return True, path
    if state == "logged_out":
        return False, f"{path} (logged out — run 'ghost login')"
    return bool(path), path


def _ollama_models() -> list[str]:
    try:
        import requests

        from gitd.config import settings

        base = os.environ.get("OLLAMA_BASE_URL") or settings.ollama_base_url
        r = requests.get(f"{base.rstrip('/')}/api/tags", timeout=2)
        if r.ok:
            return [m["name"] for m in r.json().get("models", []) if m.get("name")]
    except Exception:
        pass
    return []


def _api_key(*names: str) -> bool:
    for n in names:
        if os.environ.get(n):
            return True
    try:
        from gitd.config import settings

        field = {
            "ANTHROPIC_API_KEY": "anthropic_api_key",
            "OPENROUTER_API_KEY": "openrouter_api_key",
            "OPENAI_API_KEY": "openai_api_key",
        }
        for n in names:
            if n in field and getattr(settings, field[n], ""):
                return True
    except Exception:
        pass
    return False


def detect_backends() -> list[dict]:
    """Detected LLM backends, in recommended order.

    Each: ``{key, label, available, detail, models}``. ``key`` is a valid
    provider name (see ``PROVIDERS``) except ``opencode`` (an MCP-client only).
    """
    claude_ok, claude_detail = _claude_available()
    ollama_models = _ollama_models()
    return [
        {"key": "claude-code", "label": "Claude Code", "available": claude_ok, "detail": claude_detail, "models": []},
        {
            "key": "ollama",
            "label": "Ollama",
            "available": bool(ollama_models),
            "detail": (f"{len(ollama_models)} local models" if ollama_models else "not detected"),
            "models": ollama_models,
        },
        {
            "key": "openrouter",
            "label": "OpenRouter",
            "available": _api_key("OPENROUTER_API_KEY"),
            "detail": ("$OPENROUTER_API_KEY set" if _api_key("OPENROUTER_API_KEY") else "set $OPENROUTER_API_KEY"),
            "models": [],
        },
        {
            "key": "anthropic",
            "label": "Anthropic API",
            "available": _api_key("ANTHROPIC_API_KEY"),
            "detail": ("$ANTHROPIC_API_KEY set" if _api_key("ANTHROPIC_API_KEY") else "set $ANTHROPIC_API_KEY"),
            "models": [],
        },
        {
            "key": "codex",
            "label": "Codex CLI",
            "available": bool(shutil.which("codex")),
            "detail": (shutil.which("codex") or "not detected"),
            "models": [],
        },
        {
            "key": "opencode",
            "label": "OpenCode (MCP client)",
            "available": bool(shutil.which("opencode")),
            "detail": (shutil.which("opencode") or "not detected"),
            "models": [],
        },
    ]


def detect_devices() -> list[str]:
    try:
        from gitd.bots.common.device import list_connected_device_refs

        return list(list_connected_device_refs())
    except Exception:
        return []
