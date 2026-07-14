"""Device selection for the ``ghost`` CLI.

``--device`` (aka ``-d`` / ``--udid``) accepts a **human alias** (resolved via
``~/.ghost/devices.toml``) or a **raw serial / ref**. With no flag: auto-pick the
sole connected device (with a warning), or error listing candidates when several
are connected — never silently pick one of many.
"""

from __future__ import annotations

from gitd.ghostcli import config as gcfg


class DeviceError(Exception):
    """No device could be selected (none / ambiguous / unknown alias)."""


def _connected_refs() -> list[str]:
    try:
        from gitd.bots.common.device import list_connected_device_refs

        return list(list_connected_device_refs())
    except Exception:
        return []


def resolve_device(cli_device: str | None) -> str:
    """Resolve a device ref to act on. Raises :class:`DeviceError` on failure.

    Order: explicit ``--device`` (alias→serial, else raw) → configured default
    alias → sole connected device (auto-pick + warning).
    """
    aliases = gcfg.load_devices()

    requested = cli_device or gcfg.load_config().get("defaults", {}).get("device")
    if requested:
        # alias wins; otherwise it is a raw serial/ref used verbatim
        return aliases.get(requested, requested)

    refs = _connected_refs()
    if len(refs) == 1:
        # caller prints the warning (keeps this layer print-free / testable)
        return refs[0]
    if not refs:
        raise DeviceError("No device connected. Connect one, or configure an alias with 'ghost setup'.")
    listing = ", ".join(refs)
    raise DeviceError(
        f"Multiple devices connected ({listing}). Pick one with --device <alias-or-serial> "
        "(set aliases in ~/.ghost/devices.toml or via 'ghost setup')."
    )


def auto_picked(cli_device: str | None) -> bool:
    """True when :func:`resolve_device` would auto-pick a lone device (for the warning)."""
    if cli_device or gcfg.load_config().get("defaults", {}).get("device"):
        return False
    return len(_connected_refs()) == 1


def _android_model(serial: str) -> str:
    try:
        from gitd.bots.common.adb import Device

        return Device(serial).adb("shell", "getprop", "ro.product.model", timeout=3).strip().replace("_", " ")
    except Exception:
        return ""


def list_for_display() -> list[dict]:
    """Rows for ``ghost devices``: ``{ref, alias, model, platform}``."""
    aliases = gcfg.load_devices()
    serial_to_alias = {v: k for k, v in aliases.items()}
    rows: list[dict] = []

    ios_details: dict[str, dict] = {}
    try:
        from gitd.bots.common.device import list_configured_ios_devices

        ios_details = {d["serial"]: d for d in list_configured_ios_devices(deep_probe=False)}
    except Exception:
        pass

    for ref in _connected_refs():
        is_ios = ref in ios_details
        model = ios_details[ref].get("model", "") if is_ios else _android_model(ref)
        rows.append(
            {
                "ref": ref,
                "alias": serial_to_alias.get(ref, ""),
                "model": model or ("iOS device" if is_ios else ""),
                "platform": "ios" if is_ios else "android",
            }
        )
    return rows
