"""Contributor reputation (skillhub/scoring/rep-v1.json) from built registry skills.

Pure function of the registry ``skills`` and ``authors`` blocks: no git, no network, deterministic.
Identity is the GitHub login: the author namespace for published skills and the run principal
(``quality.signals.runs_rep``, filled by tools/build_registry.py) for verified / maintained runs.
"""

from __future__ import annotations

import json
import operator
import re
from functools import lru_cache
from pathlib import Path

DEFAULT_REP = Path(__file__).resolve().parents[1] / "skillhub" / "scoring" / "rep-v1.json"
_RULE = re.compile(r"^\s*(\w+)\s*(>=|>|==)\s*(\d+)\s*$")
_OPS = {">=": operator.ge, ">": operator.gt, "==": operator.eq}


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_rep(path: str | Path | None = None) -> dict:
    """The rep table (``skillhub/scoring/rep-v1.json`` by default)."""
    return _load(str(Path(path) if path else DEFAULT_REP))


def badge_holds(rule: str, stats: dict) -> bool:
    """``rule`` is ``<stat> <op> <int>`` over the contributor's ``stats``; anything else is a build error."""
    m = _RULE.match(rule)
    if not m or m.group(1) not in stats:
        raise ValueError(f"rep: bad badge rule {rule!r}")
    return _OPS[m.group(2)](stats[m.group(1)], int(m.group(3)))


def contributors(
    skills: dict[str, dict],
    authors: dict[str, dict],
    *,
    maintainers: dict[str, list[str]] | None = None,
    rep: dict | None = None,
) -> dict[str, dict]:
    """``{login: profile}`` sorted by login; rank by ``rep`` on the site. Only principals with real data appear."""
    rep = rep or load_rep()
    pub, ver, mnt = rep["published"], rep["verified"], rep["maintained"]
    excluded = set(pub.get("excluded_authors") or [])
    skip_status = set(pub.get("excluded_statuses") or [])
    out: dict[str, dict] = {}

    def profile(login: str) -> dict:
        a = authors.get(login) or {}
        return out.setdefault(
            login,
            {
                "login": login,
                "github": a.get("github") or login,
                "trust": a.get("trust"),
                "maintainers": list((maintainers or {}).get(login) or []),
                "rep": 0,
                "breakdown": {"published": 0, "verified": 0, "maintained": 0},
                "published": [],
                "verified": [],
                "maintained": [],
                "stats": {},
                "badges": [],
            },
        )

    for ref in sorted(skills):
        sk = skills[ref]
        author = sk["author"]
        q = sk.get("quality") or {}
        if author not in excluded:
            pts = 0 if sk.get("status") in skip_status else int(q.get("points") or 0)
            p = profile(author)
            p["published"].append({"skill": ref, "points": pts, "tier": q.get("tier"), "status": sk.get("status")})
            p["breakdown"]["published"] += pts
        for login, c in ((q.get("signals") or {}).get("runs_rep") or {}).items():
            if login == author:
                continue
            if c["class"] == "independent" and c["credited"]:
                pts = (
                    c["credited"] * ver["independent_run"]
                    + c["new_device_classes"] * ver["new_device_class"]
                    + c["new_bench_models"] * ver["new_bench_model"]
                )
                p = profile(login)
                p["verified"].append(
                    {
                        "skill": ref,
                        "points": pts,
                        "runs": c["credited"],
                        "new_device_classes": c["new_device_classes"],
                        "new_bench_models": c["new_bench_models"],
                    }
                )
                p["breakdown"]["verified"] += pts
            elif c["class"] in ("maintainer", "ci") and c["credited"]:
                p = profile(login)
                pts = mnt["per_skill"] + c["new_bench_models"] * ver["new_bench_model"]
                p["maintained"].append(
                    {"skill": ref, "points": pts, "runs": c["credited"], "new_bench_models": c["new_bench_models"]}
                )
                p["breakdown"]["maintained"] += pts

    for p in out.values():
        p["rep"] = sum(p["breakdown"].values())
        p["stats"] = {
            "published_skills": len(p["published"]),
            "verified_runs": sum(v["runs"] for v in p["verified"]),
            "verified_skills": len(p["verified"]),
            "new_device_classes": sum(v["new_device_classes"] for v in p["verified"]),
            "new_bench_models": sum(v["new_bench_models"] for v in p["verified"] + p["maintained"]),
            "maintained_skills": len(p["maintained"]),
        }
        p["badges"] = [b["id"] for b in rep["badges"] if badge_holds(b["rule"], p["stats"])]
    return dict(sorted(out.items()))
