"""Scaffold placeholders cannot reach a PR: lint warns on leftover TODOs, submit refuses them unless the skill is a draft."""
from pathlib import Path

from gitd.skills.engine.cli import main as cli_main


def _scaffold(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli_main(["scaffold", "alice/notes-demo", "--app", "org.fossify.notes", "--actions", "add_note"]) == 0
    return tmp_path / "skillhub" / "alice" / "notes-demo"


def _fill_todos(skill_dir: Path):
    for name in ("skill.yaml", "SOFT.md", "README.md"):
        f = skill_dir / name
        f.write_text(f.read_text().replace("TODO", "done"))


def test_lint_warns_on_leftover_todos_and_is_quiet_once_filled(tmp_path, monkeypatch, capsys):
    skill_dir = _scaffold(tmp_path, monkeypatch)
    assert cli_main(["lint", str(skill_dir)]) == 0
    captured = capsys.readouterr()
    assert "leftover TODO" in captured.out + captured.err
    _fill_todos(skill_dir)
    cli_main(["lint", str(skill_dir)])
    captured = capsys.readouterr()
    assert "leftover TODO" not in captured.out + captured.err


def test_submit_allows_todos_on_a_declared_draft(tmp_path, monkeypatch):
    skill_dir = _scaffold(tmp_path, monkeypatch)
    y = skill_dir / "skill.yaml"
    text = y.read_text()
    y.write_text(text.replace("status: active", "status: draft", 1) if "status: active" in text else text + "\nstatus: draft\n")
    assert cli_main(["submit", str(skill_dir), "--dry-run"]) == 0


def test_submit_refuses_leftover_todos(tmp_path, monkeypatch, capsys):
    skill_dir = _scaffold(tmp_path, monkeypatch)
    assert cli_main(["submit", str(skill_dir), "--dry-run"]) == 1
    captured = capsys.readouterr()
    assert "Leftover TODO" in captured.out + captured.err
    _fill_todos(skill_dir)
    assert cli_main(["submit", str(skill_dir), "--dry-run"]) == 0
