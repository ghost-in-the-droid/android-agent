"""Intent search over skill actions: BM25 on name, description, ref prompts and app package.

Pure functions, no network, no new dependencies. A corpus document is one (skill, action)
pair; sources are flat skill dirs (what the MCP server can run), installed hub skills and
the published registry (which carries per-action prompts since schema v2.1).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "in",
    "on",
    "for",
    "and",
    "or",
    "my",
    "me",
    "i",
    "it",
    "with",
    "please",
    "can",
    "you",
}
K1, B = 1.2, 0.75


@dataclass
class Doc:
    skill: str  # ref (author/slug) or flat dir name, as the caller can address it
    action: str
    source: str  # installed | checkout | hub | flat
    text: str
    prompt: str = ""
    app_package: str = ""
    params: list[str] = field(default_factory=list)
    description: str = ""
    tokens: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self):
        if not self.tokens:
            self.tokens = tokenize(self.text)


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens; ``{param}`` placeholders and stop words drop out."""
    cleaned = re.sub(r"\{[^}]*\}", " ", text or "")
    return [t for t in _TOKEN.findall(cleaned.casefold()) if t not in _STOP]


def _texts(raw: dict, action: dict) -> tuple[str, str, list[str]]:
    prompt = str(action.get("ref_prompt") or "").strip()
    variants = [str(v) for v in ((action.get("test_case") or {}).get("ref_prompt_variants") or []) if v]
    parts = [
        str(raw.get("name") or ""),
        str(raw.get("description") or ""),
        str(action.get("name") or "").replace("_", " "),
        str(action.get("description") or ""),
        prompt,
        *variants,
    ]
    fp = raw.get("fingerprint") or {}
    package = str((fp if isinstance(fp, dict) else {}).get("app_package") or raw.get("app_package") or "")
    if package:
        parts.append(package.replace(".", " "))
    parts += [str(p).replace(".", " ") for p in ((fp if isinstance(fp, dict) else {}).get("apps") or [])]
    return " ".join(parts), package, [prompt, *variants]


def docs_from_skill_yaml(skill: str, raw: dict, source: str) -> list[Doc]:
    """One document per v2 action of a parsed skill.yaml; v1 skills yield nothing."""
    actions = raw.get("actions") if isinstance(raw.get("actions"), list) else []
    docs = []
    for action in actions:
        if not isinstance(action, dict) or not action.get("name"):
            continue
        text, package, prompts = _texts(raw, action)
        params = [str(p.get("name")) for p in (action.get("params") or []) if isinstance(p, dict) and p.get("name")]
        docs.append(
            Doc(
                skill,
                str(action["name"]),
                source,
                text,
                prompt=prompts[0],
                app_package=package,
                params=params,
                description=str(action.get("description") or ""),
            )
        )
    return docs


def docs_from_dirs(dirs: list[tuple[str, Path]], source: str) -> list[Doc]:
    """``(skill ref or name, dir)`` pairs -> documents; unreadable skill.yaml files are skipped."""
    docs = []
    for skill, directory in dirs:
        try:
            raw = yaml.safe_load((directory / "skill.yaml").read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(raw, dict):
            docs.extend(docs_from_skill_yaml(skill, raw, source))
    return docs


def docs_from_registry(registry: dict, exclude: set[str] = frozenset()) -> list[Doc]:
    """Documents for hub skills not in ``exclude``; uses ``prompts`` when the registry carries them."""
    docs = []
    for ref, entry in (registry.get("skills") or {}).items():
        if ref in exclude or (entry.get("status") or "active") in {"blocked", "deprecated", "draft"}:
            continue
        version = (entry.get("versions") or {}).get(entry.get("latest") or "", {})
        package = str((version.get("fingerprint") or {}).get("app_package") or "")
        prompts = version.get("prompts") if isinstance(version.get("prompts"), dict) else {}
        for action in version.get("actions") or []:
            action_prompts = [str(p) for p in (prompts.get(action) or []) if p]
            text = " ".join(
                [
                    str(entry.get("name") or ""),
                    str(entry.get("description") or ""),
                    str(action).replace("_", " "),
                    *action_prompts,
                    package.replace(".", " "),
                ]
            )
            docs.append(
                Doc(
                    ref,
                    str(action),
                    "hub",
                    text,
                    prompt=action_prompts[0] if action_prompts else "",
                    app_package=package,
                    description=str(entry.get("description") or ""),
                )
            )
    return docs


def rank(intent: str, docs: list[Doc], top: int = 5) -> list[tuple[float, Doc]]:
    """BM25 (k1=1.2, b=0.75) over the corpus; ties break on skill then action for stable output."""
    query = tokenize(intent)
    if not query or not docs:
        return []
    n = len(docs)
    avgdl = sum(len(d.tokens) for d in docs) / n
    df: Counter = Counter()
    for d in docs:
        df.update(set(d.tokens))
    scored = []
    for d in docs:
        tf = Counter(d.tokens)
        score = 0.0
        for term in query:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            score += idf * freq * (K1 + 1) / (freq + K1 * (1 - B + B * len(d.tokens) / avgdl))
        if score > 0:
            scored.append((round(score, 4), d))
    scored.sort(key=lambda item: (-item[0], item[1].skill, item[1].action))
    return scored[:top]


def as_dict(score: float, doc: Doc) -> dict:
    return {
        "skill": doc.skill,
        "action": doc.action,
        "source": doc.source,
        "score": score,
        "prompt": doc.prompt,
        "params": doc.params,
        "app_package": doc.app_package,
        "description": doc.description,
    }


def installed_hub_dirs() -> list[tuple[str, Path]]:
    """``(author/slug, dir)`` for every hub skill under ``$GHOST_SKILLS_DIR`` (``@latest`` or newest version)."""
    from gitd.skills.locations import installed_skills_dir

    out = []
    root = installed_skills_dir()
    if not root.is_dir():
        return out
    for author in sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))):
        for slug in sorted(d for d in author.iterdir() if d.is_dir()):
            latest = slug / "@latest"
            if not latest.exists():
                versions = sorted(d for d in slug.iterdir() if d.is_dir() and (d / "skill.yaml").is_file())
                latest = versions[-1] if versions else None
            if latest is not None and (latest / "skill.yaml").is_file():
                out.append((f"{author.name}/{slug.name}", latest))
    return out


def skill_notes(name: str) -> str:
    """SOFT.md reference notes of a flat skill (bare name) or an installed hub skill (author/slug)."""
    from gitd.skills.locations import find_legacy_skill_dir

    skill_dir = find_legacy_skill_dir(name) or dict(installed_hub_dirs()).get(name)
    soft = skill_dir / "SOFT.md" if skill_dir else None
    return soft.read_text(encoding="utf-8") if soft and soft.is_file() else f"No SOFT.md notes for {name}"


def find_installed(intent: str, top: int = 5) -> list[dict]:
    """Ranked hits over everything ``run_skill`` can run: the flat skill dirs (source ``flat``, run by
    name) and the installed hub skills (source ``hub``, run by ``author/slug``)."""
    from gitd.skills.locations import iter_legacy_skill_dirs

    docs = docs_from_dirs([(d.name, d) for d in iter_legacy_skill_dirs()], "flat")
    docs += docs_from_dirs(installed_hub_dirs(), "hub")
    return [as_dict(score, doc) for score, doc in rank(intent, docs, max(1, min(int(top), 20)))]
