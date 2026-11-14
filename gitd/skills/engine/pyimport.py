"""File-path imports for skill-local Python (``python_action:`` and ``custom_python``).

Schema v2 refs are ``<file>:<function>`` relative to the skill dir, e.g.
``helpers:scrape_active_handle`` -> ``<skill_dir>/helpers.py``. A dotted file
part maps to a subpath (``lib.parse:fn`` -> ``lib/parse.py``). Each file is
loaded via ``importlib.util.spec_from_file_location`` under a unique module
name ``ghost_skill_<author>_<slug>_<version>_<file>`` so two installed versions
of the same skill never share module state.

Dotted ``gitd.skills.*`` targets are not supported in v2 skills.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import yaml

from gitd.skills.engine.errors import DispatchError, ParamError

CTX_SKILL_KEY = "_current_skill"     # ctx.extras: {"dir", "author", "slug", "version"}
_SAFE = re.compile(r"[^A-Za-z0-9]+")


def _sanitize(part: str) -> str:
    return _SAFE.sub("_", part).strip("_") or "x"


def module_name(author: str, slug: str, version: str, file_part: str) -> str:
    """Unique, importable module name for one skill file."""
    parts = (author, slug, version, file_part)
    return "ghost_skill_" + "_".join(_sanitize(p) for p in parts)


def skill_identity(skill_dir: str | Path) -> dict:
    """``{"dir", "author", "slug", "version"}`` for a skill dir, read from its skill.yaml."""
    d = Path(skill_dir)
    raw: Any = {}
    try:
        raw = yaml.safe_load((d / "skill.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "dir": str(d),
        "author": str(raw.get("author") or "ghost"),
        "slug": str(raw.get("name") or d.name),
        "version": str(raw.get("version") or "0.0.0"),
    }


def identity_from_ctx(ctx) -> dict:
    """Current skill identity from a RunContext (set by runner + run_skill)."""
    ident = ctx.extras.get(CTX_SKILL_KEY)
    if ident and ident.get("dir"):
        return ident
    skill_dir = ctx.extras.get("_current_skill_dir")
    if not skill_dir:
        raise DispatchError(
            "no current skill dir in context; cannot resolve skill-local Python",
            hint="Runner sets ctx.extras['_current_skill_dir'] before dispatching steps.",
        )
    return skill_identity(skill_dir)


def _split_ref(ref: str, *, what: str) -> tuple[str, str]:
    if not isinstance(ref, str) or ":" not in ref:
        raise ParamError(
            f"{what} ref {ref!r} must be `<file>:<function>`",
            hint="Example: helpers:scrape_active_handle (resolves to helpers.py in the skill dir).",
        )
    file_part, fn_name = ref.rsplit(":", 1)
    if not file_part or not fn_name:
        raise ParamError(f"{what} ref {ref!r} must be `<file>:<function>`")
    if file_part.startswith("gitd."):
        local = file_part.rsplit(".", 1)[-1]
        raise ParamError(
            f"{what} ref {ref!r}: dotted gitd.* targets are not supported in v2 skills",
            hint=f"Use a skill-local ref: {local}:{fn_name}",
        )
    return file_part, fn_name


def _file_path(skill_dir: Path, file_part: str, *, what: str, ref: str) -> Path:
    if file_part.endswith(".py"):
        file_part = file_part[:-3]
    segs = file_part.split(".")
    if any(not s or s in ("..",) or "/" in s or "\\" in s for s in segs):
        raise ParamError(f"{what} ref {ref!r}: file part must be a dotted path inside the skill dir")
    base = skill_dir.resolve()
    path = base.joinpath(*segs[:-1], segs[-1] + ".py").resolve()
    if base not in path.parents:
        raise ParamError(f"{what} ref {ref!r} escapes the skill dir")
    return path


def load_module(skill_dir: str | Path, file_part: str, *, author: str, slug: str, version: str,
                what: str = "python_action", ref: str = "") -> ModuleType:
    """Import ``<skill_dir>/<file_part>.py`` under its unique module name (cached in sys.modules)."""
    skill_dir = Path(skill_dir)
    path = _file_path(skill_dir, file_part, what=what, ref=ref or file_part)
    if not path.is_file():
        raise DispatchError(
            f"{what}: cannot import {file_part!r}: {path} does not exist",
            hint="python_action / custom_python refs resolve relative to the skill dir.",
        )
    name = module_name(author, slug, version, file_part)
    cached = sys.modules.get(name)
    if cached is not None and Path(getattr(cached, "__file__", "") or "").resolve() == path:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DispatchError(f"{what}: cannot build import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        sys.modules.pop(name, None)
        raise DispatchError(f"{what}: cannot import {file_part!r}: {type(e).__name__}: {e}") from e
    return module


def resolve_callable(ref: str, ident: dict, *, what: str = "python_action") -> Callable:
    """Resolve ``<file>:<function>`` against the skill described by ``ident``."""
    file_part, fn_name = _split_ref(ref, what=what)
    module = load_module(
        ident["dir"], file_part,
        author=ident["author"], slug=ident["slug"], version=ident["version"],
        what=what, ref=ref,
    )
    fn = getattr(module, fn_name, None)
    if not callable(fn):
        raise DispatchError(f"{what}: {file_part}.{fn_name} not found")
    return fn


def ident_for_skill(skill) -> dict:
    """Identity dict for a loaded SkillDef (what runner + run_skill put in ctx.extras)."""
    return {"dir": str(skill.skill_dir), "author": skill.author, "slug": skill.name, "version": skill.version}


def resolve_for_skill(ref: str, skill, *, what: str = "python_action") -> Callable:
    """Same as resolve_callable, for a loaded SkillDef."""
    return resolve_callable(ref, ident_for_skill(skill), what=what)
