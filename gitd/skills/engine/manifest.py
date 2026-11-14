"""Shipped-file manifest of a skill directory and its content digest.

ONE implementation for the registry (per-version ``files`` map and ``index[].sha256``) and for run
artifacts (``skill_sha256``), so "does this run belong to the code on disk" is a byte comparison.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

# Not shipped to installs: build junk, web-only demo media, run evidence, generated wrappers.
SKIP_NAMES = {"__pycache__", ".DS_Store", "demo.gif", "demo.mp4", "demo.webm"}
SKIP_TOP_DIRS = {"runs", "verifications", "demos", "bench"}
SKIP_ROOT_FILES = {"SKILL.md", "demo.spec.yaml"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def is_shipped(rel: PurePosixPath) -> bool:
    if len(rel.parts) > 1 and rel.parts[0] in SKIP_TOP_DIRS:
        return False
    if len(rel.parts) == 1 and rel.name in SKIP_ROOT_FILES:
        return False
    return not any(p in SKIP_NAMES or p.startswith(".") for p in rel.parts) and not rel.name.endswith(SKIP_SUFFIXES)


def shipped_files(skill_dir: Path) -> dict[str, bytes]:
    """``{relative posix path: bytes}`` of every file an install would receive."""
    out = {}
    for f in sorted(Path(skill_dir).rglob("*")):
        if f.is_file():
            rel = PurePosixPath(f.relative_to(skill_dir).as_posix())
            if is_shipped(rel):
                out[str(rel)] = f.read_bytes()
    return out


def file_hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {n: "sha256:" + hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}


def has_python_helpers(skill_dir: Path) -> bool:
    """Whether the shipped skill contains Python, without reading or executing helper code."""
    return any(
        path.is_file() and is_shipped(PurePosixPath(path.relative_to(skill_dir).as_posix()))
        for path in Path(skill_dir).rglob("*.py")
    )


def content_digest(files: dict[str, bytes] | dict[str, str]) -> str:
    """``sha256:<hex>`` over the sorted ``"<sha256:hash> <path>\\n"`` manifest lines (accepts bytes or hashes)."""
    hashes = file_hashes(files) if files and isinstance(next(iter(files.values())), (bytes, bytearray)) else dict(files)
    lines = "".join(f"{h} {n}\n" for n, h in sorted(hashes.items()))
    return "sha256:" + hashlib.sha256(lines.encode()).hexdigest()


# Presentation-only files: adding or replacing one cannot change what a skill does on a device.
COSMETIC_ROOT_FILES = ("icon.webp",)


def accepted_digests(files: dict[str, bytes] | dict[str, str]) -> set[str]:
    """Digests a run artifact may carry and still bind to ``files``: the exact digest, plus the digest
    without root cosmetic files, so adding an icon after recording does not orphan signed runs."""
    out = {content_digest(files)}
    stripped = {n: v for n, v in files.items() if n not in COSMETIC_ROOT_FILES}
    if len(stripped) != len(files):
        out.add(content_digest(stripped))
    return out


def skill_content_digest(skill_dir: Path) -> str:
    return content_digest(shipped_files(skill_dir))
