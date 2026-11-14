"""Skill quality ladder (see skillhub/scoring/v1.json).

Every number lives in ``skillhub/scoring/<version>.json`` (default v1): category
caps and item points, tier thresholds, hard-gate thresholds, freshness and the
provisional window. This module only implements the rules; it hardcodes no
point values. Points run 0 to 100 (the category caps sum to ``max_points``).

Tiers (draft, runs, proven, hardened, reference) need BOTH the points threshold
AND the hard gates, cumulatively:

    draft      skill.yaml validates, static scan clean
    runs       README + 1 signed self-run
    proven     1 independent run (other account, other fingerprint) + demo + N validators
    hardened   N OEM/Android-major combos + bench on N models + N community runs with
               Wilson LB >= x + "Known failure modes" section + re-verified within N days
    reference  hardened for N days + curator review + no open P1 > 14 days + author Contributor+

Categories: docs, self_evidence, independent, community_usage (round(cap x Wilson
LB) once ``min_runs`` exist), maintenance (re-verified within 30 days; bug
responses within 7 days). Downloads and likes are worth 0. A freshness
multiplier applies to the total.

Pure: ``quality(signals, now=..., previous=..., scoring=...)`` does no I/O when
``scoring`` is passed; otherwise the default table is read once from disk.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

DEFAULT_SCORING = Path(__file__).resolve().parents[1] / "skillhub" / "scoring" / "v1.json"
TIERS = ("draft", "runs", "proven", "hardened", "reference")


@lru_cache(maxsize=8)
def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def load_scoring(path: str | Path | None = None) -> dict:
    """The scoring table (``skillhub/scoring/v1.json`` by default)."""
    return _load(str(Path(path) if path else DEFAULT_SCORING))


def thresholds(scoring: dict) -> dict:
    return {t["id"]: t["points"] for t in scoring["tiers"]}


def wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval (95% by default). 0.0 when total is 0."""
    if total <= 0:
        return 0.0
    p = successes / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denom)


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _days_since(ts, now: datetime):
    dt = _parse(ts)
    return None if dt is None else (now - dt).total_seconds() / 86400


def freshness(last_verified, now: datetime, scoring: dict | None = None) -> float:
    """Multiplier from ``freshness.steps``; 1.0 if never verified (nothing to decay)."""
    sc = scoring or load_scoring()
    age = _days_since(last_verified, now)
    if age is None:
        return 1.0
    for step in sc["freshness"]["steps"]:
        if age <= step["max_days"]:
            return step["multiplier"]
    return sc["freshness"]["floor"]


def _each(spec, n: int):
    """``{"each": e, "cap": c}`` -> min(e*n, c); a plain number is awarded when n >= 1."""
    if isinstance(spec, dict):
        return min(spec["each"] * n, spec["cap"])
    return spec if n >= 1 else 0


def categories(s: dict, scoring: dict | None = None) -> dict:
    """Capped points per category (before freshness)."""
    sc = scoring or load_scoring()
    cat = sc["categories"]
    now_days = s.get("_days_since_verified")

    d = cat["docs"]["items"]
    docs = (
        _each(d["manifest"], bool(s.get("manifest_valid")))
        + _each(d["readme"], bool(s.get("readme")))
        + _each(d["failure_modes"], bool(s.get("failure_modes")))
        + _each(d["demo_any"], bool(s.get("demo")))
        + _each(d["demo_all_actions"], bool(s.get("demo_all_actions")))
        + _each(d.get("before_after", 0), bool(s.get("before_after")))  # v1.3
    )

    se = cat["self_evidence"]["items"]
    self_ev = (
        _each(se["first_self_run"], int(s.get("self_runs") or 0) >= 1)
        + _each(se["validators"], int(s.get("validators") or 0))  # per-action units (weakest action)
        + _each(se["bench_one_model"], int(s.get("bench_models") or 0) >= 1)
        + _each(se.get("self_second_device", 0), int(s.get("self_devices") or 0) >= 2)  # v1.3, weakest action
    )
    rel = se.get("self_reliability")
    if isinstance(rel, dict):
        # Wilson lower bound over the author's own verified runs, pass or fail; needs min_runs first
        # (v1.3 per: action = min_runs on every action, the action with the fewest own runs decides).
        own_total = int(s.get("runs_self_total") or 0)
        enough = int(s.get("runs_self_min_action_total") or 0) if rel.get("per") == "action" else own_total
        if enough >= int(rel["min_runs"]):
            self_ev += round(
                rel["cap"]
                * wilson_lower_bound(int(s.get("runs_self_passed") or 0), own_total, cat["community_usage"]["wilson_z"])
            )

    ind = cat["independent"]["items"]
    classes = int(s.get("independent_device_classes") or 0)
    models = int(s.get("bench_models") or 0)
    indep = (
        _each(ind["first_independent"], classes >= 1)
        + _each(ind["second_device_class"], classes >= 2)
        + _each(ind["third_device_class"], classes >= 3)
        + _each(ind["bench_second_model"], models >= 2)
        + _each(ind["bench_third_model"], models >= 3)
    )

    cu = cat["community_usage"]
    total = int(s.get("community_runs") or 0)
    ok = int(s.get("community_successes") or 0)
    usage = round(cu["cap"] * wilson_lower_bound(ok, total, cu["wilson_z"])) if total >= cu["min_runs"] else 0

    mt = cat["maintenance"]
    mi = mt["items"]
    # reverified_30d: full value within reverified_within_days of the last NON-SELF passing run, then a linear
    # decay to 0 at decay_days (v1.2); bugs_responded_7d: bugs answered within bug_response_within_days
    full, decay = mt["reverified_within_days"], mt.get("decay_days", mt["reverified_within_days"])
    if now_days is None:
        reverified = 0
    elif now_days <= full:
        reverified = mi["reverified_30d"]
    elif now_days >= decay:
        reverified = 0
    else:
        reverified = mi["reverified_30d"] * (decay - now_days) / (decay - full)
    maint = reverified + _each(mi["bug_response_7d"], int(s.get("bugs_responded_7d") or 0))

    raw = {"docs": docs, "self_evidence": self_ev, "independent": indep, "community_usage": usage, "maintenance": maint}
    capped = {k: round(min(v, cat[k]["cap"]), 2) for k, v in raw.items()}
    return {k: int(v) if float(v).is_integer() else v for k, v in capped.items()}


def _gates(s: dict, now: datetime, scoring: dict) -> dict:
    g = scoring["gates"]
    z = scoring["categories"]["community_usage"]["wilson_z"]
    total = int(s.get("community_runs") or 0)
    lb = wilson_lower_bound(int(s.get("community_successes") or 0), total, z)
    age = _days_since(s.get("last_verified"), now)
    hardened_days = _days_since(s.get("hardened_since"), now)
    return {
        "draft": bool(s.get("manifest_valid")) and s.get("static_scan_clean") is not False,
        "runs": bool(s.get("readme")) and int(s.get("self_runs") or 0) >= 1,
        # v1.3: Proven on own evidence (own passing current run on every action + a demo + validators); independent
        # moved up to Hardened
        "proven": (
            int(s.get("self_runs") or 0) >= 1
            and bool(s.get("demo"))
            and int(s.get("validators") or 0) >= g["proven_min_validators"]
        ),
        "hardened": (
            int(s.get("independent_device_classes") or 0) >= g.get("hardened_min_independent_device_classes", 0)
            and int(s.get("oem_combos") or 0) >= g["hardened_min_oem_combos"]
            and int(s.get("bench_models") or 0) >= g["hardened_min_bench_models"]
            and total >= g["hardened_min_community_runs"]
            and lb >= g["hardened_min_wilson_lb"]
            and bool(s.get("failure_modes"))
            and age is not None
            and age <= g["hardened_max_days_since_verified"]
        ),
        "reference": (
            hardened_days is not None
            and hardened_days >= g["reference_min_hardened_days"]
            and bool(s.get("curator_review"))
            and not s.get("open_p1_over_14d")
            and bool(s.get("author_contributor"))
        ),
    }


def quality(
    signals: dict, *, now: str | datetime | None = None, previous: dict | None = None, scoring: dict | None = None
) -> dict:
    """Quality block for one skill version.

    Returns ``{"tier", "score", "points", "categories", "freshness_multiplier", "provisional_until",
    "runs", "scoring_version"}`` (``score`` mirrors ``points`` for pre-Amendment consumers).
    ``previous`` is the prior quality block; a tier change starts the provisional window.
    ``scoring`` is the table (default ``skillhub/scoring/v1.json``).
    ``signals["frozen_tier"]`` pins the tier (a newer app version failed).
    """
    sc = scoring or load_scoring()
    now_dt = now if isinstance(now, datetime) else (_parse(now) or datetime.now(timezone.utc))
    cats = categories({**signals, "_days_since_verified": _days_since(signals.get("last_verified"), now_dt)}, sc)
    mult = freshness(signals.get("last_verified"), now_dt, sc)
    points = min(round(sum(cats.values()) * mult), sc["max_points"])
    gates = _gates(signals, now_dt, sc)
    limits = thresholds(sc)

    tier = "draft"
    for t in TIERS[1:]:
        # Ladder is cumulative: a tier needs every lower tier's gates too.
        if points >= limits[t] and all(gates[x] for x in TIERS[1 : TIERS.index(t) + 1]):
            tier = t
        else:
            break
    frozen = signals.get("frozen_tier")
    if frozen in TIERS:
        tier = frozen

    provisional_until = None
    if previous:
        prev_until = _parse(previous.get("provisional_until"))
        if previous.get("tier") in TIERS and previous.get("tier") != tier:
            provisional_until = _fmt(now_dt + timedelta(days=sc["provisional_days"]))
        elif prev_until and prev_until > now_dt:
            provisional_until = _fmt(prev_until)

    return {
        "tier": tier,
        "score": points,
        "points": points,
        "categories": cats,
        "freshness_multiplier": mult,
        "provisional_until": provisional_until,
        "runs": run_counts(signals),
        "scoring_version": sc["version"],
    }


def run_counts(signals: dict) -> dict:
    """Display block for hub-web. Every count is current-version
    artifacts except ``previous_versions`` and ``rejected``. Classes: self, maintainer, ci, independent."""

    def n(key):
        return int(signals.get(key) or 0)

    def split(cls):
        return {"passed": n(f"runs_{cls}_passed"), "total": n(f"runs_{cls}_total")}

    return {
        "current_version": signals.get("current_version"),
        "passed": n("runs_passed"),
        "total": n("runs_total"),
        "passed_90d": n("runs_passed_90d"),
        "total_90d": n("runs_total_90d"),
        "self": split("self"),
        "maintainer": split("maintainer"),
        "ci": split("ci"),
        "independent": split("independent"),
        "previous_versions": split("previous"),
        "emulator": {**split("emulator"), "unknown": n("runs_emulator_unknown")},
        "independent_devices": n("independent_devices"),
        "device_grid": dict(signals.get("device_grid") or {"cells": [], "independent_cells": 0}),
        "actions": dict(signals.get("runs_actions") or {}),
        "verifiers": list(signals.get("runs_verifiers") or []),
        "rejected": {"total": n("runs_rejected"), "reasons": dict(signals.get("runs_rejected_reasons") or {})},
        "bench": n("runs_bench"),
    }
