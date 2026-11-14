"""Static instruction and namespace checks shared by analyze, lint and submit."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from gitd.skills.engine.analyze import Finding

# Match agent redirection, not ordinary app instructions such as "send a message to Alice".
_INJECTION = re.compile(
    r"\bignore\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+(?:safety\s+)?(?:instructions?|rules?|prompts?)\b"
    r"|\byou\s+are\s+now\b"
    r"|\b(?:do\s+not|don[’\']t|never)\s+(?:tell|inform|notify)\s+(?:the\s+)?user\b"
    r"|\b(?:send|post|upload|forward|transmit|exfiltrate)\b[^\n.!?]{0,160}?\bto\s+https?://[^\s<>]+"
    r"|\b(?:send|post|upload|forward|transmit|exfiltrate)\b[^\n.!?]{0,80}\b(?:secrets?|credentials?|tokens?|private\s+keys?)\b[^\n.!?]{0,80}\bto\b[^\n]{0,80}"
    r"|<\s*(?:tool_call|function_call|tool_use|invoke)\b[^>]*>"
    r'|["\'](?:tool_calls?|function_call)["\']\s*:'
    r"|\b(?:functions|tools)\.[a-z_]\w*\s*\("
    r"|<!--.*?-->"
    r"|[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]"
    r"|(?<![\w+/=])[A-Za-z0-9+/=]{160,}(?![\w+/=])",
    re.I | re.S,
)


def read_manifest(root: Path) -> dict:
    source = root / "skill.yaml"
    if not source.is_file():
        return {}
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _text_nodes(node, active=False, seen=None):
    """Keep YAML line marks and decoded scalars (including escaped invisible characters)."""
    # Track ancestors only: an alias used as a prompt must still be scanned.
    seen = set() if seen is None else set(seen)
    if id(node) in seen:
        return
    seen.add(id(node))
    if isinstance(node, yaml.ScalarNode):
        if active:
            yield node.value, node.start_mark.line + 1
    elif isinstance(node, yaml.SequenceNode):
        for child in node.value:
            yield from _text_nodes(child, active, seen)
    elif isinstance(node, yaml.MappingNode):
        for key, child in node.value:
            field = key.value.lower()
            yield from _text_nodes(child, active or field == "description" or "prompt" in field, seen)


def _registry(root: Path) -> dict:
    # Local indexes only: static checks must never fetch a registry or execute submitted code.
    candidates = [p / "registry.json" for p in root.parents]
    candidates += [p / "skillhub" / "registry.json" for p in Path(__file__).resolve().parents]
    for candidate in candidates:
        if candidate.is_file():
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("skills"), dict):
                raise ValueError(f"Invalid skill registry: {candidate}")
            return raw["skills"]
    raise ValueError("A local skillhub/registry.json is required for namespace analysis")


def _distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def _confusable(value: str) -> str:
    return value.lower().replace("0", "o").replace("1", "l").replace("rn", "m").replace("-", "")


def content_findings(root: Path, raw: dict) -> list[Finding]:
    findings = []
    texts = []
    soft = root / "SOFT.md"
    if soft.is_file():
        texts.append(("SOFT.md", soft.read_text(encoding="utf-8"), 1))
    manifest = root / "skill.yaml"
    if manifest.is_file():
        texts.extend(
            ("skill.yaml", value, line)
            for value, line in _text_nodes(yaml.compose(manifest.read_text(encoding="utf-8")))
        )
    for filename, value, line in texts:
        for match in _INJECTION.finditer(value):
            span = match.group()
            # repr escapes hidden control characters rather than printing them to the terminal.
            findings.append(
                Finding(
                    filename,
                    line + value[: match.start()].count("\n"),
                    "high",
                    "soft-injection",
                    f"Agent instruction/hidden content: {span[:240]!r}",
                )
            )
    author, slug = raw.get("author"), raw.get("name")
    if not isinstance(author, str) or not isinstance(slug, str):
        return findings
    lineage = str(raw.get("forked_from", "")).split("@", 1)[0]
    for ref in sorted(_registry(root)):
        owner, separator, existing = ref.partition("/")
        if not separator or owner.lower() == author.lower() or ref == lineage:
            continue
        # Exact app names are valid in separate author namespaces; only deceptive near-names collide.
        if slug == existing:
            continue
        if _confusable(slug) == _confusable(existing) or 1 <= _distance(slug.lower(), existing.lower()) <= 2:
            findings.append(
                Finding(
                    "skill.yaml",
                    1,
                    "high",
                    "typosquat-slug",
                    f"{author}/{slug} resembles registered skill {ref}; declare forked_from for a fork",
                )
            )
    return findings
