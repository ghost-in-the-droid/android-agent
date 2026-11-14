#!/usr/bin/env python3
"""Generate skillhub/registry.json (schema is defined by this module).

Usage:
    python tools/build_registry.py skillhub/ > skillhub/registry.json
    python tools/build_registry.py skillhub/ --now 2026-10-05T12:00:00Z

Walks ``<hub>/<author>/<slug>/skill.yaml``. The version on disk is described
from the working tree; older versions come from existing git tags
``<author>/<slug>-v<version>`` (read with ``git show``). A disk version with no
tag yet gets ``"tag": null, "commit": <HEAD>``.

Quality signals (tools/quality.py) come from the skill dir plus signed run
artifacts: ``runs/<fingerprint-hash>-<ts>.json`` (self-runs) and
``verifications/<github-login>-<fingerprint-hash>-<ts>.json`` (independent runs).
Every artifact is verified before it counts (gitd.skills.engine.evidence
.artifact_rejection): the SSH signature must verify under a key that
``<hub>/SIGNERS`` or ``<hub>/verifier-keys.yml`` lists for the principal (the
author for ``runs/``, the verifier login for ``verifications/``), simulated
runs (``simulation`` true or a non-device backend) never count, the signed
``skill`` must name this skill dir, and an optional nested ``bench`` block
must be well formed. Rejections are summarised on stderr and counted in
``quality.runs.rejected``. Fields read: ``success``, ``fingerprint_hash``,
``finished_at``, ``verifier``, ``verifier_tier`` (overridden by the tier in
verifier-keys.yml for platform principals), ``device_class``,
``fingerprint.{manufacturer|hardware, os_version}``, ``bench``. Run artifacts
are not shipped to installs. The previous
``<hub>/registry.json`` (if any) feeds provisional windows and hardened_since.

Side outputs (written by the CLI unless ``--no-write``; Amendment A):
  * ``<hub>/registry/index/<author>.<slug>.json``: per-skill version history
    ``{version, tag, commit, git_tree, sha256, size, released_at, attestation}``.
    ``git_tree`` (the skill dir's git tree id at the tag) is the integrity
    pin; null until the version is tagged, since the untagged tree still moves
    (the generated SKILL.md alone changes it on commit). ``sha256`` digests the
    sorted ``"<sha256> <path>"`` file manifest (hub-ci may replace it with the
    release tarball digest); ``attestation`` is filled by hub-ci.
  * ``<hub>/<author>/<slug>/SKILL.md``: agent-skill wrapper (frontmatter
    ``name``, ``description`` = joined ``ref_prompt`` list) so skills.sh,
    LobeHub and Hermes index the skill. Generated, never shipped to installs.

Deterministic: a version's ``commit`` is the last commit that touched its skill
dir, and ``generated_at`` defaults to the last commit touching skill content
(override with ``--now`` or ``SOURCE_DATE_EPOCH``). Unrelated commits leave the
output byte-identical, so CI only commits the registry when skills changed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

import yaml

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(1, str(_HERE.parent))

from quality import load_scoring, quality  # noqa: E402
from rep import contributors as rep_contributors  # noqa: E402
from rep import load_rep  # noqa: E402

from gitd.skills.engine.evidence import artifact_rejection, signers_line, verify_signature  # noqa: E402
from gitd.skills.engine.manifest import (  # noqa: E402
    accepted_digests,
    content_digest,
    file_hashes,
    has_python_helpers,
    is_shipped,
    shipped_files,
)
from gitd.skills.refs import is_semver, max_version, version_key  # noqa: E402

SCHEMA_VERSION = 2
DEFAULT_REPO = "ghost-in-the-droid/android-agent"
OFFICIAL_AUTHOR = "ghost"
OFFICIAL_GITHUB = "ghost-in-the-droid"
OFFICIAL_MAINTAINERS = {OFFICIAL_AUTHOR: ["C-K-Loan"]}  # GitHub logins shown on the official profile (CODEOWNERS)
# Not shipped to installs: build junk, web-only demo media, run evidence.
RESERVED_HUB_DIRS = {"registry", "scoring"}  # generated index output and the scoring table, not authors
_EXPERT_VERIFIER_TIERS = {"expert", "master", "grandmaster"}  # human verifier tracks; maintainer/ci are not independent
BENCHMARK_AUTHOR = "androidworld"  # imported scaffolds: trust "benchmark", never a community login
# Same set the loader validates against (imported, so the two cannot drift).
from gitd.skills.engine.errors import SchemaError  # noqa: E402
from gitd.skills.engine.loader import (  # noqa: E402
    DEMO_DEFAULTS,
    DEMO_MAX_BYTES,
    DEMO_TYPES,
    VALID_STATUSES,
    VALID_TOS_RISK,
    _action_names,
    _disk_demos,
    before_after_clip,
    default_demo,
    discover_action_demos,
    load_before_after_metrics,
)

# ── git helpers ─────────────────────────────────────────────────────────────


def _git(repo: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode("utf-8", "replace").strip()


def _git_bytes(repo: Path, *args: str) -> bytes | None:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def _iso_utc(ts: str | None) -> str | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── per-skill description ───────────────────────────────────────────────────


def _shipped(rel: PurePosixPath) -> bool:
    return is_shipped(rel)


def _disk_files(skill_dir: Path) -> dict[str, bytes]:
    return shipped_files(skill_dir)


def _tag_files(repo: Path, tag: str, repo_rel: str) -> dict[str, bytes]:
    listing = _git(repo, "ls-tree", "-r", "--name-only", tag, "--", repo_rel + "/")
    out = {}
    for line in (listing or "").splitlines():
        rel = PurePosixPath(line).relative_to(repo_rel)
        if _shipped(rel):
            data = _git_bytes(repo, "show", f"{tag}:{line}")
            if data is not None:
                out[str(rel)] = data
    return out


def _fingerprint(raw: dict) -> dict:
    fp = raw.get("fingerprint")
    if isinstance(fp, list):
        fp = fp[0] if fp and isinstance(fp[0], dict) else {}
    if isinstance(fp, dict) and fp:
        return {
            "os": str(fp.get("os", "android")),
            "os_version": str(fp.get("os_version", "*")),
            "hardware": str(fp.get("hardware", "*")),
            "app_package": str(fp.get("app_package", "")),
            "app_version": str(fp.get("app_version", "*")),
            "apps": [str(p) for p in (fp.get("apps") or []) if p],  # multi-app skills: the other packages
        }
    # v1 skill: flat keys
    platforms = raw.get("platforms") or ["android"]
    os_name = str(platforms[0] if isinstance(platforms, list) and platforms else platforms).lower()
    pkg = raw.get("ios_bundle_id") if os_name == "ios" else (raw.get("android_package") or raw.get("app_package"))
    return {
        "os": os_name,
        "os_version": "*",
        "hardware": "*",
        "app_package": str(pkg or ""),
        "app_version": str(raw.get("app_version_tested") or "*"),
    }


def _fingerprint_count(raw: dict) -> int:
    fp = raw.get("fingerprint")
    if isinstance(fp, list):
        return len(fp)
    return 1 if fp or raw.get("app_package") or raw.get("ios_bundle_id") else 0


def _actions(raw: dict) -> list[str]:
    acts = raw.get("actions")
    if isinstance(acts, list) and acts:
        return [str(a.get("name")) for a in acts if isinstance(a, dict) and a.get("name")]
    exports = raw.get("exports") or {}
    names = list(exports.get("workflows") or []) + list(exports.get("actions") or [])
    return [str(n) for n in names]


def _prompts(raw: dict) -> dict[str, list[str]]:
    """``{action: [ref_prompt, *ref_prompt_variants]}`` so clients can search intents without the skill dir."""
    out: dict[str, list[str]] = {}
    for a in raw.get("actions") if isinstance(raw.get("actions"), list) else []:
        if not isinstance(a, dict) or not a.get("name"):
            continue
        prompts = [str(a.get("ref_prompt") or "").strip()]
        prompts += [str(v).strip() for v in ((a.get("test_case") or {}).get("ref_prompt_variants") or []) if v]
        out[str(a["name"])] = [p for p in prompts if p]
    return out


def _load_yaml(data: bytes) -> dict:
    try:
        raw = yaml.safe_load(data) or {}
    except yaml.YAMLError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _state_metadata(raw: dict) -> dict:
    """Validate and project declarations only; never publish parameter values."""
    from types import SimpleNamespace

    from gitd.skills.engine.loader import validate_secret_params
    from gitd.skills.engine.state import STATE_FIELDS, validate_states

    actions = [a for a in raw.get("actions", []) if isinstance(a, dict)]
    for action in actions:
        validate_secret_params(action)
    probes = raw.get("state_probes", {})
    validate_states(
        SimpleNamespace(
            state_probes=probes,
            actions=[
                SimpleNamespace(**{key: a.get(key, []) for key in STATE_FIELDS}, idempotent=a.get("idempotent", False))
                for a in actions
            ],
        )
    )
    if not probes:
        return {}
    return {
        "state_probes": probes,
        "action_states": {
            a["name"]: {**{key: a.get(key, []) for key in STATE_FIELDS}, "idempotent": a.get("idempotent", False)}
            for a in actions
            if any(a.get(key) for key in STATE_FIELDS)
        },
    }


def describe_version(files: dict[str, bytes], *, tag: str | None, commit: str | None) -> tuple[str, dict, dict]:
    """``(version, version_entry, raw_yaml)`` for one snapshot of a skill dir."""
    raw = _load_yaml(files.get("skill.yaml", b""))
    if raw.get("demo"):  # demos never ship to installs, wherever they live
        files = {n: b for n, b in files.items() if n != str(raw["demo"])}
    version = str(raw.get("version", "0.0.0"))
    entry = {
        "tag": tag,
        "commit": commit,
        "fingerprint": _fingerprint(raw),
        "actions": _actions(raw) or (["recorded"] if "workflows/recorded.json" in files else []),
        "prompts": _prompts(raw),
        **_state_metadata(raw),
        "data_access": [str(d) for d in (raw.get("data_access") or [])],
        "license": str(raw.get("license") or "") or None,
        "side_effects": [str(x) for x in (raw.get("side_effects") or [])],
        "destructive": raw.get("destructive") is True,
        "tos_risk": str(raw.get("tos_risk") or "") or None,
        "locale": [str(x) for x in (raw.get("locale") or [])],
        "has_python": any(n.endswith(".py") for n in files),
        "files": file_hashes(files),
        "size_bytes": sum(len(b) for b in files.values()),
    }
    return version, entry, raw


def _validator_leaf_specs(spec) -> list[dict]:
    if isinstance(spec, list):
        return [leaf for x in spec for leaf in _validator_leaf_specs(x)]
    if not isinstance(spec, dict):
        return []
    for key in ("all_of", "any_of", "not"):
        if key in spec:
            return _validator_leaf_specs(spec[key])
    return [spec] if "kind" in spec else []


def _validator_leaves(spec) -> int:
    return len(_validator_leaf_specs(spec))


_PARAM_TEXT_KINDS = {"text_visible", "ocr_text_present", "url_contains"}


def _validator_units(spec, weights: dict) -> int:
    """Weighted validator units of one action (scoring v1.1): a custom_python check or a text check
    that uses an action parameter (``{param}``) is worth ``weights`` x2 by default; a bare presence
    check x1. Scored per action so ten trivial checks on one action cannot stand in for the rest."""
    units = 0
    for leaf in _validator_leaf_specs(spec):
        kind = str(leaf.get("kind") or "")
        if kind == "custom_python":
            units += int(weights.get("custom_python", 2))
        elif kind in _PARAM_TEXT_KINDS and any(isinstance(v, str) and "{" in v and "}" in v for v in leaf.values()):
            units += int(weights.get("parameterised_text", 2))
        else:
            units += int(weights.get("default", 1))
    return units


def _validator_weights() -> dict:
    spec = load_scoring()["categories"]["self_evidence"]["items"].get("validators")
    return dict(spec.get("weights") or {}) if isinstance(spec, dict) else {}


def _bench_model(run: dict) -> str | None:
    """The agent model of a run with a ``bench`` block; ``deterministic`` is the replay arm, not a model."""
    if not isinstance(run.get("bench"), dict):
        return None
    model = str(run["bench"].get("model") or run.get("model") or "")
    return model if model and model != "deterministic" else None


def _bench_models(runs: list[dict]) -> int:
    """Distinct agent models over verified current artifacts that carry a ``bench`` block (P2-10).
    bench.yaml declarations never count."""
    return len({_bench_model(r) for r in runs} - {None})


def _has_failure_modes(skill_dir: Path) -> bool:
    import re

    pat = re.compile(r"^#+\s*known failure modes", re.I | re.M)
    for name in ("README.md", "SOFT.md"):
        f = skill_dir / name
        if f.is_file() and pat.search(f.read_text(errors="replace")):
            return True
    return False


def _manifest_valid(skill_dir: Path) -> bool:
    """Loader accepts the manifest AND reports no "required" warning (official skills used to get a pass
    for missing license / generated_with; P2-11 closes that)."""
    try:
        from gitd.skills.engine.loader import load_skill

        skill = load_skill(skill_dir)
    except Exception:
        return False
    return not any("required" in str(w) for w in (getattr(skill, "warnings", None) or []))


def _static_scan_clean(skill_dir: Path) -> bool | None:
    try:
        from gitd.skills.engine.analyze import analyze_skill
    except ImportError:
        return None
    try:
        return not any(f.severity == "high" for f in analyze_skill(skill_dir))
    except Exception:
        return None


class TrustStore:
    """allowed_signers for one hub: ``<hub>/SIGNERS`` plus every key in ``<hub>/verifier-keys.yml``.

    The combined file lives in a temp dir for the lifetime of the store. ``tier_of`` returns the tier
    verifier-keys.yml assigns to a principal, ``operator_of`` its display label. ``insider_key`` re-verifies
    a signature against the author's keys plus every maintainer-tier key: a verification signed by such a
    key is maintainer evidence whatever ``verifier`` says. Construction raises when one key appears under two
    principals or in both files (the CI assert for P0-1).
    """

    def __init__(self, hub: Path):
        import tempfile

        self.hub = Path(hub)
        self.tiers: dict[str, str] = {}
        self.operators: dict[str, str] = {}
        self.keys: dict[str, list[str]] = {}
        owners: dict[str, str] = {}
        lines: list[str] = []

        def add(principal: str, key: str, source: str) -> None:
            key = " ".join(key.split()[:2])
            if key in owners and owners[key] != principal:
                raise ValueError(
                    f"trust files: key {key[-16:]} is listed for both {owners[key]} and {principal} ({source})"
                )
            owners[key] = principal
            self.keys.setdefault(principal, []).append(key)
            lines.append(signers_line(principal, key))

        signers = self.hub / "SIGNERS"
        if signers.is_file():
            for ln in signers.read_text(encoding="utf-8").splitlines():
                if not ln.strip() or ln.lstrip().startswith("#"):
                    continue
                fields = ln.split()
                if len(fields) >= 4 and fields[1].startswith("namespaces="):
                    add(fields[0], " ".join(fields[2:4]), "SIGNERS")
        keys_file = self.hub / "verifier-keys.yml"
        if keys_file.is_file():
            try:
                data = yaml.safe_load(keys_file.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                data = {}
            for principal, info in ((data.get("principals") or {}) if isinstance(data, dict) else {}).items():
                if not isinstance(info, dict):
                    continue
                if isinstance(info.get("tier"), str):
                    self.tiers[str(principal)] = info["tier"]
                if isinstance(info.get("operator"), str):
                    self.operators[str(principal)] = info["operator"]
                for key in info.get("keys") or []:
                    try:
                        add(str(principal), str(key), "verifier-keys.yml")
                    except ValueError as exc:
                        if "listed for both" in str(exc):
                            raise
                        continue
        self._dir = tempfile.TemporaryDirectory(prefix="ghost-signers-")
        self.allowed_signers = Path(self._dir.name) / "allowed_signers"
        self.allowed_signers.write_text("".join(lines), encoding="utf-8")
        self._insider_files: dict[str, Path] = {}

    def tier_of(self, principal: str) -> str | None:
        return self.tiers.get(principal)

    def operator_of(self, principal: str) -> str | None:
        return self.operators.get(principal)

    def maintainer_principals(self) -> set[str]:
        return {p for p, t in self.tiers.items() if t == "maintainer"}

    def signer_of(self, data: dict, principals) -> str | None:
        """The first of ``principals`` (sorted) whose listed key verifies the artifact, else None."""
        payload = {k: v for k, v in data.items() if k != "signature" and not k.startswith("_")}
        for p in sorted(set(principals)):
            if self.keys.get(p) and verify_signature(payload, data.get("signature") or {}, self.allowed_signers, p):
                return p
        return None

    def insider_key(self, data: dict, author: str) -> bool:
        """True when the artifact's signature verifies under the author's own keys or any maintainer-tier key."""
        insiders = {author} | self.maintainer_principals()
        keys = [k for p in insiders for k in self.keys.get(p, [])]
        if not keys:
            return False
        tag = author
        if tag not in self._insider_files:
            f = Path(self._dir.name) / f"insider-{len(self._insider_files)}"
            f.write_text("".join(signers_line("insider", k) for k in keys), encoding="utf-8")
            self._insider_files[tag] = f
        payload = {k: v for k, v in data.items() if k != "signature" and not k.startswith("_")}
        return verify_signature(payload, data.get("signature") or {}, self._insider_files[tag], "insider")


def _trust_for(skill_dir: Path, trust: TrustStore | None) -> TrustStore:
    return trust if trust is not None else TrustStore(skill_dir.parents[1])


def read_run_artifacts(
    skill_dir: Path,
    sub: str,
    *,
    author: str | None = None,
    trust: TrustStore | None = None,
    rejected: list | None = None,
    metadata: dict | None = None,
) -> list[dict]:
    """Verified run artifacts in ``<skill_dir>/<sub>/*.json``, each tagged with ``_class``.

    Unreadable, unsigned, simulated, mis-attributed or unverifiable ones are skipped and, when ``rejected``
    is given, appended as ``(file, reason)``. Verification principal: the author for ``runs``, the signed
    ``verifier`` field for ``verifications`` (no filename fallback: ``no-verifier``). Classes:
    ``self`` (runs/, or verifier == author), ``maintainer`` (verifier is maintainer-tier, or the signing key is
    the author's or a maintainer's), ``ci`` (platform-tier principal with its own key), ``independent``.
    """
    out = []
    d = skill_dir / sub
    if not d.is_dir():
        return out
    author = author if author is not None else skill_dir.parent.name
    trust = _trust_for(skill_dir, trust)
    skill_ref = f"{author}/{skill_dir.name}"
    if metadata is None:
        spec = skill_dir / "skill.yaml"
        metadata = _load_yaml(spec.read_bytes()) if spec.is_file() else {}
    has_python = has_python_helpers(skill_dir)
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        stem = f.stem.split("-")
        if sub == "verifications":
            verifier = data.get("verifier")
            if not isinstance(verifier, str) or not verifier:
                if rejected is not None:
                    rejected.append((f"{skill_ref}/{sub}/{f.name}", "no-verifier"))
                continue
            principal = verifier
        else:
            principal = author
        reason = artifact_rejection(
            data,
            skill_ref=skill_ref,
            principal=principal,
            allowed_signers=trust.allowed_signers,
            metadata=metadata,
            has_python=has_python,
        )
        insider = False
        if reason == "bad-signature" and sub == "verifications":
            # The label's principal has no such key, but a maintainer (or the author) signed it: it is
            # still a verified run of this skill, classed as maintainer evidence under the original label.
            insider = trust.insider_key(data, author)
            if insider:
                reason = None
        if reason:
            if rejected is not None:
                rejected.append((f"{skill_ref}/{sub}/{f.name}", reason))
            continue
        if sub == "runs" or principal.casefold() == author.casefold():
            data["_class"] = "self"
        else:
            tier = trust.tier_of(principal)
            if insider or (tier != "maintainer" and trust.insider_key(data, author)):
                # rep goes to whoever holds the key, never to the label (None when the author signed it)
                holder = trust.signer_of(data, trust.maintainer_principals() - {author})
                data["_class"] = "maintainer"
                data["_rep_principal"] = holder
            elif tier == "maintainer":
                data["_class"] = "maintainer"
            elif tier == "platform":
                data["_class"] = "ci"
            else:
                data["_class"] = "independent"
            if tier:
                data["verifier_tier"] = tier
        data.setdefault("fingerprint_hash", stem[0])
        data["_file"] = f.name
        out.append(data)
    return out


def _ts(run: dict) -> str | None:
    return _iso_utc(run.get("finished_at") or run.get("ts") or run.get("started_at"))


def _oem_combo(run: dict):
    fp = run.get("fingerprint") if isinstance(run.get("fingerprint"), dict) else {}
    oem = fp.get("manufacturer") or fp.get("hardware")
    major = str(fp.get("os_version") or "").split(".")[0]
    return (str(oem), major) if oem and major else None


_DEVICE_AXES = ("app_version", "os_version", "screen_wxh", "density", "locale")
# Display-only names for known, measured models. Never echo arbitrary hardware,
# device names or serials from artifacts. Labels do not split coverage cells.
_DEVICE_LABELS = {
    "samsung/sm-a037f": "Samsung Galaxy A03s",
    "google/sdk_gphone64_x86_64": "Android emulator",
}


def device_cell_key(run: dict) -> tuple[str, ...]:
    """Observed fingerprint only: never fill missing measurements from skill defaults."""
    fp = run.get("fingerprint") if isinstance(run.get("fingerprint"), dict) else {}
    return tuple(
        str(fp[axis]).strip() if fp.get(axis) is not None and str(fp[axis]).strip() else "*" for axis in _DEVICE_AXES
    )


def device_grid(runs: list[dict]) -> dict:
    """Current verified artifacts, pass or fail; unknown axes are recorded but cover no cell.

    Callers exclude independent fingerprints also recorded by the author. Self and maintainer
    runs share the recorded-only `maintainer` counter. CI stays in the separate run breakdown.
    Repeated runs increment a cell's run count, never its coverage count.
    """
    cells = {}
    for run in runs:
        klass = run.get("_class")
        if klass not in ("self", "maintainer", "independent"):
            continue
        key = device_cell_key(run)
        cell = cells.setdefault(
            key,
            dict(zip(("app_version", "os_version", "screen", "density", "locale"), key))
            | {"independent": 0, "maintainer": 0},
        )
        cell["independent" if klass == "independent" else "maintainer"] += 1
        fp = run.get("fingerprint") if isinstance(run.get("fingerprint"), dict) else {}
        label = _DEVICE_LABELS.get(str(fp.get("hardware", "")).strip().casefold())
        if label:
            cell["device_labels"] = sorted(set(cell.get("device_labels", [])) | {label})
    return {
        "cells": [cells[key] for key in sorted(cells)],
        "independent_cells": sum(cell["independent"] > 0 and "*" not in key for key, cell in cells.items()),
    }


_CLASSES = ("self", "maintainer", "ci", "independent")


def _action_passed(run: dict, action: str) -> bool:
    return bool(run.get("success")) and any(
        isinstance(a, dict) and a.get("name") == action and a.get("success") for a in run.get("actions") or []
    )


def _action_total(run: dict, action: str) -> bool:
    return any(isinstance(a, dict) and a.get("name") == action for a in run.get("actions") or [])


def _is_current(run: dict, version: str, digest: str | set[str] | None) -> bool:
    if str(run.get("version")) != str(version):
        return False
    recorded = run.get("skill_sha256")
    if not (digest and isinstance(recorded, str) and recorded):
        return True
    return recorded in digest if isinstance(digest, set) else recorded == digest


def _rep_principal(run: dict) -> str | None:
    return run["_rep_principal"] if "_rep_principal" in run else str(run.get("verifier"))


def rep_credits(indep_passed: list[dict], non_self_passed: list[dict], self_runs: list[dict]) -> dict[str, dict]:
    """Per-principal rep inputs for scoring/rep-v1.json (tools/rep.py turns them into points).

    ``credited`` = runs the ladder already counts: independent ones from ``indep_passed`` (one per fingerprint,
    author fingerprints excluded), maintainer/ci ones = passing current runs. ``new_device_classes`` /
    ``new_bench_models`` = the earliest (ts, file) run to cover a class / an agent model the author never
    benched. A run signed by the author under another label credits nobody."""
    out: dict[str, dict] = {}

    def slot(r: dict) -> dict | None:
        p = _rep_principal(r)
        if not p:
            return None
        return out.setdefault(
            p, {"class": r["_class"], "credited": 0, "new_device_classes": 0, "new_bench_models": 0}
        )

    def firsts(runs: list[dict], key: Callable[[dict], str | None]) -> dict[str, dict]:
        first: dict[str, dict] = {}
        for r in sorted(runs, key=lambda r: (_ts(r) or "", str(r.get("_file")))):
            k = key(r)
            if k and k not in first:
                first[k] = r
        return first

    for r in indep_passed + [r for r in non_self_passed if r["_class"] != "independent"]:
        if (v := slot(r)) is not None:
            v["credited"] += 1
    for r in firsts(indep_passed, lambda r: str(r.get("device_class") or r.get("fingerprint_hash"))).values():
        if (v := slot(r)) is not None:
            v["new_device_classes"] += 1
    self_models = {_bench_model(r) for r in self_runs} - {None}
    for m, r in firsts(non_self_passed, _bench_model).items():
        if m not in self_models and (v := slot(r)) is not None:
            v["new_bench_models"] += 1
    return dict(sorted(out.items()))


def run_signals(
    skill_dir: Path,
    author: str,
    now: str,
    *,
    trust: TrustStore | None = None,
    rejected: list | None = None,
    version: str | None = None,
    digest: str | set[str] | None = None,
    actions: list[str] | None = None,
) -> dict:
    """Signals derived from VERIFIED run artifacts of the CURRENT skill (scoring v1.2).

    Current = ``artifact.version`` equals ``version`` (default: the skill.yaml on disk) and, when the artifact
    carries ``skill_sha256``, it equals ``digest``; artifacts without a digest cannot count for Python helpers.
    App binding and freshness are checked before a run enters either current or previous evidence.
    Per-class run credit is the minimum over ``actions`` of
    passing current runs that contain the action (weakest action, like validators). Independent device
    classes exclude fingerprints the author recorded on. ``last_verified`` is the last passing current run that
    is not self-recorded. ``rejected`` collects ``(file, reason)`` for artifacts that did not verify."""
    window_days = load_scoring()["categories"]["community_usage"]["window_days"]
    trust = _trust_for(skill_dir, trust)
    rejected = rejected if rejected is not None else []
    first_rejected = len(rejected)  # the list is shared across skills; count only this skill's entries
    raw = _load_yaml((skill_dir / "skill.yaml").read_bytes()) if (skill_dir / "skill.yaml").is_file() else {}
    version = version if version is not None else str(raw.get("version", "0.0.0"))
    actions = actions if actions is not None else _actions(raw)
    all_runs = read_run_artifacts(
        skill_dir, "runs", author=author, trust=trust, rejected=rejected, metadata=raw
    ) + read_run_artifacts(skill_dir, "verifications", author=author, trust=trust, rejected=rejected, metadata=raw)
    current = [r for r in all_runs if _is_current(r, version, digest)]
    previous = [r for r in all_runs if not _is_current(r, version, digest)]
    by_class = {c: [r for r in current if r.get("_class") == c] for c in _CLASSES}

    def per_action_min(runs: list[dict]) -> int:
        if not actions:
            return 0
        return min(sum(1 for r in runs if _action_passed(r, a)) for a in actions)

    # independent: one report per fingerprint (latest), and never a fingerprint the author recorded on
    self_fps = {str(r.get("fingerprint_hash")) for r in by_class["self"]}
    by_fp: dict[str, dict] = {}
    for r in by_class["independent"]:
        key = str(r.get("fingerprint_hash"))
        if key not in by_fp or (_ts(r) or "") > (_ts(by_fp[key]) or ""):
            by_fp[key] = r
    indep = [r for k, r in by_fp.items() if k not in self_fps]
    grid = device_grid(
        by_class["self"]
        + by_class["maintainer"]
        + [r for r in by_class["independent"] if str(r.get("fingerprint_hash")) not in self_fps]
    )
    indep_passed = [r for r in indep if r.get("success")]
    classes, expert_classes = set(), set()
    for r in indep_passed:
        cls = str(r.get("device_class") or r.get("fingerprint_hash"))
        classes.add(cls)
        if str(r.get("verifier_tier") or "").lower() in _EXPERT_VERIFIER_TIERS:
            expert_classes.add(cls)
    now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))

    def within(r: dict) -> bool:
        return bool(_ts(r)) and (now_dt - datetime.fromisoformat(_ts(r).replace("Z", "+00:00"))).days <= window_days

    window = [r for r in indep if within(r)]
    non_self_passed = [r for c in ("maintainer", "ci", "independent") for r in by_class[c] if r.get("success")]
    self_passed = [r for r in by_class["self"] if r.get("success")]
    recent = [r for r in current if within(r)]
    combos = {c for c in (_oem_combo(r) for r in self_passed + indep_passed) if c}
    emu = [r for r in current if r.get("emulator") is True]
    actions_block = {
        a: {
            c: {
                "passed": sum(1 for r in by_class[c] if _action_passed(r, a)),
                "total": sum(1 for r in by_class[c] if _action_total(r, a)),
            }
            for c in _CLASSES
        }
        for a in (actions or [])
    }
    verifiers: dict[str, dict] = {}
    for r in current:
        if r.get("_class") == "self":
            continue
        principal = str(r.get("verifier"))
        v = verifiers.setdefault(
            principal,
            {
                "principal": principal,
                "tier": trust.tier_of(principal),
                "class": r["_class"],
                "label": trust.operator_of(principal) or f"@{principal}",
                "passed": 0,
                "total": 0,
            },
        )
        v["total"] += 1
        v["passed"] += 1 if r.get("success") else 0
    rep = rep_credits(indep_passed, non_self_passed, by_class["self"])
    counts = {}
    for c in _CLASSES:
        counts[f"runs_{c}_total"] = len(by_class[c])
        counts[f"runs_{c}_passed"] = sum(1 for r in by_class[c] if r.get("success"))
    return {
        "current_version": version,
        "self_runs": per_action_min(by_class["self"]),
        # v1.3: own current runs (pass or fail) on the action with the fewest; gates self_reliability
        "runs_self_min_action_total": min(
            (sum(1 for r in by_class["self"] if _action_total(r, a)) for a in actions or []), default=0
        ),
        # v1.3: distinct device fingerprints with an own passing current run, weakest action decides
        "self_devices": min(
            (
                len({str(r.get("fingerprint_hash")) for r in by_class["self"] if _action_passed(r, a)})
                for a in actions or []
            ),
            default=0,
        ),
        "maintainer_runs": per_action_min(by_class["maintainer"]),
        "ci_runs": per_action_min(by_class["ci"]),
        "independent_runs": per_action_min(indep),
        "independent_devices": grid["independent_cells"],  # compatibility alias for one release
        "device_grid": grid,
        "independent_device_classes": len(classes),
        "independent_verifier_classes": len(expert_classes),
        "community_runs": len(window),
        "community_successes": sum(1 for r in window if r.get("success")),
        "oem_combos": len(combos),
        "last_verified": max((t for t in (_ts(r) for r in non_self_passed) if t), default=None),
        "last_self_run": max((t for t in (_ts(r) for r in self_passed) if t), default=None),
        "bench_models": _bench_models(current),
        "actions_with_passing_run": sorted(a for a in (actions or []) if any(_action_passed(r, a) for r in current)),
        **counts,
        "runs_total": len(current),
        "runs_passed": sum(1 for r in current if r.get("success")),
        "runs_total_90d": len(recent),
        "runs_passed_90d": sum(1 for r in recent if r.get("success")),
        "runs_previous_total": len(previous),
        "runs_previous_passed": sum(1 for r in previous if r.get("success")),
        "runs_emulator_total": len(emu),
        "runs_emulator_passed": sum(1 for r in emu if r.get("success")),
        "runs_emulator_unknown": sum(1 for r in current if r.get("emulator") is None),
        "runs_rejected": len(rejected) - first_rejected,
        "runs_rejected_reasons": dict(sorted(Counter(reason for _, reason in rejected[first_rejected:]).items())),
        "runs_bench": sum(1 for r in current if isinstance(r.get("bench"), dict)),
        "runs_actions": actions_block,
        "runs_verifiers": sorted(verifiers.values(), key=lambda v: v["principal"]),
        "runs_rep": rep,
    }


def _before_after_ok(skill_dir: Path) -> bool:
    """v1.3 docs item: demos/before-after.<webm|mp4|gif> within the demo limit AND demos/before-after.json in
    schema 1, judged by the same loader code the registry field uses. Any malformed or missing part earns nothing."""
    rel = before_after_clip(skill_dir)
    if rel is None or not 0 < (skill_dir / rel).stat().st_size <= DEMO_MAX_BYTES:
        return False
    try:
        return load_before_after_metrics(skill_dir) is not None
    except SchemaError:
        return False


def doc_signals(skill_dir: Path, raw: dict) -> dict:
    """Signals read from the skill directory alone (no run artifacts, no git). The ONLY
    implementation: the registry and the PR sticky comment (tools/ci/skill_signals.py) both use it."""

    def nonempty(name: str) -> bool:
        f = skill_dir / name
        return f.is_file() and f.stat().st_size > 0

    actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []
    weights = _validator_weights()
    return {
        "manifest_valid": _manifest_valid(skill_dir),
        "static_scan_clean": _static_scan_clean(skill_dir),
        "readme": nonempty("README.md"),
        "soft_md": nonempty("SOFT.md"),
        # demo_any: at least one allowed clip (default or per action) within the hard limit
        "demo": _demo_ok(skill_demo(skill_dir, raw)) or any(_demo_ok(d) for d in skill_demos(skill_dir, raw).values()),
        # demo_all_actions: every action has its own demos/<action> clip within the limit
        "demo_all_actions": _all_actions_have_demos(skill_dir, raw),
        "bench": nonempty("bench.yaml"),
        # v1.3: no-skill vs with-skill pair clip + measured metrics (demos/before-after.*)
        "before_after": _before_after_ok(skill_dir),
        "failure_modes": _has_failure_modes(skill_dir),
        # validator units per action (weights from the scoring table); signals_for turns them into the
        # weakest-action score, counting an action only once it has a passing current run (v1.2, P1-5)
        "validator_units": {
            str(a.get("name")): _validator_units(a.get("end_state_validator"), weights)
            for a in actions
            if isinstance(a, dict)
        },
        "validators_total": sum(
            _validator_leaves(a.get("end_state_validator")) for a in actions if isinstance(a, dict)
        ),
        "status": skill_status(raw),
        "fingerprints_verified": _fingerprint_count(raw),
    }


def signals_for(
    skill_dir: Path,
    raw: dict,
    *,
    author: str = "",
    now: str | None = None,
    trust: TrustStore | None = None,
    rejected: list | None = None,
    digest: str | set[str] | None = None,
) -> dict:
    """All quality signals for the skill on disk. ``digest`` = content digest of the shipped files (artifacts
    carrying ``skill_sha256`` must match it to count); computed from disk when omitted."""
    if digest is None:
        digest = accepted_digests(shipped_files(skill_dir)) if (skill_dir / "skill.yaml").is_file() else None
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    docs = doc_signals(skill_dir, raw)
    runs = run_signals(
        skill_dir,
        author,
        now,
        trust=trust,
        rejected=rejected,
        version=str(raw.get("version", "0.0.0")),
        digest=digest,
        actions=_actions(raw),
    )
    units = docs.pop("validator_units")
    status = docs.pop("status")
    exercised = set(runs["actions_with_passing_run"])
    # validators (P1-5): 0 for drafts; otherwise the weakest action, where an action with no passing current
    # run contributes 0 (a validator nobody has seen pass is a promise, not evidence)
    validators = 0 if status == "draft" or not units else min(u if a in exercised else 0 for a, u in units.items())
    return {
        **docs,
        "validators": validators,
        **runs,
        "tests_pass": None,
        "hardened_since": None,
        "curator_review": False,
        "open_p1_over_14d": False,
        "author_contributor": False,
        "bugs_responded_7d": 0,  # no bug-tracker data in the hub yet
    }


def reviewed_skills(hub: Path) -> dict[str, dict]:
    """``skillhub/REVIEWED``: one ``author/slug reviewer-login sha`` per line -> {ref: {reviewer, sha}}."""
    out = {}
    f = Path(hub) / "REVIEWED"
    if f.is_file():
        for ln in f.read_text(encoding="utf-8").splitlines():
            fields = ln.split()
            if ln.strip() and not ln.lstrip().startswith("#") and len(fields) >= 3:
                out[fields[0]] = {"reviewer": fields[1], "sha": fields[2]}
    return out


def author_trust(author: str, slug: str | None = None, reviewed: dict | None = None) -> str:
    """``official`` for the official author, ``benchmark`` for imported AndroidWorld scaffolds, ``verified``
    only when ``skillhub/REVIEWED`` records a review of this skill, ``unverified`` otherwise (P1-4)."""
    if author == OFFICIAL_AUTHOR:
        return "official"
    if author == BENCHMARK_AUTHOR:
        return "benchmark"
    if slug is not None and reviewed and f"{author}/{slug}" in reviewed:
        return "verified"
    return "unverified"


def _manifest_digest(files: dict) -> str:
    """Content digest of a ``{path: "sha256:..."}`` map; identical to the artifacts' ``skill_sha256``."""
    return content_digest(files)


def _git_tree(repo: Path | None, tag: str | None, repo_rel: str) -> str | None:
    if not repo or not tag or not repo_rel:
        return None
    return _git(repo, "rev-parse", f"{tag}:{repo_rel}")


def index_entry(
    version: str,
    vinfo: dict,
    *,
    git_tree: str | None,
    released_at: str | None,
    demo: dict | None = None,
    demos: dict | None = None,
) -> dict:
    return {
        "version": version,
        "tag": vinfo.get("tag"),
        "commit": vinfo.get("commit"),
        "git_tree": git_tree,
        "sha256": _manifest_digest(vinfo.get("files") or {}),
        "size": vinfo.get("size_bytes", 0),
        "released_at": released_at,
        "attestation": None,
        "demo": demo,  # {path, bytes, type} or None; demos are not in the files map
        "demos": demos or {},  # {action: {path, bytes, type}}
    }


def skill_md(author: str, slug: str, raw: dict) -> str:
    """SKILL.md wrapper text (D5): routes generic agent-skill indexes back to the Ghost engine."""
    prompts = [
        str(a.get("ref_prompt")).strip()
        for a in (raw.get("actions") or [])
        if isinstance(a, dict) and a.get("ref_prompt")
    ]
    desc = " | ".join(prompts) or str(raw.get("description") or slug)
    desc = " ".join(desc.split())[:1024]
    name = "-".join(f"{author}-{slug}".lower().replace("_", "-").split())[:64]
    lines = [
        "---",
        f"name: {name}",
        f"description: {json.dumps(desc, ensure_ascii=False)}",
        "---",
        "",
        "<!-- GENERATED by tools/build_registry.py from skill.yaml. Do not edit. -->",
        "",
        f"# {author}/{slug}",
        "",
        str(raw.get("description") or "").strip(),
        "",
        "Deterministic phone automation for the Ghost in the Droid engine. Replays at zero LLM tokens.",
        "",
        "## Install",
        "",
        "```bash",
        f"ghost skill install {author}/{slug}",
        "```",
        "",
        "## Run",
        "",
        "```bash",
    ]
    actions = [a for a in (raw.get("actions") or []) if isinstance(a, dict) and a.get("name")]
    for a in actions or [{"name": "<action>"}]:
        params = " ".join(
            f"--param {pp['name']}=<{pp['name']}>"
            for pp in (a.get("params") or [])
            if isinstance(pp, dict) and pp.get("name") and pp.get("required")
        )
        lines.append(
            f"ghost skill run {author}/{slug} {a['name']} --device <serial>" + (f" {params}" if params else "")
        )
    lines += ["```", ""]
    if actions:
        lines += ["## Actions", ""]
        lines += [f"- `{a['name']}`: {str(a.get('ref_prompt') or a.get('description') or '').strip()}" for a in actions]
        lines.append("")
    return "\n".join(lines)


def _demo_record(rel: str | None, size: int | None) -> dict | None:
    if not rel or size is None:
        return None
    mime = DEMO_TYPES.get(PurePosixPath(rel).suffix.lower())
    return {"path": rel, "bytes": size, "type": mime} if mime else None


def skill_demo(skill_dir: Path, raw: dict) -> dict | None:
    """``{path, bytes, type}`` for the skill's demo (``demo:`` or demo.webm / .mp4 / .gif), or None."""
    rel = default_demo(skill_dir, raw)
    f = skill_dir / rel if rel else None
    return _demo_record(rel, f.stat().st_size if f is not None and f.is_file() else None)


def _tag_demos(repo: Path | None, tag: str | None, repo_rel: str, raw: dict) -> tuple[dict | None, dict]:
    """(default clip, {action: clip}) for a tagged version, from `git ls-tree -l`
    (demos are not in the files map)."""
    if not repo or not tag:
        return None, {}
    sizes = {}
    for line in (_git(repo, "ls-tree", "-r", "-l", tag, "--", repo_rel + "/") or "").splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 4 and parts[3].isdigit():
            sizes[str(PurePosixPath(path).relative_to(repo_rel))] = int(parts[3])
    clips = discover_action_demos(list(sizes), _action_names(raw))[0]
    demos = {a: _demo_record(rel, sizes.get(rel)) for a, rel in clips.items()}
    first = next((clips[a] for a in _action_names(raw) if a in clips), None)
    rel = str(raw["demo"]) if raw.get("demo") else first or next((n for n in DEMO_DEFAULTS if n in sizes), None)
    return (_demo_record(rel, sizes.get(rel)) if rel else None), demos


def _demo_ok(d: dict | None) -> bool:
    return bool(d and 0 < d["bytes"] <= DEMO_MAX_BYTES)


def _all_actions_have_demos(skill_dir: Path, raw: dict) -> bool:
    names = _action_names(raw)
    clips = skill_demos(skill_dir, raw)
    return bool(names) and all(_demo_ok(clips.get(a)) for a in names)


def skill_demos(skill_dir: Path, raw: dict) -> dict:
    """``{action: {path, bytes, type}}`` for demos/<action>.<ext> clips (empty when none)."""
    clips = _disk_demos(skill_dir, raw)[0]
    return {a: _demo_record(rel, (skill_dir / rel).stat().st_size) for a, rel in clips.items()}


def skill_before_after(skill_dir: Path) -> dict | None:
    """``{clip: {path, bytes, type}, metrics: <before-after.json or null>}`` for the no-skill vs
    with-skill pair recording (demos/before-after.*), or None without a pair clip. The numbers describe
    one recorded pair; they are never run evidence (scoring may count the pair as a docs item)."""
    rel = before_after_clip(skill_dir)
    if not rel:
        return None
    return {"clip": _demo_record(rel, (skill_dir / rel).stat().st_size), "metrics": load_before_after_metrics(skill_dir)}


def skill_icon(skill_dir: Path, raw: dict) -> str | None:
    """`icon:` from skill.yaml, else icon.webp when present; None when the file is missing."""
    rel = str(raw.get("icon") or "icon.webp")
    return rel if (skill_dir / rel).is_file() else None


def skill_status(raw: dict) -> str:
    """Lifecycle status from skill.yaml (`status:`, default active). Unknown values
    fall back to active here; `ghost skill validate` reports them as errors."""
    st = str(raw.get("status") or "active")
    return st if st in VALID_STATUSES else "active"


# Skills that predate the required `tos_risk:` field. The list only shrinks: add the field to a manifest
# (which changes its content digest, so do it with a fresh signed run) and delete the entry.
TOS_RISK_LEGACY_UNDECLARED = frozenset({"ghost/google_maps", "ghost/play_store", "ghost/safari", "ghost/send_gmail_email"})


def validate_tos_risk(raw: dict, ref: str) -> None:
    """Fail closed: a skill without a valid `tos_risk:` is never published (legacy entries excepted)."""
    value = raw.get("tos_risk")
    if value in VALID_TOS_RISK or (value is None and ref in TOS_RISK_LEGACY_UNDECLARED):
        return
    raise ValueError(f"{ref}: `tos_risk:` must be one of {sorted(VALID_TOS_RISK)}, got {value!r}")


def validate_ref_prompts(raw: dict, ref: str) -> None:
    """Require useful sample prompts on current actions before publishing a registry."""
    for action in raw.get("actions") or []:
        name = str(action.get("name") or "<unnamed>")
        prompt = action.get("ref_prompt")
        text = prompt.strip() if isinstance(prompt, str) else ""
        if (
            len(text) < 12
            or re.search(r"TODO|TBD|FIXME", text, re.IGNORECASE)
            or text.casefold() in {name.casefold(), name.replace("_", " ").casefold()}
        ):
            raise ValueError(
                f"{ref}/{name}: ref_prompt must be at least 12 characters, descriptive, and free of TODO/TBD/FIXME placeholders"
            )


def build_skill(
    repo: Path | None,
    hub: Path,
    author: str,
    skill_dir: Path,
    *,
    head: str | None,
    fallback_time: str,
    previous: dict | None = None,
    trust: TrustStore | None = None,
    rejected: list | None = None,
) -> dict:
    slug = skill_dir.name
    repo_rel = skill_dir.relative_to(repo).as_posix() if repo else ""
    tags = {}
    if repo:
        for t in (_git(repo, "tag", "--list", f"{author}/{slug}-v*") or "").splitlines():
            v = t.rsplit("-v", 1)[-1]
            if is_semver(v):
                tags[v] = t

    versions: dict[str, dict] = {}
    demos: dict[str, dict | None] = {}
    for v, tag in tags.items():
        files = _tag_files(repo, tag, repo_rel)
        if "skill.yaml" not in files:
            continue
        commit = _git(repo, "rev-list", "-n", "1", tag)
        _, entry, tag_raw = describe_version(files, tag=tag, commit=commit)
        versions[v] = entry
        demos[v] = _tag_demos(repo, tag, repo_rel, tag_raw)

    # Last commit that touched this skill dir (not HEAD), so unrelated commits do not churn the output.
    # The generated SKILL.md is excluded so committing a regen does not move the skill's commit.
    dir_commit = (
        _git(repo, "log", "-1", "--format=%H", "--", repo_rel, f":(exclude){repo_rel}/SKILL.md") if repo else None
    ) or head
    disk_version, disk_entry, raw = describe_version(_disk_files(skill_dir), tag=None, commit=dir_commit)
    validate_ref_prompts(raw, f"{author}/{slug}")
    validate_tos_risk(raw, f"{author}/{slug}")
    if disk_version in tags:
        disk_entry["tag"] = tags[disk_version]
        disk_entry["commit"] = versions.get(disk_version, {}).get("commit") or _git(
            repo, "rev-list", "-n", "1", tags[disk_version]
        )
    versions[disk_version] = disk_entry
    demo = skill_demo(skill_dir, raw)
    action_demos = skill_demos(skill_dir, raw)
    demos[disk_version] = (demo, action_demos)

    signals = signals_for(
        skill_dir,
        raw,
        author=author,
        now=fallback_time,
        trust=trust,
        rejected=rejected,
        digest=accepted_digests(disk_entry["files"]),
    )
    prev_q = (previous or {}).get("quality") or {}
    prev_since = (prev_q.get("signals") or {}).get("hardened_since")
    if prev_since and prev_q.get("tier") in ("hardened", "reference"):
        signals["hardened_since"] = prev_since
    q = quality(signals, now=fallback_time, previous=prev_q or None)
    if q["tier"] in ("hardened", "reference") and not signals["hardened_since"]:
        signals["hardened_since"] = fallback_time
    elif q["tier"] not in ("hardened", "reference"):
        signals["hardened_since"] = None
    updated = (
        _iso_utc(_git(repo, "log", "-1", "--format=%cI", "--", repo_rel, f":(exclude){repo_rel}/SKILL.md"))
        if repo
        else None
    )
    from gitd.skills.engine.loader import iter_asks

    asks = list(iter_asks(raw))
    counts = {who: sum(a.get("who") == who for a in asks) for who in ("human", "parent_agent", "sub_agent")}
    ask_flags = (
        {"asks": counts, "tokens_at_replay": bool(counts["parent_agent"] or counts["sub_agent"])} if asks else {}
    )
    trust = author_trust(author, slug, reviewed_skills(hub))
    index = []
    for v in sorted(versions, key=version_key):
        vi = versions[v]
        tree = _git_tree(repo, vi.get("tag"), repo_rel)
        released = _iso_utc(_git(repo, "log", "-1", "--format=%cI", vi["tag"])) if vi.get("tag") else None
        vd, vds = demos.get(v) or (None, {})
        index.append(index_entry(v, vi, git_tree=tree, released_at=released, demo=vd, demos=vds))
    return {
        "_index": index,
        "_skill_md": skill_md(author, slug, raw),
        "author": author,
        "slug": slug,
        "name": str(raw.get("name") or slug),
        "description": str(raw.get("description") or ""),
        "skill_class": "soft"
        if any(not isinstance(a.get("fallback"), dict) for a in asks)
        else str(raw.get("skill_class") or "hard"),
        # quality-neutral; path relative to the skill dir (icon.webp by default), or null
        "icon": skill_icon(skill_dir, raw),
        "demo": demo,  # default clip {path, bytes, type} or null; never part of install downloads
        "demos": action_demos,  # {action: {path, bytes, type}}; never part of install downloads
        # no-skill vs with-skill pair: {clip, metrics} or null; never run evidence (docs item in scoring v1.3+)
        "before_after": skill_before_after(skill_dir),
        # "v1" = legacy (no v2 actions; run `ghost skill migrate`); hub.install refuses it.
        "schema": "v2" if isinstance(raw.get("actions"), list) and raw["actions"] else "v1",
        "trust": trust,
        "status": skill_status(raw),
        # lineage: the skill this one was forked from, the ref that replaces it, why it is deprecated (site renders)
        "forked_from": str(raw.get("forked_from") or "") or None,
        "superseded_by": str(raw.get("superseded_by") or "") or None,
        "deprecated_reason": str(raw.get("deprecated_reason") or "") or None,
        # blocked = cannot complete autonomously today; hub hides it by default, install warns.
        "flags": {"blocked": skill_status(raw) == "blocked", **ask_flags},
        "latest": max_version(versions) or disk_version,
        "versions": {v: versions[v] for v in sorted(versions, key=version_key)},
        "quality": {**q, "signals": signals},
        "updated_at": updated or fallback_time,
    }


def build_registry(
    hub: Path,
    *,
    repo_name: str | None = None,
    now: str | None = None,
    warn: Callable[[str], None] | None = None,
    previous: dict | None = None,
    side: dict | None = None,
) -> dict:
    """Build the registry dict. ``previous`` defaults to ``<hub>/registry.json`` when present.

    ``side`` (optional dict) receives ``{"index": {<author>.<slug>: {...}}, "skill_md": {<author>/<slug>: text}}``.
    """
    hub = hub.resolve()
    top = _git(hub, "rev-parse", "--show-toplevel")
    repo = Path(top).resolve() if top else None
    head = _git(repo, "rev-parse", "HEAD") if repo else None
    generated = now or _generated_at(repo, hub)
    warn = warn or (lambda m: print(f"build_registry: {m}", file=sys.stderr))

    if previous is None:
        try:
            previous = json.loads((hub / "registry.json").read_text())
        except (OSError, ValueError):
            previous = {}
    prev_skills = (previous or {}).get("skills") or {}
    trust = TrustStore(hub)
    rejected: list[tuple[str, str]] = []
    authors: dict[str, dict] = {}
    skills: dict[str, dict] = {}
    index: dict[str, dict] = {}
    skill_mds: dict[str, str] = {}
    for author_dir in sorted(
        p for p in hub.iterdir() if p.is_dir() and not p.name.startswith((".", "_")) and p.name not in RESERVED_HUB_DIRS
    ):
        author = author_dir.name
        count = 0
        for skill_dir in sorted(p for p in author_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            if not (skill_dir / "skill.yaml").is_file():
                warn(f"skipping {skill_dir}: no skill.yaml")
                continue
            entry = build_skill(
                repo,
                hub,
                author,
                skill_dir,
                head=head,
                fallback_time=generated,
                previous=prev_skills.get(f"{author}/{skill_dir.name}"),
                trust=trust,
                rejected=rejected,
            )
            key = f"{author}/{skill_dir.name}"
            index[f"{author}.{skill_dir.name}"] = {
                "author": author,
                "slug": skill_dir.name,
                "latest": entry["latest"],
                "versions": entry.pop("_index"),
            }
            skill_mds[key] = entry.pop("_skill_md")
            skills[key] = entry
            count += 1
        if count:
            authors[author] = {
                "trust": "verified"
                if any(sk["trust"] == "verified" for k, sk in skills.items() if k.startswith(author + "/"))
                else author_trust(author),
                "github": OFFICIAL_GITHUB if author == OFFICIAL_AUTHOR else author,
                "skills": count,
            }
    if rejected:
        reasons = Counter(reason for _, reason in rejected)
        warn(
            f"evidence rejected: {len(rejected)} artifact(s) do not count ("
            + ", ".join(f"{k} {v}" for k, v in sorted(reasons.items()))
            + ")"
        )
        for name, reason in rejected[:20]:
            warn(f"  {reason}: {name}")
        if len(rejected) > 20:
            warn(f"  ... {len(rejected) - 20} more")
    if side is not None:
        side["index"] = index
        side["skill_md"] = skill_mds
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "repo": repo_name or os.environ.get("GHOST_HUB_REPO", DEFAULT_REPO),
        "authors": authors,
        "skills": skills,
        "rep_version": load_rep()["version"],
        "contributors": rep_contributors(skills, authors, maintainers=OFFICIAL_MAINTAINERS),
    }


def _generated_at(repo: Path | None, hub: Path | None = None) -> str:
    """SOURCE_DATE_EPOCH, else the time of the last commit touching skill content under ``hub``
    (generated registry outputs excluded), else HEAD time, else now."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if repo:
        args = ["log", "-1", "--format=%cI"]
        if hub is not None:
            rel = hub.resolve().relative_to(repo).as_posix() if hub.resolve() != repo else "."
            args += [
                "--",
                rel,
                f":(exclude){rel}/registry.json",
                f":(exclude){rel}/registry",
                f":(exclude,glob){rel}/*/*/SKILL.md",
            ]
        ts = _iso_utc(_git(repo, *args))
        if ts:
            return ts
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dumps(registry: dict) -> str:
    return json.dumps(registry, indent=2, ensure_ascii=False) + "\n"


def write_side_files(hub: Path, side: dict) -> list[Path]:
    """Write registry/index/*.json + per-skill SKILL.md; drop stale index files. Returns paths written."""
    written = []
    idx_dir = hub / "registry" / "index"
    idx_dir.mkdir(parents=True, exist_ok=True)
    keep = set()
    for name, data in sorted(side.get("index", {}).items()):
        f = idx_dir / f"{name}.json"
        keep.add(f.name)
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if not f.exists() or f.read_text() != text:
            f.write_text(text)
            written.append(f)
    for f in idx_dir.glob("*.json"):
        if f.name not in keep:
            f.unlink()
    for key, text in sorted(side.get("skill_md", {}).items()):
        f = hub / key / "SKILL.md"
        if not f.exists() or f.read_text() != text:
            f.write_text(text)
            written.append(f)
    return written


def signing_tool_missing(hub: Path) -> bool:
    """True when the hub holds signed artifacts but ssh-keygen cannot verify them."""
    if shutil.which("ssh-keygen"):
        return False
    return any(hub.glob("*/*/runs/*.json")) or any(hub.glob("*/*/verifications/*.json"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("hub", nargs="?", default="skillhub", help="Path to the skillhub/ dir")
    p.add_argument(
        "--repo", default=None, help="org/repo recorded in the registry (default: $GHOST_HUB_REPO or %s)" % DEFAULT_REPO
    )
    p.add_argument("--now", default=None, help="Override generated_at (ISO 8601 UTC)")
    p.add_argument("-o", "--output", default=None, help="Write to file instead of stdout")
    p.add_argument("--no-write", action="store_true", help="Only print registry.json; skip registry/index + SKILL.md")
    args = p.parse_args(argv)
    hub = Path(args.hub)
    if not hub.is_dir():
        print(f"build_registry: {hub} is not a directory", file=sys.stderr)
        return 2
    if signing_tool_missing(hub):
        # verify_signature fails closed without ssh-keygen, so the build would
        # "succeed" with every artifact rejected as bad-signature and every
        # skill demoted to draft. Refuse rather than publish a void registry.
        print("build_registry: ssh-keygen is required to verify run artifacts (install openssh-client)", file=sys.stderr)
        return 2
    side: dict = {}
    try:
        text = dumps(build_registry(hub, repo_name=args.repo, now=args.now, side=side))
    except ValueError as exc:
        print(f"build_registry: {exc}", file=sys.stderr)
        return 2
    if not args.no_write:
        write_side_files(hub, side)
    if args.output:
        Path(args.output).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
