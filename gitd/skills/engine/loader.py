"""Skill YAML loader — parses a skill directory into typed dataclasses.

Public API:
    skill = load_skill(path)                    # dir containing skill.yaml
    skill = load_skill("ghost/tiktok@2.0.0")    # hub ref, see resolve_skill_dir()
    action = skill.action("get_active_account")  # KeyError if missing

Validates Schema v2 conformance at load time — raises SchemaError with
actionable hints. Load-time validation catches ~80% of author mistakes for
free before any step runs.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gitd.skills.engine.errors import SchemaError, SkillNotFoundError
from gitd.skills.locations import find_skillhub_root, installed_skills_dir
from gitd.skills.refs import MAIN, is_ref, max_version, parse_ref

log = logging.getLogger(__name__)

# ── Constants used by validation ─────────────────────────────────────────────

VALID_SKILL_CLASSES = {"hard", "soft"}
VALID_OS = {"android", "ios"}
VALID_DATA_ACCESS = {
    "contacts",
    "sms",
    "camera",
    "mic",
    "microphone",
    "location",
    "notifications",
    "clipboard",
    "files",
    "storage",
    "network",
    "calendar",
    "photos",
    "bluetooth",
}
VALID_CHECKPOINT_REASONS = {"captcha", "sms", "email", "login", "llm_decision", "generic"}
VALID_ACTION_MODES = {"draft", "post"}  # informational; used by TT skill only

# Amendment A / synthesis D6 fields
VALID_SIDE_EFFECTS = {"sends_message", "posts_content", "makes_payment", "modifies_account", "deletes_data", "none"}
VALID_TOS_RISK = {"low", "medium", "high"}
VALID_THEMES = {"light", "dark", "*"}
VALID_STATUSES = {
    "active",
    "blocked",
    "deprecated",
    "draft",
}  # lifecycle; blocked = cannot complete autonomously today; draft = scaffold, steps/validators not authored yet
DEFAULT_ICON = "icon.webp"
MAX_ICON_BYTES = 16 * 1024
DEMO_DEFAULTS = ("demo.webm", "demo.mp4", "demo.gif")  # legacy single demo, first existing one wins
DEMOS_DIR = "demos"  # demos/<action>.webm|mp4|gif (+ <action>.spec.yaml)
DEMO_SPEC_SUFFIX = ".spec.yaml"
DEMO_TYPES = {".webm": "video/webm", ".mp4": "video/mp4", ".gif": "image/gif"}
DEMO_MAX_BYTES = 3 * 1024 * 1024  # hard limit (validate error)
DEMO_WARN_BYTES = 3 * 512 * 1024  # 1.5 MB: lint warning above this
DEMO_WARN_SECONDS = 30  # lint warning (ffprobe, when installed)
DEMO_WARN_LONG_SIDE = 720
# demos/before-after.<webm|mp4|gif> (+ before-after.json): a no-skill vs with-skill pair, not an action clip
BEFORE_AFTER_STEM = "before-after"
BEFORE_AFTER_JSON = "before-after.json"
BEFORE_AFTER_OK_MEANS = ("verified_task_check", "agent_finished_turn")
BEFORE_AFTER_SIDE_KEYS = ("seconds", "tokens", "tool_calls", "ok")
OFFICIAL_AUTHOR = "ghost"  # official skills get warnings instead of errors for D6 fields until migrated
_SPDX_RE = re.compile(
    r"^(?:LicenseRef-[A-Za-z0-9.-]+|[A-Za-z0-9.+-]+)(?: (?:AND|OR|WITH) (?:LicenseRef-[A-Za-z0-9.-]+|[A-Za-z0-9.+-]+))*$"
)
_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")
_WXH_RE = re.compile(r"^\d{2,5}x\d{2,5}$")


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class Param:
    name: str
    type: str = "str"
    required: bool = False
    secret: bool = False
    default: Any = None
    values: list[Any] | None = None  # for type: enum
    description: str = ""


@dataclass
class SubroutineDef:
    """Reusable step-list, internal to a skill. NOT agent-invocable.

    Use to de-dup boilerplate across actions (e.g. nav_to_profile_tab that
    every read-only action needs). No ref_prompt / end_state_validator /
    test_case — those only apply to top-level actions.
    """

    name: str
    description: str = ""
    steps: list[dict] = field(default_factory=list)


@dataclass
class ActionDef:
    name: str
    requires_state: list[str] = field(default_factory=list)
    provides_state: list[str] = field(default_factory=list)
    clears_state: list[str] = field(default_factory=list)
    idempotent: bool = False
    description: str = ""
    ref_prompt: str = ""
    params: list[Param] = field(default_factory=list)
    pre_hooks: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    checkpoints: list[dict] = field(default_factory=list)
    end_state_validator: dict = field(default_factory=dict)
    test_case: dict = field(default_factory=dict)
    on_popup: dict = field(default_factory=dict)
    demo_params: dict = field(default_factory=dict)  # optional: params `ghost skill demo` uses when no --param is given

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)


@dataclass
class Fingerprint:
    os: str = "android"
    os_version: str = "*"
    hardware: str = "*"
    app_package: str = ""
    app_version: str = "*"
    # optional (D6)
    screen_wxh: str = "*"
    density: str = "*"
    locale: str = "*"
    theme: str = "*"
    apps: list[str] = field(
        default_factory=list
    )  # extra packages a multi-app skill drives; app_package stays the primary


@dataclass
class SkillDef:
    # Identity
    name: str
    version: str
    author: str = "ghost"
    description: str = ""
    skill_class: str = "hard"
    data_access: list[str] = field(default_factory=list)
    status: str = "active"  # active | blocked | deprecated | draft
    # Lineage (hub lifecycle): `<author>/<slug>@<version>` the skill was forked from, the ref that replaces it, why it is deprecated
    forked_from: str = ""
    superseded_by: str = ""
    deprecated_reason: str = ""
    icon: str | None = None  # path relative to skill_dir; defaults to icon.webp when present
    demo: str | None = None  # default clip: demo:, else first action clip, else demo.webm / .mp4 / .gif
    demos: dict[str, str] = field(default_factory=dict)  # action -> demos/<action>.<ext>
    before_after: str | None = None  # demos/before-after.<ext>: no-skill vs with-skill pair clip, or None
    before_after_metrics: dict | None = None  # parsed demos/before-after.json (schema 1), or None
    _demo_problems: list[str] = field(default_factory=list, repr=False)
    _demo_duplicates: list[str] = field(default_factory=list, repr=False)

    # Provenance + risk (D6)
    license: str = ""
    generated_with: str = ""
    side_effects: list[str] = field(default_factory=list)
    destructive: bool = False
    tos_risk: str = ""
    locale: list[str] = field(default_factory=list)

    # Matrix
    fingerprint: Fingerprint = field(default_factory=Fingerprint)

    # Entry (soft-skill web flows)
    entry_url: str = ""

    # Registry
    repo_url: str = ""
    skill_path: str = ""

    # Popups (Layer 2)
    popup_detectors: list[dict] = field(default_factory=list)
    os_popup_policy: dict = field(default_factory=dict)

    # Actions (agent-invocable)
    state_probes: dict = field(default_factory=dict)
    actions: list[ActionDef] = field(default_factory=list)

    # Subroutines (internal reusable step-lists — de-dup within skill)
    subroutines: list[SubroutineDef] = field(default_factory=list)

    # Filesystem
    skill_dir: Path = field(default_factory=Path)  # where skill.yaml + helpers live

    # Non-fatal validation findings (e.g. official skills missing D6 fields)
    warnings: list[str] = field(default_factory=list)
    # Raw action dicts, for checks on keys the dataclasses do not model
    _raw_actions: list[dict] = field(default_factory=list, repr=False)

    def action(self, name: str) -> ActionDef:
        for a in self.actions:
            if a.name == name:
                return a
        avail = ", ".join(a.name for a in self.actions)
        raise KeyError(f"Action {name!r} not defined on skill {self.name!r}. Available: [{avail}]")

    def subroutine(self, name: str) -> SubroutineDef:
        for s in self.subroutines:
            if s.name == name:
                return s
        avail = ", ".join(s.name for s in self.subroutines) or "(none)"
        raise KeyError(f"Subroutine {name!r} not defined on skill {self.name!r}. Available: [{avail}]")

    def action_names(self) -> list[str]:
        return [a.name for a in self.actions]

    def subroutine_names(self) -> list[str]:
        return [s.name for s in self.subroutines]


_REF_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*/[a-z][a-z0-9_-]{0,63}$")
_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")


def _validate_lineage(s) -> None:
    """forked_from is `<author>/<slug>@<version>`, superseded_by a ref, deprecated needs a reason, apps are packages."""
    if s.forked_from:
        ref, _, version = s.forked_from.partition("@")
        if not _REF_RE.match(ref) or not _VERSION_RE.match(version):
            raise SchemaError(f"`forked_from:` {s.forked_from!r} must be <author>/<slug>@<version>", skill=s.name)
        if ref == f"{s.author}/{s.name}":
            raise SchemaError("`forked_from:` cannot name the skill itself", skill=s.name)
    if s.superseded_by:
        if not _REF_RE.match(s.superseded_by.partition("@")[0]):
            raise SchemaError(f"`superseded_by:` {s.superseded_by!r} must be <author>/<slug>[@<version>]", skill=s.name)
        if s.superseded_by.partition("@")[0] == f"{s.author}/{s.name}":
            raise SchemaError("`superseded_by:` cannot name the skill itself", skill=s.name)
    if s.status == "deprecated" and not s.deprecated_reason:
        s.warnings.append("`status: deprecated` without `deprecated_reason:`; users see no explanation")
    if s.deprecated_reason and s.status != "deprecated":
        s.warnings.append("`deprecated_reason:` set but status is not deprecated")
    for package in s.fingerprint.apps:
        if not _PACKAGE_RE.match(package):
            raise SchemaError(f"`fingerprint.apps:` {package!r} is not a package name", skill=s.name)
    if s.fingerprint.app_package and s.fingerprint.app_package in s.fingerprint.apps:
        raise SchemaError("`fingerprint.apps:` lists the primary app_package; list only the other apps", skill=s.name)


# ── Loader ───────────────────────────────────────────────────────────────────

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?$")


def installed_latest_version(skill_root: Path) -> str | None:
    """Version an installed ``<author>/<slug>/`` dir points at as latest.

    Reads the ``@latest`` symlink, else ``latest.txt`` (Windows), else the highest SemVer subdir.
    """
    link = skill_root / "@latest"
    if link.is_symlink() or link.is_dir():
        target = link.resolve()
        if (target / "skill.yaml").exists():
            return target.name
    txt = skill_root / "latest.txt"
    if txt.is_file():
        v = txt.read_text().strip()
        if v and (skill_root / v / "skill.yaml").exists():
            return v
    if not skill_root.is_dir():
        return None
    return max_version(d.name for d in skill_root.iterdir() if (d / "skill.yaml").exists())


def _yaml_version(skill_dir: Path) -> str:
    try:
        raw = yaml.safe_load((skill_dir / "skill.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return ""
    return str(raw.get("version", "")) if isinstance(raw, dict) else ""


def resolve_skill_dir(ref_or_path: str | Path) -> Path:
    """Resolve a filesystem path or ``<author>/<slug>[@<version>]`` ref to a skill dir.

    Order (see gitd/skills/locations.py):
      1. existing filesystem path (file or dir)
      2. installed: ``$GHOST_SKILLS_DIR`` or ``~/.ghost/skills`` / author / slug / version
      3. repo dev fallback: ``<repo>/skillhub/<author>/<slug>/`` (pinned version must match skill.yaml)
      4. SkillNotFoundError

    A returned path may be a skill.yaml file (case 1) or a dir.
    """
    p = Path(ref_or_path)
    if p.exists():
        return p
    text = str(ref_or_path)
    if not is_ref(text):
        raise SkillNotFoundError(
            f"skill.yaml not found at {p}",
            hint="Pass a skill dir path or a hub ref like ghost/tiktok@2.0.0.",
        )
    try:
        ref = parse_ref(text)
    except ValueError as e:
        raise SkillNotFoundError(str(e), hint="Ref syntax: <author>/<slug>[@<version>]") from e
    if ref.version == MAIN:
        log.warning("skill ref %s tracks @main: unpinned, may change under you", ref.key)

    looked: list[str] = []
    root = installed_skills_dir() / ref.author / ref.slug
    version = ref.version if ref.pinned else installed_latest_version(root)
    if version:
        cand = root / version
        looked.append(str(cand))
        if (cand / "skill.yaml").exists():
            return cand
    else:
        looked.append(str(root / "@latest"))

    hub = find_skillhub_root()
    if hub is not None:
        cand = hub / ref.author / ref.slug
        looked.append(str(cand))
        if (cand / "skill.yaml").exists() and (not ref.pinned or _yaml_version(cand) == ref.version):
            return cand

    raise SkillNotFoundError(
        f"skill {ref} not found",
        payload={"looked_in": looked},
        hint=f"ghost skill install {ref.key}" + (f"@{ref.version}" if ref.pinned else ""),
    )


def load_skill(ref_or_path: str | Path) -> SkillDef:
    """Load a skill from a path or a hub ref.

    Args:
        ref_or_path: Directory path, direct path to a skill.yaml file, or
            ``<author>/<slug>[@<version>]`` (``@latest`` default).

    Returns:
        Fully-parsed SkillDef with Schema v2 validation applied.

    Raises:
        SkillNotFoundError: (a FileNotFoundError) nothing resolves / skill.yaml missing.
        SchemaError: yaml parses but violates Schema v2.
    """
    p = resolve_skill_dir(ref_or_path)
    if p.is_dir():
        yaml_path = p / "skill.yaml"
        skill_dir = p
    else:
        yaml_path = p
        skill_dir = p.parent

    if not yaml_path.exists():
        raise SkillNotFoundError(f"skill.yaml not found at {yaml_path}")

    with yaml_path.open() as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SchemaError(
                f"YAML parse error: {e}",
                hint="Check indentation + quoting. Types like 'list[str]' need quoting to avoid flow-mapping conflicts.",
            ) from e

    if not isinstance(raw, dict):
        raise SchemaError("skill.yaml root must be a mapping (dict)", hint=f"Got {type(raw).__name__}")

    skill = _parse_skill(raw, skill_dir.resolve())
    _validate_skill(skill)
    return skill


def _parse_skill(raw: dict, skill_dir: Path) -> SkillDef:
    fp_raw = raw.get("fingerprint") or {}
    fp = Fingerprint(
        os=fp_raw.get("os", "android"),
        os_version=str(fp_raw.get("os_version", "*")),
        hardware=fp_raw.get("hardware", "*"),
        app_package=fp_raw.get("app_package", ""),
        app_version=str(fp_raw.get("app_version", "*")),
        screen_wxh=str(fp_raw.get("screen_wxh", "*")),
        density=str(fp_raw.get("density", "*")),
        locale=str(fp_raw.get("locale", "*")),
        theme=str(fp_raw.get("theme", "*")),
        apps=[str(p) for p in (fp_raw.get("apps") or []) if p],
    )

    actions = [_parse_action(a) for a in (raw.get("actions") or [])]
    subroutines = [_parse_subroutine(s) for s in (raw.get("subroutines") or [])]

    return SkillDef(
        name=raw.get("name", ""),
        version=str(raw.get("version", "")),
        author=raw.get("author", "ghost"),
        description=raw.get("description", ""),
        skill_class=raw.get("skill_class", "hard"),
        data_access=list(raw.get("data_access") or []),
        status=str(raw.get("status") or "active"),
        forked_from=str(raw.get("forked_from") or ""),
        superseded_by=str(raw.get("superseded_by") or ""),
        deprecated_reason=str(raw.get("deprecated_reason") or ""),
        icon=(
            str(raw["icon"]) if raw.get("icon") else (DEFAULT_ICON if (skill_dir / DEFAULT_ICON).is_file() else None)
        ),
        demo=default_demo(skill_dir, raw),
        **_demo_fields(skill_dir, raw),
        license=str(raw.get("license") or ""),
        generated_with=str(raw.get("generated_with") or ""),
        side_effects=list(raw.get("side_effects") or []),
        destructive=raw.get("destructive", False),
        tos_risk=str(raw.get("tos_risk") or ""),
        locale=list(raw.get("locale") or []),
        fingerprint=fp,
        entry_url=raw.get("entry_url", ""),
        repo_url=raw.get("repo_url", ""),
        skill_path=raw.get("skill_path", ""),
        popup_detectors=list(raw.get("popup_detectors") or []),
        os_popup_policy=raw.get("os_popup_policy") or {},
        state_probes=raw.get("state_probes", {}),
        actions=actions,
        subroutines=subroutines,
        skill_dir=skill_dir,
        _raw_actions=[a for a in (raw.get("actions") or []) if isinstance(a, dict)],
    )


def _parse_subroutine(raw: dict) -> SubroutineDef:
    if not isinstance(raw, dict):
        raise SchemaError(f"Subroutine entry must be a mapping, got {type(raw).__name__}")
    return SubroutineDef(
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        steps=list(raw.get("steps") or []),
    )


def _parse_action(raw: dict) -> ActionDef:
    if not isinstance(raw, dict):
        raise SchemaError(f"Action entry must be a mapping, got {type(raw).__name__}")

    validate_secret_params(raw)
    params = [_parse_param(p) for p in (raw.get("params") or [])]

    return ActionDef(
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        ref_prompt=raw.get("ref_prompt", ""),
        requires_state=raw.get("requires_state", []),
        provides_state=raw.get("provides_state", []),
        clears_state=raw.get("clears_state", []),
        idempotent=raw.get("idempotent", False),
        params=params,
        pre_hooks=list(raw.get("pre_hooks") or []),
        steps=list(raw.get("steps") or []),
        checkpoints=list(raw.get("checkpoints") or []),
        end_state_validator=raw.get("end_state_validator") or {},
        test_case=raw.get("test_case") or {},
        on_popup=raw.get("on_popup") or {},
        demo_params=raw.get("demo_params") or {},
    )


def validate_secret_params(raw: dict) -> None:
    """Shared by the loader and registry: secret metadata must never embed a value."""
    for param in raw.get("params") or []:
        if not isinstance(param, dict):
            raise SchemaError("Param entry must be a mapping")
        if type(param.get("secret", False)) is not bool:
            raise SchemaError("param secret must be a boolean")
        if not param.get("secret"):
            continue
        if param.get("type", "str") != "str":
            raise SchemaError("secret params must have type str")
        name = param.get("name")
        if "default" in param or "values" in param or name in (raw.get("demo_params") or {}):
            raise SchemaError("secret params cannot have defaults, values, or demo_params")
        if name in ((raw.get("test_case") or {}).get("params") or {}):
            raise SchemaError("secret params cannot have test_case params")


def _parse_param(raw: dict) -> Param:
    if not isinstance(raw, dict):
        raise SchemaError(f"Param entry must be a mapping, got {type(raw).__name__}")
    return Param(
        name=raw.get("name", ""),
        type=raw.get("type", "str"),
        required=bool(raw.get("required", False)),
        secret=raw.get("secret", False),
        default=raw.get("default"),
        values=raw.get("values"),
        description=raw.get("description", ""),
    )


# ── Schema v2 validation ─────────────────────────────────────────────────────


def discover_action_demos(rel_paths, action_names) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """Pure: from skill-relative posix paths, the per-action clips under ``demos/``.

    Returns ``(clips, duplicates, problems)``: ``clips`` maps action -> preferred clip
    (webm, then mp4, then gif), ``duplicates`` the other clips per action, ``problems``
    every file in ``demos/`` that is not ``<action>.<webm|mp4|gif>`` or
    ``<action>.spec.yaml`` for a real action (nested dirs included). The reserved
    ``before-after.<webm|mp4|gif>`` pair clip and ``before-after.json`` are neither.
    """
    actions = set(action_names)
    found: dict[str, list[str]] = {}
    problems: list[str] = []
    order = list(DEMO_TYPES)
    for rel in sorted(rel_paths):
        parts = rel.split("/")
        if parts[0] != DEMOS_DIR or len(parts) < 2 or parts[-1].startswith("."):
            continue
        if len(parts) > 2:
            problems.append(f"{rel}: demos/ holds files only, no sub-dirs")
            continue
        name = parts[1]
        if name == BEFORE_AFTER_JSON:
            continue
        if name.endswith(DEMO_SPEC_SUFFIX):
            stem = name[: -len(DEMO_SPEC_SUFFIX)]
            if stem not in actions:
                problems.append(f"{rel}: no action named {stem!r}")
            continue
        suffix = Path(name).suffix.lower()
        stem = name[: -len(suffix)] if suffix else name
        if suffix not in DEMO_TYPES:
            problems.append(f"{rel}: not a webm/mp4/gif clip or a .spec.yaml")
        elif stem == BEFORE_AFTER_STEM:
            continue  # the pair clip, read by before_after_clip()
        elif stem not in actions:
            problems.append(f"{rel}: no action named {stem!r}")
        else:
            found.setdefault(stem, []).append(rel)
    clips, dups = {}, {}
    for action, rels in found.items():
        rels.sort(key=lambda r: order.index(Path(r).suffix.lower()))
        clips[action], rest = rels[0], rels[1:]
        if rest:
            dups[action] = rest
    return clips, dups, problems


def _action_names(raw: dict) -> list[str]:
    return [str(a.get("name")) for a in (raw.get("actions") or []) if isinstance(a, dict) and a.get("name")]


def _disk_demos(skill_dir: Path, raw: dict):
    d = skill_dir / DEMOS_DIR
    rels = [f.relative_to(skill_dir).as_posix() for f in d.rglob("*") if f.is_file()] if d.is_dir() else []
    return discover_action_demos(rels, _action_names(raw))


def _demo_fields(skill_dir: Path, raw: dict) -> dict:
    clips, dups, problems = _disk_demos(skill_dir, raw)
    return {
        "demos": clips,
        "before_after": before_after_clip(skill_dir),
        "before_after_metrics": load_before_after_metrics(skill_dir),
        "_demo_problems": problems,
        "_demo_duplicates": [p for v in dups.values() for p in v],
    }


def before_after_clip(skill_dir: Path) -> str | None:
    """``demos/before-after.<webm|mp4|gif>`` (first that exists, in that order) or None."""
    for ext in DEMO_TYPES:
        rel = f"{DEMOS_DIR}/{BEFORE_AFTER_STEM}{ext}"
        if (skill_dir / rel).is_file():
            return rel
    return None


def validate_before_after_metrics(data: Any, *, skill: str = "") -> dict:
    """Schema 1 of demos/before-after.json: measured numbers for the no-skill (`before`) and
    with-skill (`after`) side of one pair recording. Raises SchemaError on any malformed field."""
    where = f"{DEMOS_DIR}/{BEFORE_AFTER_JSON}"
    if not isinstance(data, dict):
        raise SchemaError(f"{where}: must be a JSON object", skill=skill)
    if data.get("schema_version") != 1:
        raise SchemaError(f"{where}: schema_version must be 1", skill=skill)
    for side in ("before", "after"):
        s = data.get(side)
        if not isinstance(s, dict) or any(k not in s for k in BEFORE_AFTER_SIDE_KEYS):
            raise SchemaError(f"{where}: `{side}` needs {', '.join(BEFORE_AFTER_SIDE_KEYS)}", skill=skill)
        for k in ("seconds", "tokens", "tool_calls"):
            v = s[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise SchemaError(f"{where}: `{side}.{k}` must be a number >= 0", skill=skill)
        if not isinstance(s["ok"], bool):
            raise SchemaError(f"{where}: `{side}.ok` must be true or false", skill=skill)
    if data.get("ok_means", BEFORE_AFTER_OK_MEANS[0]) not in BEFORE_AFTER_OK_MEANS:
        raise SchemaError(f"{where}: ok_means must be one of {', '.join(BEFORE_AFTER_OK_MEANS)}", skill=skill)
    for k in ("action", "prompt", "notes", "model", "device", "source", "recorded"):
        if data.get(k) is not None and not isinstance(data[k], str):
            raise SchemaError(f"{where}: `{k}` must be a string", skill=skill)
    return data


def load_before_after_metrics(skill_dir: Path) -> dict | None:
    """Parsed, validated demos/before-after.json, or None when the file is absent."""
    f = skill_dir / DEMOS_DIR / BEFORE_AFTER_JSON
    if not f.is_file():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SchemaError(f"{DEMOS_DIR}/{BEFORE_AFTER_JSON}: not valid JSON ({e})") from e
    return validate_before_after_metrics(data)


def default_demo(skill_dir: Path, raw: dict) -> str | None:
    """`demo:` from skill.yaml, else the first action clip (in action order), else the legacy
    demo.webm / demo.mp4 / demo.gif."""
    if raw.get("demo"):
        return str(raw["demo"])
    clips = _disk_demos(skill_dir, raw)[0]
    first = next((clips[a] for a in _action_names(raw) if a in clips), None)
    return first or next((name for name in DEMO_DEFAULTS if (skill_dir / name).is_file()), None)


def _validate_demo(s: SkillDef) -> None:
    if s._demo_problems:
        raise SchemaError(
            f"demos/: {s._demo_problems[0]}",
            skill=s.name,
            payload={"problems": s._demo_problems},
            hint="Name clips demos/<action>.webm|mp4|gif (optional demos/<action>.spec.yaml).",
        )
    for action, rel in s.demos.items():
        size = (s.skill_dir / rel).stat().st_size
        if size > DEMO_MAX_BYTES:
            raise SchemaError(
                f"{rel} is {size} bytes; the limit is {DEMO_MAX_BYTES} (3 MB)",
                skill=s.name,
                action=action,
                hint="Re-encode as webm or mp4, 30 s or shorter, long side 720 px or less.",
            )
    if s.before_after:
        size = (s.skill_dir / s.before_after).stat().st_size
        if size > DEMO_MAX_BYTES:
            raise SchemaError(
                f"{s.before_after} is {size} bytes; the limit is {DEMO_MAX_BYTES} (3 MB)",
                skill=s.name,
                hint="Re-encode the pair as webm (VP9, 10 fps, 1600 px wide fits a 3 minute pair in 2.5 MB).",
            )
    if not s.demo:
        return
    rel = Path(s.demo)
    if rel.is_absolute() or ".." in rel.parts:
        raise SchemaError(f"`demo:` {s.demo!r} must be a path inside the skill dir", skill=s.name)
    if rel.suffix.lower() not in DEMO_TYPES:
        raise SchemaError(f"`demo:` {s.demo!r} must be webm, mp4 or gif", skill=s.name)
    f = s.skill_dir / rel
    if not f.is_file():
        raise SchemaError(f"`demo:` {s.demo!r} does not exist", skill=s.name)
    size = f.stat().st_size
    if size > DEMO_MAX_BYTES:
        raise SchemaError(
            f"`demo:` {s.demo!r} is {size} bytes; the limit is {DEMO_MAX_BYTES} (3 MB)",
            skill=s.name,
            hint="Re-encode as webm or mp4, 30 s or shorter, long side 720 px or less.",
        )


def _validate_icon(s: SkillDef) -> None:
    if not s.icon:
        return
    rel = Path(s.icon)
    if rel.is_absolute() or ".." in rel.parts:
        raise SchemaError(f"`icon:` {s.icon!r} must be a path inside the skill dir", skill=s.name)
    f = s.skill_dir / rel
    if not f.is_file():
        raise SchemaError(
            f"`icon:` {s.icon!r} does not exist",
            skill=s.name,
            hint="Run tools/fetch_app_icons.py or drop the icon: field.",
        )
    size = f.stat().st_size
    if size > MAX_ICON_BYTES:
        raise SchemaError(
            f"`icon:` {s.icon!r} is {size} bytes; the limit is {MAX_ICON_BYTES}",
            skill=s.name,
            hint="96x96 WebP, aim for 8 KB or less.",
        )


def _validate_skill(s: SkillDef) -> None:
    from .state import validate_states

    validate_states(s)
    if not s.name:
        raise SchemaError("`name:` is required")
    if not _NAME_RE.match(s.name):
        raise SchemaError(
            f"`name:` {s.name!r} invalid — must match {_NAME_RE.pattern}",
            hint="Use kebab-case: lowercase, digits, hyphens, underscores; start with a letter.",
        )
    if not s.version:
        raise SchemaError("`version:` is required")
    if not _VERSION_RE.match(s.version):
        raise SchemaError(
            f"`version:` {s.version!r} invalid — must be SemVer (e.g. 1.2.3, 2.0.0-rc1)",
        )
    if s.skill_class not in VALID_SKILL_CLASSES:
        raise SchemaError(
            f"`skill_class:` {s.skill_class!r} invalid",
            hint=f"Must be one of {sorted(VALID_SKILL_CLASSES)}",
        )
    _validate_icon(s)
    _validate_demo(s)
    if s.status not in VALID_STATUSES:
        raise SchemaError(
            f"`status:` {s.status!r} invalid",
            skill=s.name,
            hint=f"Must be one of {sorted(VALID_STATUSES)} (default active)",
        )
    _validate_lineage(s)
    for da in s.data_access:
        if da not in VALID_DATA_ACCESS:
            raise SchemaError(
                f"`data_access:` {da!r} unknown",
                hint=f"Valid values: {sorted(VALID_DATA_ACCESS)}",
            )
    if s.fingerprint.os not in VALID_OS:
        raise SchemaError(f"`fingerprint.os:` {s.fingerprint.os!r} must be one of {sorted(VALID_OS)}")
    _validate_d6(s)
    if not s.actions:
        raise SchemaError(
            "Skill declares zero actions",
            hint="Add at least one entry to `actions:` — actions are the first-class thing agents invoke.",
        )

    seen = set()
    for a in s.actions:
        if a.name in seen:
            raise SchemaError(f"Duplicate action name {a.name!r}")
        seen.add(a.name)
        _validate_action(s, a)

    sub_seen = set()
    for sr in s.subroutines:
        if not sr.name or not _NAME_RE.match(sr.name):
            raise SchemaError(f"Subroutine name {sr.name!r} invalid — must match {_NAME_RE.pattern}")
        if sr.name in sub_seen:
            raise SchemaError(f"Duplicate subroutine name {sr.name!r}")
        if sr.name in seen:
            raise SchemaError(
                f"Subroutine {sr.name!r} collides with an action of the same name",
                hint="Rename the subroutine (e.g. `_open_app` prefix) or the action.",
            )
        for spec in iter_asks(sr.steps):
            validate_ask(spec)
            if not isinstance(spec.get("fallback"), dict):
                s.skill_class = "soft"
        sub_seen.add(sr.name)
        if not sr.steps:
            raise SchemaError(f"Subroutine {sr.name!r} has no steps", skill=s.name)


def _validate_action(skill: SkillDef, a: ActionDef) -> None:
    if not a.name or not _NAME_RE.match(a.name):
        raise SchemaError(
            f"Action name {a.name!r} invalid — must match {_NAME_RE.pattern}",
            skill=skill.name,
            action=a.name,
        )
    if not isinstance(a.demo_params, dict):
        raise SchemaError("`demo_params:` must be a mapping of param name to value", skill=skill.name, action=a.name)
    undeclared = sorted(k for k in a.demo_params if a.param(k) is None)
    if undeclared:
        raise SchemaError(
            f"`demo_params:` names undeclared params {undeclared}",
            skill=skill.name,
            action=a.name,
            hint="Every demo_params key must be one of the action's params.",
        )
    if not a.ref_prompt:
        raise SchemaError(
            "Action missing `ref_prompt:` — required so LLMs can pick the right action",
            skill=skill.name,
            action=a.name,
            hint="Write the natural-language phrase a user would say to trigger this action.",
        )
    if not a.steps:
        raise SchemaError(
            "Action has no `steps:` — must have at least one step",
            skill=skill.name,
            action=a.name,
        )
    if not a.end_state_validator:
        raise SchemaError(
            "Action missing `end_state_validator:` — required so success is verifiable",
            skill=skill.name,
            action=a.name,
            hint="Declare at least one validator (text_visible, element_present, custom_python, etc.).",
        )

    # Param name uniqueness
    seen = set()
    for p in a.params:
        if p.name in seen:
            raise SchemaError(f"Duplicate param name {p.name!r}", skill=skill.name, action=a.name)
        seen.add(p.name)
        if p.type == "enum" and not p.values:
            raise SchemaError(
                f"Param {p.name!r} type=enum requires `values:` list",
                skill=skill.name,
                action=a.name,
            )

    for spec in iter_asks(a.steps + a.pre_hooks):
        validate_ask(spec)
        if not isinstance(spec.get("fallback"), dict):
            skill.skill_class = "soft"

    # checkpoint: steps (top level of the action)
    for i, st in enumerate(a.steps):
        if isinstance(st, dict) and "checkpoint" in st:
            _validate_checkpoint_step(skill, a, i, st["checkpoint"])

    # Checkpoint reason validation
    for i, cp in enumerate(a.checkpoints):
        reason = cp.get("reason")
        if reason and reason not in VALID_CHECKPOINT_REASONS:
            raise SchemaError(
                f"checkpoint[{i}] reason={reason!r} invalid",
                skill=skill.name,
                action=a.name,
                hint=f"Valid: {sorted(VALID_CHECKPOINT_REASONS)}",
            )


def _has_confirm_or_dry_run(s: SkillDef) -> bool:
    for raw in s._raw_actions:
        if raw.get("confirm_before"):
            return True
        if any(isinstance(st, dict) and "confirm_before" in st for st in (raw.get("steps") or [])):
            return True
    return any(p.name == "dry_run" for a in s.actions for p in a.params)


def _validate_d6(s: SkillDef) -> None:
    """Amendment A schema fields. Bad values are errors. Missing required fields are
    errors, except for official (`author: ghost`) skills, where they are warnings until migrated."""
    official = s.author == OFFICIAL_AUTHOR

    def missing(msg: str, hint: str) -> None:
        if official:
            s.warnings.append(f"{msg} (required for new skills; official skills: migrate)")
        else:
            raise SchemaError(msg, skill=s.name, hint=hint)

    if not s.license:
        missing("`license:` is required (SPDX id, e.g. MIT, Apache-2.0)", "Add `license: MIT` or another SPDX id.")
    elif not _SPDX_RE.match(s.license):
        raise SchemaError(f"`license:` {s.license!r} is not an SPDX expression", skill=s.name)
    if not s.generated_with.strip():
        missing(
            "`generated_with:` is required (how the skill was authored)",
            "Free text, e.g. `generated_with: human` or `generated_with: claude-opus-5-5 via ghost skill mine`.",
        )
    for se in s.side_effects:
        if se not in VALID_SIDE_EFFECTS:
            raise SchemaError(
                f"`side_effects:` {se!r} unknown", skill=s.name, hint=f"Valid values: {sorted(VALID_SIDE_EFFECTS)}"
            )
    if "none" in s.side_effects and len(s.side_effects) > 1:
        raise SchemaError("`side_effects:` 'none' cannot be combined with other values", skill=s.name)
    if not isinstance(s.destructive, bool):
        raise SchemaError(f"`destructive:` must be true or false, got {s.destructive!r}", skill=s.name)
    if s.tos_risk and s.tos_risk not in VALID_TOS_RISK:
        raise SchemaError(f"`tos_risk:` {s.tos_risk!r} invalid", skill=s.name, hint=f"One of {sorted(VALID_TOS_RISK)}")
    for loc in s.locale:
        if not isinstance(loc, str) or not _LOCALE_RE.match(loc):
            raise SchemaError(f"`locale:` {loc!r} is not a BCP-47 tag", skill=s.name, hint="e.g. en-US, de-DE")
    fp = s.fingerprint
    if fp.screen_wxh != "*" and not _WXH_RE.match(fp.screen_wxh):
        raise SchemaError(f"`fingerprint.screen_wxh:` {fp.screen_wxh!r} must look like 1080x2400", skill=s.name)
    if fp.density != "*" and not fp.density.isdigit():
        raise SchemaError(f"`fingerprint.density:` {fp.density!r} must be a dpi integer", skill=s.name)
    if fp.theme not in VALID_THEMES:
        raise SchemaError(f"`fingerprint.theme:` {fp.theme!r} must be one of {sorted(VALID_THEMES)}", skill=s.name)
    if fp.locale != "*" and not _LOCALE_RE.match(fp.locale):
        raise SchemaError(f"`fingerprint.locale:` {fp.locale!r} is not a BCP-47 tag", skill=s.name)
    if s.destructive and not _has_confirm_or_dry_run(s):
        missing(
            "`destructive: true` needs a `confirm_before:` gate or a `dry_run` param",
            "Add `confirm_before:` to the destructive action, or a `dry_run` bool param.",
        )


def _validate_checkpoint_step(skill: SkillDef, a: ActionDef, i: int, cp) -> None:
    if not isinstance(cp, dict):
        raise SchemaError(
            f"step[{i}] checkpoint: must be a mapping {{reason, prompt, success?, timeout_s?}}",
            skill=skill.name,
            action=a.name,
        )
    reason = cp.get("reason")
    if reason and reason not in VALID_CHECKPOINT_REASONS:
        raise SchemaError(
            f"step[{i}] checkpoint reason={reason!r} invalid",
            skill=skill.name,
            action=a.name,
            hint=f"Valid: {sorted(VALID_CHECKPOINT_REASONS)}",
        )
    t = cp.get("timeout_s")
    if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or t < 0):
        raise SchemaError(
            f"step[{i}] checkpoint timeout_s={t!r} must be a number >= 0 (0 waits indefinitely)",
            skill=skill.name,
            action=a.name,
        )
    succ = cp.get("success")
    if succ is not None and not isinstance(succ, (dict, list)):
        raise SchemaError(f"step[{i}] checkpoint success: must be a validator spec", skill=skill.name, action=a.name)


def iter_asks(value):
    if isinstance(value, dict):
        if "ask" in value:
            yield value["ask"]
        for key, child in value.items():
            if key != "ask":
                yield from iter_asks(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_asks(child)


def validate_ask(spec):
    from .ask import validate_answer
    from .errors import AskInvalidAnswerError

    def bad(message):
        raise SchemaError("ask: " + message)

    if not isinstance(spec, dict):
        bad("must be a mapping")
    if spec.get("who") not in ("human", "parent_agent", "sub_agent"):
        bad("who must be human, parent_agent or sub_agent")
    if not isinstance(spec.get("prompt"), str) or not spec["prompt"]:
        bad("prompt must be a nonempty string")
    if not isinstance(spec.get("store_as"), str) or not spec["store_as"] or spec["store_as"].startswith("_"):
        bad("store_as is required and cannot be private")
    schema = spec.get("schema")
    if not isinstance(schema, dict) or schema.get("type") not in ("str", "int", "enum", "json"):
        bad("schema requires type str, int, enum or json")
    if schema["type"] == "enum" and (not isinstance(schema.get("values"), list) or not schema["values"]):
        bad("enum schema requires nonempty values")
    timeout = spec.get("timeout_s", 0)
    if type(timeout) is not int or timeout < 0:
        bad("timeout_s must be an integer >= 0")
    attach = spec.get("attach", [])
    if not isinstance(attach, list):
        bad("attach must be a list")
    for item in attach:
        if item in ("screenshot", "a11y"):
            continue
        if (
            not isinstance(item, dict)
            or set(item) != {"params"}
            or not isinstance(item["params"], list)
            or not all(isinstance(x, str) for x in item["params"])
        ):
            bad("attach accepts screenshot, a11y or params: [names]")
    fb = spec.get("fallback", "fail")
    if fb != "fail":
        if not isinstance(fb, dict) or set(fb) != {"value"}:
            bad("fallback must be fail or {value: ...}")
        try:
            validate_answer(fb["value"], schema)
        except AskInvalidAnswerError:
            bad("fallback does not match schema")
