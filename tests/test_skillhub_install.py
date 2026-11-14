"""gitd/skills/hub.py install client (contract section 2). No network: file:// or a fake _fetch."""

import importlib.util
import json
from pathlib import Path

import pytest

from gitd.skills import hub
from gitd.skills.engine.context import RunContext
from gitd.skills.engine.dispatch import dispatch
from gitd.skills.engine.loader import load_skill
from gitd.skills.engine.pyimport import CTX_SKILL_KEY, ident_for_skill

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_test_tools_build_registry_i", REPO / "tools" / "build_registry.py")
build_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_registry)

YAML = """\
name: {slug}
version: {version}
author: {author}
description: "demo"
skill_class: hard
tos_risk: low
fingerprint: {{os: android, app_package: com.example}}
actions:
  - name: ping
    ref_prompt: "Ping the example application"
    steps: [{{python_action: "helpers:ping"}}]
    end_state_validator: [{{kind: text_visible, text: ok}}]
"""
HELPERS = 'def ping(device, params, context):\n    return {{"success": True, "data": {{"v": "{version}"}}}}\n'


def make(hub_dir: Path, author: str, slug: str, version: str) -> Path:
    d = hub_dir / author / slug
    (d / "data").mkdir(parents=True, exist_ok=True)
    (d / "skill.yaml").write_text(YAML.format(author=author, slug=slug, version=version))
    (d / "helpers.py").write_text(HELPERS.format(version=version))
    (d / "README.md").write_text("# demo\n")
    (d / "data" / "ref.txt").write_text("ref\n")
    return d


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A local hub repo checkout + an empty install root."""
    repo = tmp_path / "repo"
    hub_dir = repo / "skillhub"
    make(hub_dir, "ghost", "demo", "1.0.0")
    make(hub_dir, "alice", "foo", "0.1.0")
    installed = tmp_path / "installed"
    monkeypatch.setenv("GHOST_SKILLS_DIR", str(installed))
    monkeypatch.delenv("GHOST_HUB_REPO", raising=False)

    def write_registry():
        reg = build_registry.build_registry(hub_dir, now="2026-10-05T12:00:00Z")
        for entry in reg["skills"].values():  # tmp hub is not a git checkout: pin to a fake sha
            for vinfo in entry["versions"].values():
                vinfo["commit"] = "c0ffee"
        (hub_dir / "registry.json").write_text(json.dumps(reg))
        return reg

    reg = write_registry()
    return {"repo": repo, "hub": hub_dir, "installed": installed, "registry": reg, "rebuild": write_registry}


@pytest.fixture
def fake_cdn(env, monkeypatch):
    """Serve the local repo at jsDelivr URLs and release tarballs; record every URL requested."""
    seen = []
    fail_jsdelivr = {"on": False}
    releases = {}
    prefixes = (f"https://cdn.jsdelivr.net/gh/{hub.DEFAULT_HUB_REPO}@",)

    def fetch(url):
        seen.append(url)
        assert "raw.githubusercontent.com" not in url, "installs must never hit raw GitHub"
        if url in releases:
            return releases[url]
        if fail_jsdelivr["on"] and "jsdelivr" in url and not url.endswith("registry.json"):
            raise hub.HubError(f"fetch failed: {url}: 503")
        for p in prefixes:
            if url.startswith(p):
                rest = url[len(p) :]
                path = rest[rest.index("/skillhub/") + 1 :]  # rev may contain "/" (tags)
                f = env["repo"] / path
                if f.is_file():
                    return f.read_bytes()
        raise hub.HubError(f"fetch failed: {url}: 404")

    monkeypatch.setattr(hub, "_fetch", fetch)
    return {"seen": seen, "fail_jsdelivr": fail_jsdelivr, "releases": releases}


def _tarball(skill_dir: Path, prefix: str) -> bytes:
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for f in sorted(skill_dir.rglob("*")):
            if f.is_file():
                tf.add(f, arcname=prefix + f.relative_to(skill_dir).as_posix())
    return buf.getvalue()


def _never(_prompt):
    raise AssertionError("trust prompt must not be shown")


def test_official_install_from_hub_is_silent_and_verified(env, fake_cdn):
    got = hub.install("ghost/demo", confirm=_never)
    dest = env["installed"] / "ghost" / "demo" / "1.0.0"
    assert got.path == dest and got.trust == "official" and got.version == "1.0.0"
    assert (dest / "skill.yaml").is_file() and (dest / "data" / "ref.txt").is_file()
    assert got.rev == "c0ffee"  # latest is pinned to its commit too
    assert fake_cdn["seen"][0].endswith("@main/skillhub/registry.json")
    assert any(
        u.startswith("https://cdn.jsdelivr.net/gh/ghost-in-the-droid/android-agent@c0ffee/skillhub/ghost/demo/")
        for u in fake_cdn["seen"]
    )
    latest = env["installed"] / "ghost" / "demo" / "@latest"
    assert latest.is_symlink() or (env["installed"] / "ghost" / "demo" / "latest.txt").is_file()
    meta = json.loads((dest / hub.INSTALL_META).read_text())
    assert meta["trust"] == "official" and meta["version"] == "1.0.0"


def test_pinned_install_prefers_commit_then_tag(env, fake_cdn):
    reg = env["registry"]
    vinfo = reg["skills"]["ghost/demo"]["versions"]["1.0.0"]
    vinfo["tag"], vinfo["commit"] = "ghost/demo-v1.0.0", "abc123"
    assert hub.install("ghost/demo@1.0.0", registry=reg, confirm=_never).rev == "abc123"
    vinfo["commit"] = None
    assert hub.install("ghost/demo@1.0.0", registry=reg, confirm=_never, force=True).rev == "ghost/demo-v1.0.0"
    vinfo["tag"] = None
    with pytest.raises(hub.HubError, match="no commit or tag"):
        hub.install("ghost/demo@1.0.0", registry=reg, force=True)


@pytest.mark.parametrize("prefix", ["", "demo/", "./"])
def test_release_tarball_is_second_source(env, fake_cdn, prefix):
    reg = env["registry"]
    reg["skills"]["ghost/demo"]["versions"]["1.0.0"]["tag"] = "ghost/demo-v1.0.0"
    url = hub.release_asset_url("ghost/demo-v1.0.0", "ghost", "demo", "1.0.0")
    assert url == (
        "https://github.com/ghost-in-the-droid/android-agent/releases/download/"
        "ghost/demo-v1.0.0/ghost-demo-v1.0.0.tar.gz"
    )
    fake_cdn["releases"][url] = _tarball(env["hub"] / "ghost" / "demo", prefix)
    fake_cdn["fail_jsdelivr"]["on"] = True
    got = hub.install("ghost/demo@1.0.0", registry=reg, confirm=_never)
    assert (got.path / "data" / "ref.txt").read_text() == "ref\n"
    assert fake_cdn["seen"][-1] == url


def test_no_tag_no_release_fallback(env, fake_cdn):
    fake_cdn["fail_jsdelivr"]["on"] = True
    with pytest.raises(hub.HubError, match="503"):
        hub.install("ghost/demo")
    assert not any("releases/download" in u for u in fake_cdn["seen"])


def test_installed_skill_loads_and_runs_python(env, fake_cdn):
    hub.install("ghost/demo")
    skill = load_skill("ghost/demo")
    assert skill.skill_dir == env["installed"] / "ghost" / "demo" / "1.0.0"
    ctx = RunContext(action_name="ping")
    ctx.extras["_current_skill_dir"] = str(skill.skill_dir)
    ctx.extras[CTX_SKILL_KEY] = ident_for_skill(skill)
    dispatch({"python_action": "helpers:ping"}, ctx, None)
    assert ctx.result == {"v": "1.0.0"}


def test_verified_prints_note(env, fake_cdn, capsys):
    (env["hub"] / "REVIEWED").write_text("alice/foo C-K-Loan 0123456\n")  # v1.2: verified only after a recorded review
    reg = env["rebuild"]()
    assert reg["skills"]["alice/foo"]["trust"] == "verified"
    hub.install(
        "alice/foo", yes=True, registry=reg
    )  # alice/foo carries Python: the first install needs --yes (card + gate)
    assert "verified community skill by @alice" in capsys.readouterr().out


def test_unreviewed_community_skill_is_unverified_and_benchmark_installs_with_a_note(env, fake_cdn, capsys):
    assert env["registry"]["skills"]["alice/foo"]["trust"] == "unverified"
    reg = env["registry"]
    reg["skills"]["alice/foo"]["trust"] = "benchmark"
    hub.install("alice/foo", yes=True, registry=reg)
    assert "benchmark reference skill" in capsys.readouterr().out


def test_file_source_is_unverified_and_needs_yes(env):
    src = env["repo"].as_uri()
    with pytest.raises(hub.TrustDeclined):
        hub.install("ghost/demo", source=src, confirm=lambda _p: False)
    assert not (env["installed"] / "ghost" / "demo").exists()

    asked = []
    got = hub.install("ghost/demo", source=src, confirm=lambda p: asked.append(p) or True)
    assert asked and got.trust == "unverified"

    got = hub.install("ghost/demo", source=str(env["repo"]), yes=True, force=True)
    assert got.trust == "unverified" and got.source.startswith("file://")


def test_quarantined_needs_force(env, fake_cdn):
    reg = env["registry"]
    reg["skills"]["ghost/demo"]["trust"] = "quarantined"
    with pytest.raises(hub.TrustDeclined):
        hub.install("ghost/demo", registry=reg)
    assert hub.install("ghost/demo", registry=reg, force=True).trust == "quarantined"


def test_sha_mismatch_writes_nothing(env, fake_cdn):
    (env["hub"] / "ghost" / "demo" / "helpers.py").write_text("tampered = True\n")
    with pytest.raises(hub.HubError, match="sha256 mismatch"):
        hub.install("ghost/demo")
    assert not (env["installed"] / "ghost" / "demo" / "1.0.0").exists()


def test_unsafe_file_path_rejected(env, fake_cdn):
    reg = env["registry"]
    reg["skills"]["ghost/demo"]["versions"]["1.0.0"]["files"]["../../evil.py"] = "sha256:00"
    with pytest.raises(hub.HubError, match="unsafe"):
        hub.install("ghost/demo", registry=reg)


def test_unknown_skill_and_version(env, fake_cdn):
    with pytest.raises(hub.HubError, match="not in the registry"):
        hub.install("nobody/nothing")
    with pytest.raises(hub.HubError, match="available: 1.0.0"):
        hub.install("ghost/demo@9.9.9")


def test_already_installed_is_noop_unless_force(env, fake_cdn):
    first = hub.install("ghost/demo")
    marker = first.path / "local-edit.txt"
    marker.write_text("x")
    assert hub.install("ghost/demo").path == first.path and marker.exists()
    hub.install("ghost/demo", force=True)
    assert not marker.exists()


def test_list_outdated_update_uninstall(env, fake_cdn):
    hub.install("ghost/demo")
    hub.install("alice/foo", yes=True)
    assert [(s.key, s.version) for s in hub.list_installed()] == [("alice/foo", "0.1.0"), ("ghost/demo", "1.0.0")]
    assert hub.outdated() == []
    assert hub.update("ghost/demo") is None

    make(env["hub"], "ghost", "demo", "1.1.0")
    env["rebuild"]()
    assert hub.outdated() == [{"ref": "ghost/demo", "installed": "1.0.0", "latest": "1.1.0"}]
    got = hub.update("ghost/demo")
    assert got.version == "1.1.0"
    assert load_skill("ghost/demo").version == "1.1.0"  # @latest repointed
    assert load_skill("ghost/demo@1.0.0").version == "1.0.0"  # old version kept

    hub.uninstall("ghost/demo@1.1.0")
    assert load_skill("ghost/demo").version == "1.0.0"
    hub.uninstall("ghost/demo")
    assert not (env["installed"] / "ghost").exists()
    assert [s.key for s in hub.list_installed()] == ["alice/foo"]
    with pytest.raises(hub.HubError):
        hub.uninstall("ghost/demo")


def test_github_source_maps_to_jsdelivr_never_raw(monkeypatch):
    monkeypatch.delenv("GHOST_HUB_REPO", raising=False)
    assert (
        hub._normalize_source("https://github.com/bob/skills/tree/dev") == "https://cdn.jsdelivr.net/gh/bob/skills@dev"
    )
    assert hub._normalize_source("https://github.com/bob/skills.git") == "https://cdn.jsdelivr.net/gh/bob/skills@main"
    assert not hub._is_hub_source("https://raw.githubusercontent.com/bob/skills/main")
    assert hub._is_hub_source("https://raw.githubusercontent.com/ghost-in-the-droid/android-agent/main")
    with pytest.raises(hub.HubError):
        hub._normalize_source("ftp://x/y")


def test_destructive_skill_needs_acknowledgement(env, fake_cdn, capsys):
    reg = env["registry"]
    vinfo = reg["skills"]["ghost/demo"]["versions"]["1.0.0"]
    vinfo["destructive"], vinfo["side_effects"] = True, ["deletes_data"]
    with pytest.raises(hub.TrustDeclined, match="destructive"):
        hub.install("ghost/demo", registry=reg, confirm=lambda _p: False)
    assert "deletes_data" in capsys.readouterr().err
    assert not (env["installed"] / "ghost" / "demo").exists()
    assert hub.install("ghost/demo", registry=reg, yes=True).version == "1.0.0"


def test_v1_legacy_skill_is_refused_with_hint(env, fake_cdn):
    reg = env["registry"]
    reg["skills"]["ghost/demo"]["schema"] = "v1"
    with pytest.raises(hub.HubError, match="legacy v1 skill.*ghost skill migrate skillhub/ghost/demo"):
        hub.install("ghost/demo", registry=reg)
    assert not (env["installed"] / "ghost").exists()


def test_install_card_and_first_python_install_gate(env, fake_cdn, capsys):
    reg = env["registry"]
    entry = reg["skills"]["alice/foo"]
    entry["trust"] = "verified"
    vinfo = entry["versions"]["0.1.0"]
    vinfo["data_access"], vinfo["tos_risk"] = ["contacts"], "medium"
    assert vinfo["has_python"]
    with pytest.raises(hub.TrustDeclined, match="needs --yes"):
        hub.install("alice/foo", registry=reg, confirm=lambda _p: False)
    err = capsys.readouterr().err
    assert "Install card: alice/foo@0.1.0 (verified" in err
    assert "has_python:   yes" in err and "data_access:  contacts" in err and "tos_risk:     medium" in err
    assert "tested on:    * * *" in err and "runs 0/0 passed (0/0 independent)" in err
    assert not (env["installed"] / "alice" / "foo").exists()
    assert hub.install("alice/foo", registry=reg, confirm=lambda p: "Python" in p).version == "0.1.0"
    capsys.readouterr()
    # Already installed: a reinstall or upgrade asks nothing more.
    assert hub.install("alice/foo", registry=reg, force=True).version == "0.1.0"
    assert "Install card" in capsys.readouterr().err
    assert hub.install("alice/foo", registry=reg, yes=True, force=True).version == "0.1.0"


def test_official_installs_print_no_card(env, fake_cdn, capsys):
    hub.install("ghost/demo", registry=env["registry"])
    assert "Install card" not in capsys.readouterr().err


def test_unverified_python_install_is_asked_once_with_the_card(env, capsys):
    prompts = []

    def confirm(prompt):
        prompts.append(prompt)
        return True

    got = hub.install("ghost/demo", source=str(env["repo"]), confirm=confirm, force=True)
    assert got.trust == "unverified" and len(prompts) == 1 and "Continue?" in prompts[0]
    err = capsys.readouterr().err
    assert (
        "Install card: ghost/demo@1.0.0 (unverified" in err and err.index("Install card") < err.index("UNVERIFIED")
        if "UNVERIFIED" in err
        else True
    )


def test_is_hub_source_is_exact_not_prefix(monkeypatch):
    monkeypatch.delenv("GHOST_HUB_REPO", raising=False)
    repo = hub.DEFAULT_HUB_REPO
    assert hub._is_hub_source(f"https://cdn.jsdelivr.net/gh/{repo}@main")
    assert hub._is_hub_source(f"https://github.com/{repo}")
    assert not hub._is_hub_source(f"https://cdn.jsdelivr.net/gh/{repo}-fork@main")
    assert not hub._is_hub_source(hub._normalize_source(f"https://github.com/{repo}-fork"))
    assert not hub._is_hub_source(hub._normalize_source(f"https://github.com/{repo}/tree/dev"))


@pytest.mark.parametrize("evil", ["../../x", "/abs/escaped", "1.0.0/../../x", ".."])
def test_malicious_registry_version_is_rejected_and_writes_nothing(env, evil, tmp_path):
    reg = json.loads(json.dumps(env["registry"]))
    entry = reg["skills"]["ghost/demo"]
    entry["versions"][evil] = entry["versions"]["1.0.0"]
    entry["latest"] = evil
    with pytest.raises(hub.HubError):
        hub.install("ghost/demo", registry=reg, yes=True, force=True)
    assert not env["installed"].exists() or not any(env["installed"].rglob("*"))
    assert not (tmp_path / "x").exists() and not Path("/abs/escaped").exists()


def test_unknown_action_returns_param_error_not_keyerror(env, fake_cdn):
    from gitd.skills.engine.runner import _run_action, run_action

    hub.install("ghost/demo")
    skill = load_skill("ghost/demo")
    res = run_action(skill, "nosuch", {}, dry_run=True)
    assert not res.success and res.error["kind"] == "param_error" and "nosuch" in res.error["message"]
    res = _run_action(skill, "nosuch", {}, "", dry_run=True)
    assert not res.success and res.error["kind"] == "param_error"
