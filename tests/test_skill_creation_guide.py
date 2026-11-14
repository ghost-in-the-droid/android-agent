"""The skill creation guide ships in three places that must stay identical, and the
agent-loadable copy under skillhub/_guides must never be treated as a skill."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "SKILL_CREATION_GUIDE.md"
SKILL_MD = ROOT / "skillhub" / "_guides" / "skill-creation-guide" / "SKILL.md"
SITE = ROOT / "site" / "src" / "content" / "docs" / "skills" / "skill-creation-guide.md"


def _split_frontmatter(text):
    assert text.startswith("---\n")
    _, fm, body = text.split("---\n", 2)
    return fm, body


def test_agent_skill_md_matches_guide():
    fm, body = _split_frontmatter(SKILL_MD.read_text())
    assert "name: ghost-skill-creation-guide" in fm
    assert "description:" in fm
    assert body.lstrip("\n") == GUIDE.read_text()


def test_site_page_matches_guide_without_h1():
    fm, body = _split_frontmatter(SITE.read_text())
    assert "title:" in fm and "description:" in fm
    guide = GUIDE.read_text()
    assert guide.startswith("# ")
    assert body.lstrip("\n") == guide.split("\n", 2)[2]


def test_guide_quotes_scoring_v1_numbers():
    scoring = json.loads((ROOT / "skillhub" / "scoring" / "v1.json").read_text())
    text = GUIDE.read_text()
    for tier in scoring["tiers"]:
        assert f"| {tier['id'].capitalize()} | {tier['points']} |" in text
    for name, cat in scoring["categories"].items():
        assert f"({cat['cap']})" in text, name


def test_registry_builder_ignores_guides(tmp_path):
    hub = tmp_path / "skillhub"
    guide = hub / "_guides" / "skill-creation-guide"
    guide.mkdir(parents=True)
    (guide / "SKILL.md").write_text(SKILL_MD.read_text())
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_registry.py"), str(hub), "--no-write"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    registry = json.loads(out.stdout)
    assert "_guides" not in registry.get("authors", {})
    assert not any(key.startswith("_guides/") for key in registry.get("skills", {}))
