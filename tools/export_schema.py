#!/usr/bin/env python3
"""Export a JSON Schema (draft 2020-12) for skill.yaml from the loader dataclasses.

Usage:
    python tools/export_schema.py                       # print to stdout
    python tools/export_schema.py -o site/src/lib/hub/skill.schema.json

The schema is derived by introspecting `gitd.skills.engine.loader` (SkillDef,
ActionDef, Param, SubroutineDef, Fingerprint + the VALID_* enums), then
overlaid with the contract Amendment A field constraints (license,
side_effects, destructive, tos_risk, generated_with, locale, extra fingerprint
keys); the overlay wins over the loader's bare dataclass types. If the loader cannot be imported, a stub
schema with the same shape is emitted and marked `x-ghost-source: stub`.

Consumed by the site `/skills/validate` page (ajv in the browser). Keep it
dependency-free: stdlib only.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import typing
from pathlib import Path

SCHEMA_ID = "https://ghostinthedroid.com/skills/schema/v2.json"

# Mirrors loader._NAME_RE / _VERSION_RE (kept literal so the stub path works).
NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
VERSION_PATTERN = r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?$"

# Amendment A / synthesis D6.
SIDE_EFFECTS = ["sends_message", "posts_content", "makes_payment", "modifies_account", "deletes_data", "none"]
TOS_RISK = ["low", "medium", "high"]
TRUST_TIERS = ["official", "benchmark", "verified", "unverified", "quarantined"]
STATUSES = ["active", "blocked", "deprecated", "draft"]  # mirrors loader.VALID_STATUSES

# Fields that the loader rejects when empty (see loader._validate_skill / _validate_action).
SKILL_REQUIRED = ["name", "version", "actions"]
ACTION_REQUIRED = ["name", "ref_prompt", "steps", "end_state_validator"]
# Required for new skills; the validate page downgrades to warnings for author `ghost`.
AMENDMENT_REQUIRED = ["license", "generated_with"]

# Fields that are runtime-only and never written in skill.yaml.
# loader-internal, not part of skill.yaml (before_after* come from demos/before-after.* on disk)
SKIP_FIELDS = {"skill_dir", "warnings", "_raw_actions", "before_after", "before_after_metrics"}


def _ann_to_schema(ann: typing.Any, defs: dict) -> dict:
    origin = typing.get_origin(ann)
    args = typing.get_args(ann)
    if ann is typing.Any:
        return {}
    if origin is typing.Union or (origin is not None and str(origin) == "types.UnionType"):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _ann_to_schema(non_none[0], defs)
        return {"anyOf": [_ann_to_schema(a, defs) for a in non_none]}
    if origin in (list, typing.List):
        item = _ann_to_schema(args[0], defs) if args else {}
        return {"type": "array", "items": item}
    if origin in (dict, typing.Dict) or ann is dict:
        return {"type": "object"}
    if ann is list:
        return {"type": "array"}
    if ann is str:
        return {"type": "string"}
    if ann is bool:
        return {"type": "boolean"}
    if ann is int:
        return {"type": "integer"}
    if ann is float:
        return {"type": "number"}
    if dataclasses.is_dataclass(ann):
        name = ann.__name__
        if name not in defs:
            defs[name] = {}  # placeholder breaks recursion
            defs[name] = _dataclass_schema(ann, defs)
        return {"$ref": f"#/$defs/{name}"}
    return {}


def _dataclass_schema(cls: type, defs: dict) -> dict:
    hints = typing.get_type_hints(cls)
    props = {}
    for f in dataclasses.fields(cls):
        if f.name in SKIP_FIELDS or f.name.startswith("_"):
            continue
        props[f.name] = _ann_to_schema(hints.get(f.name, typing.Any), defs)
    return {"type": "object", "properties": props, "additionalProperties": True}


def _overlay(schema: dict, enums: dict) -> dict:
    """Apply loader enums, patterns, required lists and Amendment A fields."""
    defs = schema["$defs"]
    skill = schema
    sp = skill["properties"]

    sp["name"].update({"pattern": NAME_PATTERN, "description": "kebab-case slug"})
    sp["version"].update({"pattern": VERSION_PATTERN, "description": "SemVer"})
    if "skill_class" in sp:
        sp["skill_class"]["enum"] = sorted(enums["skill_class"])
    sp["status"] = {
        "type": "string",
        "enum": sorted(enums.get("status", STATUSES)),
        "default": "active",
        "description": "Lifecycle: blocked = cannot complete autonomously today; deprecated = scheduled for removal; "
        "draft = scaffold whose steps and validators are not authored yet.",
    }
    if "data_access" in sp:
        sp["data_access"]["items"] = {"enum": sorted(enums["data_access"])}
    if "actions" in sp:
        sp["actions"]["minItems"] = 1
    sp.setdefault("trust_tier", {"enum": TRUST_TIERS, "description": "Set by the registry, never by the author."})

    sp["forked_from"] = {
        "type": "string",
        "pattern": r"^[a-z0-9][a-z0-9_.-]*/[a-z][a-z0-9_-]{0,63}@\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?$",
        "description": "<author>/<slug>@<version> this skill was forked from (ghost skill fork writes it); evidence never carries over",
    }
    sp["superseded_by"] = {
        "type": "string",
        "pattern": r"^[a-z0-9][a-z0-9_.-]*/[a-z][a-z0-9_-]{0,63}(@.+)?$",
        "description": "Ref users should install instead of this skill",
    }
    sp["deprecated_reason"] = {"type": "string", "minLength": 1, "description": "Why status is deprecated"}
    amendment = {
        "license": {"type": "string", "minLength": 1, "description": "SPDX identifier, e.g. MIT or Apache-2.0"},
        "side_effects": {"type": "array", "items": {"enum": SIDE_EFFECTS}, "uniqueItems": True},
        "destructive": {"type": "boolean"},
        "tos_risk": {"enum": TOS_RISK},
        "generated_with": {
            "type": "string",
            "minLength": 1,
            "description": "Tools or models used to author the skill; write 'hand' if none.",
        },
        "locale": {
            "type": "array",
            "items": {"type": "string"},
            "description": "BCP-47 locales the skill was tested in",
        },
    }
    for k, v in amendment.items():
        sp[k] = v  # override: the loader declares these with bare types; the overlay carries enums/patterns
    skill["required"] = SKILL_REQUIRED + AMENDMENT_REQUIRED

    fp = defs.get("Fingerprint")
    if fp:
        fp["properties"]["os"]["enum"] = sorted(enums["os"])
        for k, v in {
            "screen_wxh": {"type": "string", "pattern": r"^\d+x\d+$"},
            "density": {"type": ["integer", "string"]},
            "locale": {"type": "string"},
            "theme": {"enum": ["light", "dark", "*"]},
        }.items():
            fp["properties"][k] = v
        for k in ("os_version", "app_version"):
            fp["properties"][k] = {"type": ["string", "number"]}
        fp["properties"]["apps"] = {
            "type": "array",
            "items": {"type": "string", "pattern": r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$"},
            "uniqueItems": True,
            "description": "Other packages a multi-app skill drives; app_package stays the primary",
        }

    state_pattern = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
    selector = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"const": "element_present"},
            **{key: {"type": "string", "minLength": 1, "pattern": r"^[^{}]+$"} for key in ("id", "text", "desc")},
        },
        "required": ["kind"],
        "oneOf": [{"required": [key]} for key in ("id", "text", "desc")],
        "minProperties": 2,
        "maxProperties": 2,
    }
    sp["state_probes"] = {
        "type": "object",
        "propertyNames": {"pattern": state_pattern},
        "additionalProperties": {
            "oneOf": [
                selector,
                {"type": "object", "properties": {"not": selector}, "required": ["not"], "additionalProperties": False},
            ]
        },
    }
    act = defs.get("ActionDef")
    if act:
        for key in ("requires_state", "provides_state", "clears_state"):
            act["properties"][key] = {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "pattern": state_pattern},
            }
        act["properties"]["idempotent"] = {"type": "boolean", "default": False}
        act["properties"]["name"]["pattern"] = NAME_PATTERN
        act["properties"]["ref_prompt"]["minLength"] = 1
        act["properties"]["steps"]["minItems"] = 1
        act["properties"]["end_state_validator"]["minProperties"] = 1
        act["required"] = ACTION_REQUIRED
        cps = act["properties"].get("checkpoints")
        if cps is not None:
            cps["items"] = {
                "type": "object",
                "properties": {"reason": {"enum": sorted(enums["checkpoint_reasons"])}},
            }

    sub = defs.get("SubroutineDef")
    if sub:
        sub["properties"]["name"]["pattern"] = NAME_PATTERN
        sub["properties"]["steps"]["minItems"] = 1
        sub["required"] = ["name", "steps"]

    param = defs.get("Param")
    if param:
        param["properties"]["secret"] = {"type": "boolean", "default": False}
        param["required"] = ["name"]
        param["properties"]["default"] = {}
        param["properties"]["values"] = {"type": "array"}
        param["allOf"] = [
            {
                "if": {"properties": {"secret": {"const": True}}, "required": ["secret"]},
                "then": {
                    "properties": {"type": {"const": "str"}},
                    "not": {"anyOf": [{"required": ["default"]}, {"required": ["values"]}]},
                },
            },
            {
                "if": {"properties": {"type": {"const": "enum"}}, "required": ["type"]},
                "then": {"required": ["values"], "properties": {"values": {"minItems": 1}}},
            },
        ]
    return schema


def _wrap(skill_schema: dict, defs: dict, source: str) -> dict:
    out = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Ghost skill.yaml (schema v2)",
        "x-ghost-source": source,
        **skill_schema,
        "$defs": defs,
    }
    return out


def build_from_loader() -> dict:
    from gitd.skills.engine import loader  # noqa: WPS433 (import inside function by design)

    defs: dict = {}
    skill = _dataclass_schema(loader.SkillDef, defs)
    enums = {
        "skill_class": loader.VALID_SKILL_CLASSES,
        "data_access": loader.VALID_DATA_ACCESS,
        "os": loader.VALID_OS,
        "checkpoint_reasons": loader.VALID_CHECKPOINT_REASONS,
        "status": getattr(loader, "VALID_STATUSES", set(STATUSES)),
    }
    return _overlay(_wrap(skill, defs, "gitd.skills.engine.loader"), enums)


def build_stub() -> dict:
    s = {"type": "string"}
    arr = {"type": "array"}
    obj = {"type": "object"}
    defs = {
        "Param": {
            "type": "object",
            "properties": {
                "name": s,
                "type": s,
                "required": {"type": "boolean"},
                "default": {},
                "values": arr,
                "description": s,
            },
        },
        "SubroutineDef": {
            "type": "object",
            "properties": {"name": s, "description": s, "steps": {"type": "array", "items": obj}},
        },
        "ActionDef": {
            "type": "object",
            "properties": {
                "name": dict(s),
                "description": s,
                "ref_prompt": dict(s),
                "params": {"type": "array", "items": {"$ref": "#/$defs/Param"}},
                "pre_hooks": {"type": "array", "items": obj},
                "steps": {"type": "array", "items": obj},
                "checkpoints": {"type": "array", "items": obj},
                "end_state_validator": dict(obj),
                "test_case": obj,
                "on_popup": obj,
            },
        },
        "Fingerprint": {
            "type": "object",
            "properties": {
                "os": dict(s),
                "os_version": s,
                "hardware": s,
                "app_package": s,
                "app_version": s,
                "apps": {"type": "array", "items": s},
            },
        },
    }
    skill = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "name": dict(s),
            "version": dict(s),
            "author": s,
            "description": s,
            "skill_class": dict(s),
            "data_access": {"type": "array", "items": s},
            "fingerprint": {"$ref": "#/$defs/Fingerprint"},
            "entry_url": s,
            "repo_url": s,
            "skill_path": s,
            "icon": s,
            "demo": s,
            "demos": obj,
            "forked_from": s,
            "superseded_by": s,
            "deprecated_reason": s,
            "popup_detectors": {"type": "array", "items": obj},
            "os_popup_policy": obj,
            "actions": {"type": "array", "items": {"$ref": "#/$defs/ActionDef"}},
            "subroutines": {"type": "array", "items": {"$ref": "#/$defs/SubroutineDef"}},
        },
    }
    enums = {
        "skill_class": {"hard", "soft"},
        "data_access": {
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
        },
        "os": {"android", "ios"},
        "checkpoint_reasons": {"captcha", "sms", "email", "login", "llm_decision", "generic"},
    }
    return _overlay(_wrap(skill, defs, "stub"), enums)


def build_schema() -> dict:
    repo = Path(__file__).resolve().parent.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    try:
        return build_from_loader()
    except Exception as exc:  # loader missing or not importable: ship the stub
        print(f"export_schema: loader not importable ({exc}); emitting stub", file=sys.stderr)
        return build_stub()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", help="write to file instead of stdout")
    ap.add_argument("--stub", action="store_true", help="force the stub schema (no loader import)")
    args = ap.parse_args(argv)
    schema = build_stub() if args.stub else build_schema()
    text = json.dumps(schema, indent=2, sort_keys=False) + "\n"
    if args.output:
        Path(args.output).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
