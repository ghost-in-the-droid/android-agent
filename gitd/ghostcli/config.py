"""``~/.ghost/`` config + device-alias store for the ``ghost`` CLI.

Thin layer over two TOML files, with a strict precedence chain so a flag always
beats an env var beats the config file beats the built-in default:

    explicit flag  >  GHOST_* env  >  ~/.ghost/config.toml  >  detected default

Files (dir overridable with ``GHOST_CONFIG_DIR`` for tests / non-default homes):

    ~/.ghost/config.toml   [backend] name/model · [defaults] mode/device · [dashboard] port
    ~/.ghost/devices.toml  [devices] <alias> = "<serial-or-ref>"

Read uses stdlib ``tomllib`` (3.11+); we hand-write TOML on save (the schema is
flat, so a real TOML writer isn't worth a dependency).
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover - py3.10 fallback
    import tomli as tomllib  # type: ignore

VALID_MODES = ("fast", "vision", "reason")


def ghost_dir() -> Path:
    """The ``~/.ghost`` directory (overridable via ``GHOST_CONFIG_DIR``)."""
    override = os.environ.get("GHOST_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".ghost"


def config_path() -> Path:
    return ghost_dir() / "config.toml"


def devices_path() -> Path:
    return ghost_dir() / "devices.toml"


def skills_dir() -> Path:
    return ghost_dir() / "skills"


def logs_dir() -> Path:
    return ghost_dir() / "logs"


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (FileNotFoundError, ValueError):
        return {}


def load_config() -> dict:
    return _read_toml(config_path())


def load_devices() -> dict[str, str]:
    """Return the ``{alias: serial}`` map from devices.toml.

    Accepts both the canonical ``[devices]`` section and a bare ``alias = "serial"``
    file with no header (a common hand-edit) — the latter parses to top-level keys,
    which would otherwise be silently ignored.
    """
    data = _read_toml(devices_path())
    section = data.get("devices")
    if not isinstance(section, dict):
        # No [devices] header: treat top-level string entries as aliases.
        section = {k: v for k, v in data.items() if isinstance(v, str)}
    return {str(k): str(v) for k, v in section.items()}


def config_exists() -> bool:
    return config_path().exists()


# ── writing ──────────────────────────────────────────────────────────────────


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _dump_toml(data: dict) -> str:
    """Serialize a shallow ``{section: {key: scalar}}`` dict to TOML text."""
    lines: list[str] = []
    for section, body in data.items():
        if not isinstance(body, dict):
            continue
        lines.append(f"[{section}]")
        for key, value in body.items():
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                lines.append(f"{key} = {'true' if value else 'false'}")
            elif isinstance(value, (int, float)):
                lines.append(f"{key} = {value}")
            else:
                lines.append(f'{key} = "{_toml_escape(str(value))}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_config(data: dict) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_toml(data), encoding="utf-8")
    return path


def save_devices(devices: dict[str, str]) -> Path:
    path = devices_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_toml({"devices": devices}), encoding="utf-8")
    return path


def set_device_alias(alias: str, serial: str) -> None:
    devices = load_devices()
    devices[alias] = serial
    save_devices(devices)


# ── flat get/set for `ghost config get/set <dotted.key>` ─────────────────────

# Whitelisted dotted keys → (section, key, coercer). Keeps `config set` from
# writing arbitrary junk into the file.
_KEYS: dict[str, tuple[str, str, type]] = {
    "backend.name": ("backend", "name", str),
    "backend.model": ("backend", "model", str),
    "defaults.mode": ("defaults", "mode", str),
    "defaults.device": ("defaults", "device", str),
    "dashboard.port": ("dashboard", "port", int),
}


def get_value(dotted: str):
    if dotted not in _KEYS:
        raise KeyError(dotted)
    section, key, _ = _KEYS[dotted]
    return load_config().get(section, {}).get(key)


def set_value(dotted: str, raw: str) -> None:
    if dotted not in _KEYS:
        raise KeyError(dotted)
    section, key, coerce = _KEYS[dotted]
    value = coerce(raw)
    if dotted == "defaults.mode" and value not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}")
    cfg = load_config()
    cfg.setdefault(section, {})[key] = value
    save_config(cfg)


def known_keys() -> tuple[str, ...]:
    return tuple(_KEYS)
