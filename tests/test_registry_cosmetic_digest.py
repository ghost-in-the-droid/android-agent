"""A presentation-only icon added after recording must not orphan signed runs; any other file change must."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from build_registry import _is_current  # noqa: E402

from gitd.skills.engine.manifest import accepted_digests, content_digest  # noqa: E402

FILES = {"skill.yaml": b"name: x\n", "helpers.py": b"def f():\n    return 1\n", "README.md": b"# X\n"}


def _run(files):
    return {"version": "1.0.0", "skill_sha256": content_digest(files)}


def test_run_recorded_before_icon_still_binds_after_icon_added():
    with_icon = {**FILES, "icon.webp": b"RIFF....WEBP"}
    assert _is_current(_run(FILES), "1.0.0", accepted_digests(with_icon))


def test_run_recorded_with_icon_binds_exactly():
    with_icon = {**FILES, "icon.webp": b"RIFF....WEBP"}
    assert _is_current(_run(with_icon), "1.0.0", accepted_digests(with_icon))


def test_any_behavioural_change_still_unbinds():
    changed = {**FILES, "helpers.py": b"def f():\n    return 2\n", "icon.webp": b"RIFF....WEBP"}
    assert not _is_current(_run(FILES), "1.0.0", accepted_digests(changed))


def test_nested_icon_is_not_cosmetic():
    nested = {**FILES, "assets/icon.webp": b"RIFF....WEBP"}
    assert not _is_current(_run(FILES), "1.0.0", accepted_digests(nested))


def test_plain_string_digest_still_supported():
    assert _is_current(_run(FILES), "1.0.0", content_digest(FILES))
    assert not _is_current(_run(FILES), "1.0.0", "sha256:" + "0" * 64)
