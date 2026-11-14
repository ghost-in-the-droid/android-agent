"""Skill reference syntax: ``<author>/<slug>[@<version>]``.

``@latest`` is the default. ``@main`` is allowed (tracks the hub repo's main
branch) and callers should warn when it is used. Anything else must be SemVer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LATEST = "latest"
MAIN = "main"

_SEG = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"
_REF_RE = re.compile(rf"^(?P<author>{_SEG})/(?P<slug>{_SEG})(?:@(?P<version>[A-Za-z0-9_.+-]+))?$")
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class SkillRef:
    author: str
    slug: str
    version: str = LATEST

    @property
    def key(self) -> str:
        """Registry key, ``<author>/<slug>``."""
        return f"{self.author}/{self.slug}"

    @property
    def pinned(self) -> bool:
        return self.version not in (LATEST, MAIN)

    def __str__(self) -> str:
        return f"{self.key}@{self.version}"


def is_ref(text: str) -> bool:
    return bool(_REF_RE.match(text or ""))


def parse_ref(text: str) -> SkillRef:
    """Parse ``author/slug[@version]``. Author and slug are lower-cased (GitHub handles are case-insensitive).

    Raises ValueError on malformed input or a version that is not latest/main/SemVer.
    """
    m = _REF_RE.match(text or "")
    if not m:
        raise ValueError(f"invalid skill ref {text!r}: expected <author>/<slug>[@<version>]")
    author, slug = m.group("author").lower(), m.group("slug").lower()
    if author in (".", "..") or slug in (".", ".."):
        raise ValueError(f"invalid skill ref {text!r}")
    version = m.group("version") or LATEST
    if version not in (LATEST, MAIN) and not _SEMVER_RE.match(version):
        raise ValueError(f"invalid version {version!r} in {text!r}: expected latest, main or SemVer")
    return SkillRef(author, slug, version)


def is_semver(version: str) -> bool:
    return bool(_SEMVER_RE.match(version or ""))


def version_key(version: str) -> tuple:
    """Sort key for SemVer strings. Pre-releases sort before the release; non-SemVer sorts first."""
    m = _SEMVER_RE.match(version or "")
    if not m:
        return (-1, -1, -1, 0, ())
    major, minor, patch, pre = m.groups()
    if pre is None:
        return (int(major), int(minor), int(patch), 1, ())
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return (int(major), int(minor), int(patch), 0, parts)


def max_version(versions) -> str | None:
    vs = [v for v in versions if is_semver(v)]
    return max(vs, key=version_key) if vs else None
