"""scripts/privacy/scan_forbidden.py: the CI forbidden-pattern scan skips only public-strip paths."""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from privacy.scan_forbidden import is_stripped, load_strip_paths, scan  # noqa: E402

PATTERNS = [("re:token-[0-9]+", re.compile(r"token-[0-9]+"))]


def _repo(tmp_path, files, strip="docs/reports/\ndocs/private.md\n"):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/public-strip.txt").write_text("# comment\n" + strip)
    for rel, text in files.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    return tmp_path


def test_hits_in_stripped_paths_are_skipped_and_others_fail(tmp_path):
    repo = _repo(
        tmp_path,
        {
            "docs/reports/run.md": "token-1",
            "docs/private.md": "token-2",
            "docs/private.md.bak.md": "token-3",
            "docs/reports-public.md": "token-4",
            "gitd/app.py": "x = 'token-5'",
        },
    )
    hits, skipped = scan(repo, PATTERNS)
    assert sorted(h[0] for h in hits) == ["docs/private.md.bak.md", "docs/reports-public.md", "gitd/app.py"]
    assert skipped == 3  # two stripped docs plus the strip list itself


def test_strip_semantics_match_release_sh():
    # Directories end with "/" and match by prefix; files match exactly.
    assert is_stripped("docs/reports/a/b.md", ["docs/reports/"])
    assert not is_stripped("docs/reportsx.md", ["docs/reports/"])
    assert is_stripped("docs/HUMAN.md", ["docs/HUMAN.md"]) and not is_stripped("docs/HUMAN.md.x", ["docs/HUMAN.md"])


def test_kept_file_inside_stripped_directory_is_scanned():
    assert not is_stripped("docs/reports/kept.md", ["docs/reports/", "!docs/reports/kept.md"])
    assert is_stripped("docs/reports/other.md", ["docs/reports/", "!docs/reports/kept.md"])


def test_repo_strip_list_loads_and_tree_is_clean():
    if (REPO / "scripts/public-strip.txt").exists():
        assert "docs/reports/" in load_strip_paths(REPO)
    hits, _ = scan(REPO)
    assert hits == [], hits


def test_privacy_workflow_runs_the_script():
    assert "python3 scripts/privacy/scan_forbidden.py" in (REPO / ".github/workflows/privacy.yml").read_text()
