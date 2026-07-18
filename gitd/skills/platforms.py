"""Platform compatibility helpers for automation skills."""
from __future__ import annotations

from typing import Any

from gitd.bots.common.device import is_ios_ref

VALID_PLATFORMS = ("android", "ios")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_platforms(value: Any) -> list[str]:
    """Normalize a metadata platforms value to ordered supported platform names."""
    if value is None or value == "":
        return []
    raw_values = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in raw_values:
        platform = _clean(item).lower()
        if platform in VALID_PLATFORMS and platform not in result:
            result.append(platform)
    return result


def platform_for_device_ref(device: str | None) -> str:
    return "ios" if device and is_ios_ref(device) else "android"


def skill_android_package(metadata: dict[str, Any]) -> str:
    return _clean(metadata.get("android_package") or metadata.get("app_package"))


def skill_ios_bundle_id(metadata: dict[str, Any]) -> str:
    return _clean(metadata.get("ios_bundle_id"))


def skill_platforms(metadata: dict[str, Any] | None) -> list[str]:
    """Return supported platforms for a skill.

    Legacy skills predate explicit platform metadata. Preserve their behavior by
    treating skills without iOS metadata as Android skills.
    """
    metadata = metadata or {}
    explicit = normalize_platforms(metadata.get("platforms"))
    if explicit:
        return explicit

    inferred: list[str] = []
    if skill_android_package(metadata):
        inferred.append("android")
    if skill_ios_bundle_id(metadata):
        inferred.append("ios")
    return inferred or ["android"]


def skill_supports_platform(metadata: dict[str, Any] | None, platform: str) -> bool:
    return platform.lower() in skill_platforms(metadata)


def skill_supports_device(metadata: dict[str, Any] | None, device: str | None) -> bool:
    return skill_supports_platform(metadata, platform_for_device_ref(device))


def skill_target_for_device(metadata: dict[str, Any] | None, device: str | None) -> str:
    metadata = metadata or {}
    if platform_for_device_ref(device) == "ios":
        return skill_ios_bundle_id(metadata)
    return skill_android_package(metadata)


def skill_platform_summary(metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata or {}
    platforms = skill_platforms(metadata)
    return {
        "platforms": platforms,
        "supports_android": "android" in platforms,
        "supports_ios": "ios" in platforms,
        "app_package": _clean(metadata.get("app_package")),
        "android_package": skill_android_package(metadata),
        "ios_bundle_id": skill_ios_bundle_id(metadata),
        "platform_limitations": metadata.get("platform_limitations") or {},
    }


def skill_platform_error(skill_name: str, metadata: dict[str, Any] | None, device: str | None) -> dict[str, Any]:
    platform = platform_for_device_ref(device)
    supported = skill_platforms(metadata)
    supported_text = ", ".join(supported) if supported else "none"
    return {
        "ok": False,
        "error": "unsupported_platform",
        "skill": skill_name,
        "device": device or "",
        "platform": platform,
        "supported_platforms": supported,
        "message": f"Skill '{skill_name}' does not support {platform}; supported platforms: {supported_text}",
    }


def skill_platform_error_text(skill_name: str, metadata: dict[str, Any] | None, device: str | None) -> str:
    return f"ERROR: {skill_platform_error(skill_name, metadata, device)['message']}"
