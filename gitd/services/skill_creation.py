"""Shared helpers for creating recorded mobile automation skills."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from gitd.skills.platforms import normalize_platforms

_MISSING = object()


def _json_or_value(value: Any, default: Any = _MISSING) -> Any:
    if value is None:
        if default is _MISSING:
            return None
        return default
    if isinstance(value, str):
        if not value.strip():
            if default is _MISSING:
                return None
            return default
        return json.loads(value)
    return value


def _platform_list(platforms: Any, *, app_package: str, ios_bundle_id: str) -> list[str]:
    if isinstance(platforms, str):
        raw_text = platforms.strip()
        if not raw_text:
            raw = []
        else:
            try:
                raw = json.loads(raw_text)
            except json.JSONDecodeError:
                raw = [p.strip() for p in raw_text.split(",")]
    else:
        raw = _json_or_value(platforms, default=[])
    if isinstance(raw, str):
        raw = [p.strip() for p in raw.split(",")]
    parsed = normalize_platforms(raw)
    if parsed:
        return parsed
    return ["ios"] if ios_bundle_id and not app_package else ["android"]


def _platform_meta(app_package: str, android_package: str | None, ios_bundle_id: str, platforms: Any) -> dict[str, Any]:
    """Compute the platform-aware skill.yaml fields shared by every skill kind."""
    app_package = app_package or ""
    android_package_source = android_package if android_package is not None else app_package
    ios_bundle_id = ios_bundle_id or ""
    parsed_platforms = _platform_list(platforms, app_package=app_package, ios_bundle_id=ios_bundle_id)

    android_package_meta = android_package_source if "android" in parsed_platforms else ""
    ios_target = ios_bundle_id
    if "ios" in parsed_platforms and not ios_target:
        ios_target = app_package
    app_package_meta = app_package if "android" in parsed_platforms else ""
    return {
        "app_package": app_package_meta,
        "android_package": android_package_meta,
        "ios_bundle_id": ios_target,
        "platforms": parsed_platforms,
    }


def create_recorded_skill(
    *,
    name: str,
    steps: Any,
    app_package: str = "",
    android_package: str | None = None,
    platforms: Any = "",
    ios_bundle_id: str = "",
    elements_ios: Any = None,
    elements_android: Any = None,
    skills_dir: str | Path | None = None,
    description_prefix: str = "Auto-generated skill with",
    description: str = "",
    kind: str = "hard",
) -> dict[str, Any]:
    """Create a recorded (HARD) skill directory with platform-aware metadata."""
    skill_name = name.strip()
    parsed_steps = _json_or_value(steps, default=[])
    if not skill_name or not parsed_steps:
        raise ValueError("name and steps required")

    pmeta = _platform_meta(app_package, android_package, ios_bundle_id, platforms)
    parsed_platforms = pmeta["platforms"]

    base_dir = Path(skills_dir) if skills_dir is not None else Path(__file__).resolve().parents[1] / "skills"
    skill_dir = base_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "actions").mkdir(exist_ok=True)
    (skill_dir / "workflows").mkdir(exist_ok=True)

    meta = {
        "name": skill_name,
        "version": "1.0.0",
        "kind": kind,
        **pmeta,
        "description": description.strip() or f"{description_prefix} {len(parsed_steps)} steps",
    }
    (skill_dir / "skill.yaml").write_text(yaml.dump(meta, default_flow_style=False))
    (skill_dir / "workflows" / "recorded.json").write_text(json.dumps(parsed_steps, indent=2))
    (skill_dir / "__init__.py").write_text(f'"""Skill: {skill_name}"""\n')

    parsed_elements_android = _json_or_value(elements_android)
    if parsed_elements_android is not None:
        (skill_dir / "elements.yaml").write_text(yaml.dump(parsed_elements_android, default_flow_style=False))

    parsed_elements_ios = _json_or_value(elements_ios)
    if parsed_elements_ios is not None:
        (skill_dir / "elements_ios.yaml").write_text(yaml.dump(parsed_elements_ios, default_flow_style=False))

    return {
        "ok": True,
        "skill": skill_name,
        "steps": len(parsed_steps),
        "dir": str(skill_dir),
        "platforms": parsed_platforms,
        "metadata": meta,
        "message": f"Skill '{skill_name}' created at skills/{skill_name}/ with {len(parsed_steps)} steps for {', '.join(parsed_platforms)}",
    }


def create_soft_skill(
    *,
    name: str,
    guidance: str,
    app_package: str = "",
    android_package: str | None = None,
    platforms: Any = "",
    ios_bundle_id: str = "",
    description: str = "",
    skills_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create a SOFT skill: markdown guidance (guidance.md) + skill.yaml, no steps.

    Soft skills carry no replayable actions — the guidance is surfaced to the
    LLM on demand (see list_skills / run_skill). Platform metadata is kept so
    the same compatibility matrix and app-package targeting apply.
    """
    skill_name = name.strip()
    guidance = (guidance or "").strip()
    if not skill_name or not guidance:
        raise ValueError("name and guidance required")

    pmeta = _platform_meta(app_package, android_package, ios_bundle_id, platforms)
    parsed_platforms = pmeta["platforms"]

    base_dir = Path(skills_dir) if skills_dir is not None else Path(__file__).resolve().parents[1] / "skills"
    skill_dir = base_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "name": skill_name,
        "version": "1.0.0",
        "kind": "soft",
        **pmeta,
        "description": description or f"Guidance for {parsed_platforms and parsed_platforms[0] or 'the app'}",
    }
    (skill_dir / "skill.yaml").write_text(yaml.dump(meta, default_flow_style=False))
    (skill_dir / "guidance.md").write_text(guidance if guidance.endswith("\n") else guidance + "\n")
    (skill_dir / "__init__.py").write_text(f'"""Soft skill: {skill_name}"""\n')

    return {
        "ok": True,
        "skill": skill_name,
        "kind": "soft",
        "dir": str(skill_dir),
        "platforms": parsed_platforms,
        "metadata": meta,
        "guidance_chars": len(guidance),
        "message": f"Soft skill '{skill_name}' created at skills/{skill_name}/ ({len(guidance)} chars of guidance)",
    }
