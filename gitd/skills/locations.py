"""Where skills live on disk.

Three roots, in resolution order (see this module):

1. An explicit filesystem path (dev + tests), handled by the loader.
2. Installed skills: ``~/.ghost/skills/<author>/<slug>/<version>/``.
   ``GHOST_SKILLS_DIR`` overrides ``~/.ghost/skills``.
3. ``<repo>/skillhub/<author>/<slug>/`` when running from a source checkout.

The legacy v1 runtime (routers, MCP server, ``_run_skill.py``) scans flat
``<name>/skill.yaml`` dirs. ``iter_legacy_skill_dirs`` gives it both the
user-created dirs in ``gitd/skills/`` and the official ``skillhub/ghost/`` dirs.

No third-party imports here: ``gitd/skills/__init__.py`` imports this module.
"""
from __future__ import annotations

import os
from pathlib import Path

GITD_SKILLS_DIR = Path(__file__).resolve().parent
OFFICIAL_AUTHOR = "ghost"


def installed_skills_dir() -> Path:
    """Root of installed hub skills (``GHOST_SKILLS_DIR`` or ``~/.ghost/skills``)."""
    env = os.environ.get("GHOST_SKILLS_DIR")
    return Path(env).expanduser() if env else Path.home() / ".ghost" / "skills"


def find_skillhub_root(start: Path | None = None) -> Path | None:
    """Return ``<repo>/skillhub`` by walking up from ``start`` (default: this file).

    Returns None when not running from a source checkout (pip install).
    """
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        cand = parent / "skillhub"
        if cand.is_dir():
            return cand
    return None


def legacy_skill_roots(primary: Path | None = None) -> list[Path]:
    """Flat skill roots for the v1 runtime: user-created first (``primary``, default
    ``gitd/skills``), then official hub skills."""
    roots = [Path(primary) if primary is not None else GITD_SKILLS_DIR]
    hub = find_skillhub_root()
    if hub and (hub / OFFICIAL_AUTHOR).is_dir():
        roots.append(hub / OFFICIAL_AUTHOR)
    return roots


def iter_legacy_skill_dirs(primary: Path | None = None) -> list[Path]:
    """All flat ``<name>/skill.yaml`` dirs, sorted by name; first root wins on a name clash."""
    seen: dict[str, Path] = {}
    for root in legacy_skill_roots(primary):
        if not root.is_dir():
            continue
        for d in root.iterdir():
            if d.is_dir() and not d.name.startswith("__") and (d / "skill.yaml").exists():
                seen.setdefault(d.name, d)
    return [seen[k] for k in sorted(seen)]


def find_legacy_skill_dir(name: str, primary: Path | None = None) -> Path | None:
    """Locate a flat skill dir by name across ``legacy_skill_roots(primary)``."""
    if not name or "/" in name or name.startswith("."):
        return None
    for root in legacy_skill_roots(primary):
        d = root / name
        if (d / "skill.yaml").exists():
            return d
    return None


def legacy_meta(meta: dict) -> dict:
    """Expose v2 ``fingerprint:`` fields under the flat v1 keys the v1 runtime reads.

    Never overrides keys the skill already sets at top level.
    """
    fp = meta.get("fingerprint")
    if not isinstance(fp, dict):
        return meta
    out = dict(meta)
    pkg = fp.get("app_package") or ""
    os_name = fp.get("os") or "android"
    if pkg and not out.get("app_package"):
        out["app_package"] = pkg
    if pkg and os_name == "android" and not out.get("android_package"):
        out["android_package"] = pkg
    if pkg and os_name == "ios" and not out.get("ios_bundle_id"):
        out["ios_bundle_id"] = pkg
    if not out.get("platforms"):
        out["platforms"] = [os_name]
    return out
