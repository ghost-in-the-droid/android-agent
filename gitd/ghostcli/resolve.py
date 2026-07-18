"""Resolve backend / model / mode / device for a ``ghost`` run.

Precedence everywhere: explicit flag > ``GHOST_*`` env > ``~/.ghost/config.toml``
> built-in default. Heavy modules (``agent_chat``, ``anthropic``) are imported
lazily so ``ghost --help`` and ``ghost devices`` stay fast.
"""

from __future__ import annotations

import os
import shutil

from gitd.ghostcli import config as gcfg

VALID_MODES = gcfg.VALID_MODES
_DEFAULT_PROVIDER = "claude-code"


class GhostConfigError(Exception):
    """Raised when there is no usable backend to run a task."""


def _providers() -> dict:
    from gitd.services.agent_chat import PROVIDERS

    return PROVIDERS


def valid_providers() -> tuple[str, ...]:
    return tuple(_providers().keys())


def resolve_backend(cli_backend: str | None = None, cli_model: str | None = None) -> tuple[str, str]:
    """Return ``(provider, model)`` by precedence. Does not validate usability."""
    cfg = gcfg.load_config().get("backend", {})
    provider = (
        cli_backend
        or os.environ.get("GHOST_BACKEND")
        or cfg.get("name")
        or _settings_default_provider()
        or _DEFAULT_PROVIDER
    )
    providers = _providers()
    model = cli_model or os.environ.get("GHOST_MODEL") or cfg.get("model")
    if not model:
        models = providers.get(provider, {}).get("models") or [""]
        model = models[0]
    return provider, model


def _settings_default_provider() -> str:
    try:
        from gitd.config import settings

        return settings.default_provider
    except Exception:
        return ""


def is_provider_usable(provider: str) -> bool:
    """Best-effort check that ``provider`` can actually run right now.

    Used to decide whether an unconfigured user can be sent straight into a run
    (they have ``claude`` on PATH, or an API key) vs. shown the setup hint.
    """
    if provider == "claude-code":
        if not shutil.which("claude"):
            return False
        try:
            from gitd.cli import _claude_auth_state

            return _claude_auth_state() == "logged_in"
        except Exception:
            return True  # claude present; assume usable if we can't probe auth
    try:
        from gitd.config import settings

        if provider == "anthropic":
            return bool(settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
        if provider == "openrouter":
            return bool(settings.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY"))
        if provider in ("openai",):
            return bool(settings.openai_api_key or os.environ.get("OPENAI_API_KEY"))
    except Exception:
        pass
    # ollama / vllm / on-device: assume the endpoint is up (the run surfaces a
    # clear connection error otherwise).
    return provider in ("ollama", "vllm", "on-device")


def unconfigured() -> bool:
    """True when the user has no config file and no GHOST_* backend env set."""
    return not gcfg.config_exists() and not os.environ.get("GHOST_BACKEND")


def resolve_backend_or_error(cli_backend: str | None, cli_model: str | None) -> tuple[str, str]:
    """Resolve, but raise :class:`GhostConfigError` when nothing usable exists.

    An explicit ``--backend`` / ``GHOST_BACKEND`` is trusted (the run will surface
    its own error if wrong). Otherwise, if the user is unconfigured and the default
    provider is not usable, send them to ``ghost setup``.
    """
    provider, model = resolve_backend(cli_backend, cli_model)
    explicit = bool(cli_backend or os.environ.get("GHOST_BACKEND"))
    if provider not in _providers():
        raise GhostConfigError(f"Unknown backend '{provider}'. Valid: {', '.join(valid_providers())}.")
    if not explicit and unconfigured() and not is_provider_usable(provider):
        raise GhostConfigError(
            "No backend configured. Run 'ghost setup' to configure, or pass "
            "--backend <name> (e.g. --backend ollama), or set GHOST_BACKEND."
        )
    return provider, model


def resolve_mode(cli_mode: str | None) -> str:
    mode = cli_mode or os.environ.get("GHOST_MODE") or gcfg.load_config().get("defaults", {}).get("mode") or "fast"
    if mode not in VALID_MODES:
        raise GhostConfigError(f"Invalid --mode '{mode}'. Choose one of: {', '.join(VALID_MODES)}.")
    return mode
