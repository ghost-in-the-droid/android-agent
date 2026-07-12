"""First-run onboarding wizard for the ``ghost`` CLI.

Detect available backends → let the user pick → capture a model + a device alias
+ a default mode → write ``~/.ghost/config.toml``. The caller then **resumes the
original command** so the user never re-types. Fully scriptable via
``ghost setup --backend ... --model ... --mode ... --device alias:serial`` and via
``GHOST_*`` env (which bypasses the wizard entirely).
"""

from __future__ import annotations

import sys

from gitd.ghostcli import config as gcfg
from gitd.ghostcli import detect
from gitd.ghostcli.resolve import VALID_MODES


def build_and_save(*, backend: str, model: str, mode: str, device_alias: str = "", device_serial: str = "") -> dict:
    """Assemble + persist config.toml (and a device alias); return the config dict."""
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}")
    cfg: dict = {"backend": {"name": backend}, "defaults": {"mode": mode}}
    if model:
        cfg["backend"]["model"] = model
    if device_alias and device_serial:
        gcfg.set_device_alias(device_alias, device_serial)
        cfg["defaults"]["device"] = device_alias
    gcfg.save_config(cfg)
    return cfg


def apply_noninteractive(*, backend: str, model: str = "", mode: str = "fast", device: str = "") -> dict:
    """`ghost setup --backend ... --device alias:serial` — no prompts."""
    alias, serial = "", ""
    if device:
        if ":" in device:
            alias, serial = device.split(":", 1)
        else:
            alias, serial = device, device  # bare serial: alias == serial
    return build_and_save(backend=backend, model=model, mode=mode, device_alias=alias, device_serial=serial)


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return ans or default


def run_interactive() -> dict | None:
    """Drive the menu-based wizard. Returns the written config, or None if skipped."""
    backends = detect.detect_backends()
    print("\nGhost setup — pick your LLM backend\n")
    for i, b in enumerate(backends, 1):
        mark = "" if b["available"] else "  (unavailable)"
        rec = "   ← recommended" if b["available"] and i == 1 else ""
        print(f"  [{i}] {b['label']:<22} {b['detail']}{mark}{rec}")
    skip_n = len(backends) + 1
    print(f"  [{skip_n}] Skip — configure later\n")

    default_choice = next((str(i) for i, b in enumerate(backends, 1) if b["available"]), str(skip_n))
    choice = _ask("Choose", default_choice)
    if not choice.isdigit() or not (1 <= int(choice) <= skip_n):
        print("Not a valid choice; skipping setup.")
        return None
    if int(choice) == skip_n:
        return None

    chosen = backends[int(choice) - 1]
    backend = chosen["key"]

    model = ""
    if chosen["models"]:  # ollama — pick a local model
        model = _ask(f"Which model? ({', '.join(chosen['models'][:6])})", chosen["models"][0])
    elif backend in ("claude-code", "anthropic", "openrouter", "openai"):
        model = _ask("Default model (blank = backend default)", "")

    device_alias, device_serial = "", ""
    devices = detect.detect_devices()
    if devices:
        device_serial = devices[0]
        device_alias = _ask(f"Nickname for device {device_serial}", "phone")

    mode = _ask(f"Default mode ({'/'.join(VALID_MODES)})", "fast")
    if mode not in VALID_MODES:
        mode = "fast"

    cfg = build_and_save(
        backend=backend, model=model, mode=mode, device_alias=device_alias, device_serial=device_serial
    )
    print(
        f"\n✓ Wrote {gcfg.config_path()}  (backend={backend}"
        + (f", model={model}" if model else "")
        + (f", device={device_alias}" if device_alias else "")
        + f", mode={mode})\n"
    )
    return cfg
