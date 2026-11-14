"""Release/integration PRs skip the per-skill submission guard; skill PRs stay strict."""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((REPO / ".github/workflows/skill-submission.yml").read_text())
DETECT = WORKFLOW["jobs"]["detect"]


def _eval_expr(expr, event):
    """Evaluate the RELEASE_PR GitHub expression against an event, translated to Python."""
    body = re.fullmatch(r"\$\{\{(.*)\}\}", expr.strip()).group(1)
    ctx = {
        "github.event.pull_request.head.repo.full_name": repr(event["head_repo"]),
        "github.repository": repr(event["repo"]),
        "github.event.pull_request.head.ref": repr(event["head_ref"]),
        "github.event.pull_request.labels.*.name": repr(event["labels"]),
    }
    for name, value in sorted(ctx.items(), key=lambda kv: -len(kv[0])):
        body = body.replace(name, value)
    body = body.replace("&&", " and ").replace("||", " or ").replace("'", '"')
    body = re.sub(r"startsWith\(", "_starts(", body)
    body = re.sub(r"contains\(", "_contains(", body)
    assert re.fullmatch(r'[\s\w"\-/.,()=\[\]*]+', body), body  # nothing but the translated expression
    return eval(body, {"_starts": lambda s, p: s.startswith(p), "_contains": lambda xs, x: x in xs})


def _event(head_ref="feature", head_repo="org/repo", labels=()):
    return {"head_ref": head_ref, "head_repo": head_repo, "repo": "org/repo", "labels": list(labels)}


@pytest.mark.parametrize(
    ("event", "exempt"),
    [
        (_event("wrap/release-v16"), True),
        (_event("wrap/fable-base", labels=["release-merge"]), True),
        (_event("alice/new-skill"), False),
        (_event("alice/new-skill", labels=["skill-submission"]), False),
        (_event("wrap/release-v16", head_repo="mallory/repo"), False),  # fork cannot claim it by branch name
        (_event("x", head_repo="mallory/repo", labels=["release-merge"]), False),
        (_event("wrap/released-skill"), False),
    ],
)
def test_release_pr_expression(event, exempt):
    assert _eval_expr(DETECT["env"]["RELEASE_PR"], event) is exempt


def _changed_step():
    return next(s for s in DETECT["steps"] if s.get("id") == "changed")


def _run_changed(tmp_path, release):
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "python3").write_text(
        "#!/bin/sh\necho 'ValueError: PRs cannot edit generated registry files' >&2\nexit 1\n"
    )
    (stub / "python3").chmod(0o755)
    out = tmp_path / "out"
    out.write_text("")
    env = {
        "PATH": f"{stub}:/usr/bin:/bin",
        "GITHUB_OUTPUT": str(out),
        "RELEASE_PR": release,
        "BASE_SHA": "b",
        "HEAD_SHA": "h",
    }
    proc = subprocess.run(["bash", "-e", "-c", _changed_step()["run"]], env=env, capture_output=True, text=True)
    return proc, out.read_text()


def test_release_pr_detect_emits_zero_skills(tmp_path):
    proc, outputs = _run_changed(tmp_path, "true")
    assert proc.returncode == 0, proc.stderr
    assert 'matrix={"skill": []}' in outputs and "count=0" in outputs and "release=true" in outputs


def test_skill_pr_detect_still_runs_the_guard(tmp_path):
    proc, outputs = _run_changed(tmp_path, "false")
    assert proc.returncode != 0 and "count=" not in outputs and "release=true" not in outputs


def test_release_pr_skips_evidence_binding_and_emulator_proof_passes_on_zero():
    evidence = next(s for s in DETECT["steps"] if s.get("name") == "Authenticate independent verification artifacts")
    assert "steps.changed.outputs.release != 'true'" in evidence["if"]
    proof = yaml.safe_load((REPO / ".github/workflows/skill-emulator-run.yml").read_text())
    run = next(j for n, j in proof["jobs"].items() if j.get("name") == "skill-emulator-proof")["steps"][0]["run"]
    assert 'if [ "$COUNT" = 0 ]; then exit 0; fi' in run
