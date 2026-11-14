"""Published login declarations must remain probeable and distinct from demo evidence."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gitd.skills.engine.loader import load_skill
from gitd.skills.engine.state import probe_state

HUB = Path(__file__).resolve().parents[1] / "skillhub"
PREMIUM = Path(__file__).resolve().parents[1] / "premium" / "skills" / "ghost"
needs_premium = pytest.mark.skipif(not PREMIUM.is_dir(), reason="premium skills are not part of the public tree")


def signup_dir():
    return next(
        p.parent
        for p in PREMIUM.glob("*signup/skill.yaml")
        if any(a["name"] == "register" for a in yaml.safe_load(p.read_text())["actions"])
    )


@pytest.mark.parametrize(
    "kind", [pytest.param("signup", marks=needs_premium), "tiktok", "play_store", "send_gmail_email"]
)
def test_published_login_probe_requires_positive_visible_evidence(kind):
    path = signup_dir() if kind == "signup" else HUB / "ghost" / kind
    skill = load_skill(path)
    spec = skill.state_probes["logged_in"]
    key = "desc" if "desc" in spec else "text"
    attr = "content-desc" if key == "desc" else "text"
    from xml.sax.saxutils import quoteattr

    xml = f"<hierarchy><node {attr}={quoteattr(spec[key])}/></hierarchy>"
    assert probe_state(skill, "logged_in", SimpleNamespace(dump_xml=lambda: xml)) is True
    assert (
        probe_state(
            skill, "logged_in", SimpleNamespace(dump_xml=lambda: '<hierarchy><node text="Sign in"/></hierarchy>')
        )
        is False
    )
    assert probe_state(skill, "logged_in", SimpleNamespace(dump_xml=lambda: "")) is None


@needs_premium
def test_premium_signup_registers_without_requiring_login():
    signup = load_skill(signup_dir())
    assert signup.action("register").provides_state == ["logged_in"]
    assert signup.action("register").requires_state == []


def test_only_account_dependent_actions_require_login():
    assert all(a.requires_state == ["logged_in"] for a in load_skill(HUB / "ghost/tiktok").actions)
    assert load_skill(HUB / "ghost/send_gmail_email").action("recorded").requires_state == ["logged_in"]
    store = load_skill(HUB / "ghost/play_store")
    assert {a.name for a in store.actions if a.requires_state == ["logged_in"]} == {
        "install_by_name",
        "search_app",
        "install_app",
        "update_app",
    }
    assert all(not a.requires_state for a in load_skill(HUB / "ghost/calculator").actions)


@needs_premium
def test_signup_note_is_unscored():
    path = signup_dir()
    note = (path / "README.md").read_text()
    assert "human-assisted captcha demo, not a replay" in note
    assert not list((path / "runs").glob("*.json"))
