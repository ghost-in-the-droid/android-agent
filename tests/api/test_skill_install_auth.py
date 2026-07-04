"""Regression tests for CWE-94 in POST /api/skills/install.

The endpoint used to be reachable without any authentication and fed the
attacker-supplied ``url`` directly into ``git clone``.  Combined with the
subsequent ``importlib.import_module`` in ``_load_skill`` that was a
drive-by RCE.  These tests lock in the fix:

* the endpoint refuses to run when ``GITD_ADMIN_TOKEN`` is unset,
* it refuses invalid tokens,
* it rejects URLs that don't match a strict shape *before* invoking git
  (so ``--upload-pack=...``, whitespace-smuggled shell payloads, and
  hostnames like ``github.com.evil.example.com`` never reach the sink),
* the intended admin flow still works with a valid token via either
  ``X-Ghost-Admin-Token`` or ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """Fresh TestClient with a clean env for each case."""
    monkeypatch.delenv("GITD_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("GITD_ALLOW_UNAUTHENTICATED_ADMIN", raising=False)

    from gitd.app import app  # imported after env is scrubbed

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def no_git(monkeypatch):
    """Explode if the router ever lets ``git clone`` execute during a test."""
    calls: list[list[str]] = []
    real_run = subprocess.run

    def guarded_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "git":
            calls.append(list(cmd))
            raise AssertionError(f"git reached with attacker input: {cmd!r}")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)
    return calls


# ── The drive-by CVE cases ────────────────────────────────────────────


def test_unauthenticated_url_install_is_rejected(client, no_git):
    """No token configured → refuse and never call git."""
    r = client.post(
        "/api/skills/install",
        json={"url": "github.com/attacker/malicious-skill"},
    )
    assert r.status_code in (401, 403), r.text
    assert no_git == []


def test_unauthenticated_registry_install_is_rejected(client, no_git):
    r = client.post(
        "/api/skills/install",
        json={"name": "some_registry_skill"},
    )
    assert r.status_code in (401, 403), r.text


def test_wrong_token_is_rejected(client, no_git, monkeypatch):
    monkeypatch.setenv("GITD_ADMIN_TOKEN", "s3cret")
    r = client.post(
        "/api/skills/install",
        headers={"X-Ghost-Admin-Token": "not-the-token"},
        json={"url": "github.com/attacker/malicious-skill"},
    )
    assert r.status_code in (401, 403), r.text
    assert no_git == []


def test_flag_injection_url_is_rejected(client, no_git, monkeypatch):
    """``--upload-pack=<cmd>`` smuggling must be caught before git runs."""
    monkeypatch.setenv("GITD_ADMIN_TOKEN", "s3cret")
    r = client.post(
        "/api/skills/install",
        headers={"X-Ghost-Admin-Token": "s3cret"},
        json={"url": "--upload-pack=touch /tmp/pwned github.com/x/y"},
    )
    assert r.status_code == 400, r.text
    assert no_git == []


def test_whitespace_smuggling_url_is_rejected(client, no_git, monkeypatch):
    monkeypatch.setenv("GITD_ADMIN_TOKEN", "s3cret")
    r = client.post(
        "/api/skills/install",
        headers={"X-Ghost-Admin-Token": "s3cret"},
        json={"url": "github.com/foo/bar\nrm -rf /"},
    )
    assert r.status_code == 400, r.text
    assert no_git == []


def test_lookalike_hostname_is_rejected(client, no_git, monkeypatch):
    """``github.com.evil.example.com`` used to pass the substring check."""
    monkeypatch.setenv("GITD_ADMIN_TOKEN", "s3cret")
    r = client.post(
        "/api/skills/install",
        headers={"X-Ghost-Admin-Token": "s3cret"},
        json={"url": "https://github.com.evil.example.com/foo/bar"},
    )
    # Either rejected as bad shape (400) or as "not a github URL"; the
    # important thing is that no clone ran.
    assert r.status_code in (400, 401), r.text
    assert no_git == []


# ── The legitimate admin flow still works ─────────────────────────────


def test_valid_token_via_header_reaches_install(client, monkeypatch, tmp_path):
    monkeypatch.setenv("GITD_ADMIN_TOKEN", "s3cret")

    from gitd import cli as cli_module

    fake_source = tmp_path / "fake_skill"
    fake_source.mkdir()
    (fake_source / "skill.yaml").write_text(
        "name: fake\ndisplay_name: fake\ndescription: x\nversion: 1.0.0\napp_package: com.example\nauthor: tester\n"
    )

    monkeypatch.setattr(cli_module, "_clone_github_skill", lambda u: fake_source)
    monkeypatch.setattr(cli_module, "_install_to_skills_dir", lambda s, name=None: True)
    monkeypatch.setattr(cli_module, "_validate_skill_dir", lambda s, verbose=True: True)

    r = client.post(
        "/api/skills/install",
        headers={"X-Ghost-Admin-Token": "s3cret"},
        json={"url": "github.com/legit/skill"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True


def test_valid_token_via_bearer_header_reaches_install(client, monkeypatch, tmp_path):
    monkeypatch.setenv("GITD_ADMIN_TOKEN", "s3cret")

    from gitd import cli as cli_module

    fake_source = tmp_path / "fake_skill"
    fake_source.mkdir()
    (fake_source / "skill.yaml").write_text(
        "name: fake\ndisplay_name: fake\ndescription: x\nversion: 1.0.0\napp_package: com.example\nauthor: tester\n"
    )

    monkeypatch.setattr(cli_module, "_clone_github_skill", lambda u: fake_source)
    monkeypatch.setattr(cli_module, "_install_to_skills_dir", lambda s, name=None: True)
    monkeypatch.setattr(cli_module, "_validate_skill_dir", lambda s, verbose=True: True)

    r = client.post(
        "/api/skills/install",
        headers={"Authorization": "Bearer s3cret"},
        json={"url": "github.com/legit/skill"},
    )
    assert r.status_code == 200, r.text
