"""Docs say only what the code does: every documented `ghost skill <sub>` exists, counts match the registries,
approval labels use the enforced name, and unbuilt features are marked planned."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOC_ROOTS = ["docs", "site/src/content", "skillhub/_guides", "README.md", "CONTRIBUTING.md", "CHANGELOG.md"]
# Historical records and research notes describe what happened or what others do, not the shipped CLI.
EXCLUDED_DIRS = ("docs/reports/", "docs/research/", "docs/HUMAN/", "docs/community/archive/")
PLANNED_MARKERS = ("planned", "not implemented", "not in v1.6.0", "v1.7", "proposed", "designed, not yet", "will ")
SUB_RE = re.compile(r"`?ghost skill ([a-z][a-z-]*)\b")
PLACEHOLDERS = {"subcommands", "subcommand", "sub", "command", "commands"}


def doc_files() -> list[Path]:
    out: list[Path] = []
    for root in DOC_ROOTS:
        p = REPO / root
        if p.is_file():
            out.append(p)
            continue
        out += [f for f in p.rglob("*") if f.suffix in (".md", ".mdx", ".html")]
    return sorted(f for f in out if not any(x in f.as_posix() for x in EXCLUDED_DIRS))


def lines_with_heading(path: Path):
    heading = ""
    for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if line.startswith("#"):
            heading = line
        yield n, line, heading


def is_planned(line: str, heading: str) -> bool:
    text = (line + " " + heading).lower()
    return any(m in text for m in PLANNED_MARKERS)


def file_is_planned(path: Path) -> bool:
    """A design doc announces itself as planned in its first lines (after any frontmatter)."""
    head = "\n".join(path.read_text(errors="replace").splitlines()[:15]).lower()
    return any(m in head for m in ("planned", "deferred")) and any(
        m in head for m in ("not implemented", "design", "not shipping")
    )


def real_subcommands() -> set[str]:
    from gitd.skills.engine import cli

    return set(cli._SUBCOMMANDS)


def test_every_documented_subcommand_exists_or_is_marked_planned():
    real = real_subcommands()
    bad = []
    for f in doc_files():
        if file_is_planned(f):
            continue
        for n, line, heading in lines_with_heading(f):
            for m in SUB_RE.finditer(line):
                sub = m.group(1)
                if sub in real or sub == "resume" or sub in PLACEHOLDERS:
                    continue
                if is_planned(line, heading):
                    continue
                bad.append(f"{f.relative_to(REPO)}:{n}: `ghost skill {sub}` ({line.strip()[:90]})")
    assert not bad, "documented subcommands that do not exist and are not marked planned:\n" + "\n".join(bad)


def test_unbuilt_commands_are_not_claimed_in_shipped_sections():
    # These do not exist in v1.6.0; every mention must sit on a planned line or under a planned heading.
    real = real_subcommands()
    for sub in ("mine",):
        assert sub not in real, f"`ghost skill {sub}` now exists; drop it from this list and update the docs"
    assert "find" in real  # shipped 2026-10-20; docs may present it as shipped
    assert "bench" in real  # shipped 2026-10-20 (AndroidWorld replay arm); agent arms stay planned
    bad = []
    for f in doc_files():
        if file_is_planned(f):
            continue
        for n, line, heading in lines_with_heading(f):
            if re.search(r"ghost skill (mine)\b", line) and not is_planned(line, heading):
                bad.append(f"{f.relative_to(REPO)}:{n}")
    assert not bad, "unbuilt commands presented as shipped:\n" + "\n".join(bad)


def test_fingerprint_distance_docs_match_the_shipped_flags():
    """Distance matching shipped (engine/fingerprint.py): the flags the docs name must exist, and no doc may still call it unimplemented."""
    cli_text = (REPO / "gitd/skills/engine/cli.py").read_text()
    assert (
        "--strict-fingerprint" in cli_text
        and "--force-fingerprint" in cli_text
        and "--no-fingerprint-check" in cli_text
    )
    bad = []
    for f in doc_files():
        for n, line, heading in lines_with_heading(f):
            if "--strict-fingerprint" in line and "not implemented" in line and "Adapt" not in line:
                bad.append(f"{f.relative_to(REPO)}:{n}")
            if "fingerprint distance" in line and "not implemented" in line and "Adapt" not in line:
                bad.append(f"{f.relative_to(REPO)}:{n}")
    assert not bad, "fingerprint distance still described as unimplemented:\n" + "\n".join(bad)


def test_approval_label_name_matches_review_guard():
    review_guard = pytest.importorskip(
        "tools.ci.review_guard"
    )  # lands with the Phase 2 security PR; absent on branches before it

    assert "'approved:'" in Path(review_guard.__file__).read_text()
    bad = [
        f"{f.relative_to(REPO)}:{n}"
        for f in doc_files()
        for n, line, _ in lines_with_heading(f)
        if "security-approved" in line and not any(w in line.lower() for w in ("legacy", "stale", "comment"))
    ]
    assert not bad, "docs still use the old `security-approved` label name:\n" + "\n".join(bad)


def test_step_and_validator_counts_match_the_registries():
    from gitd.skills.engine import dispatch, validators

    steps, kinds = len(dispatch._HANDLERS), len(validators._VALIDATORS)
    bad = []
    for f in doc_files():
        for n, line, _ in lines_with_heading(f):
            for m in re.finditer(r"\b(\d+) step kinds\b", line):
                if int(m.group(1)) != steps:
                    bad.append(f"{f.relative_to(REPO)}:{n}: says {m.group(1)} step kinds, registry has {steps}")
            for m in re.finditer(r"\b(\d+) validator kinds\b", line):
                if int(m.group(1)) != kinds:
                    bad.append(f"{f.relative_to(REPO)}:{n}: says {m.group(1)} validator kinds, registry has {kinds}")
            # Counts under another name drift unnoticed; only the canonical phrasing is allowed.
            if re.search(r"\b\d+ (step types|step primitives|validator primitives|validators)\b", line):
                bad.append(f"{f.relative_to(REPO)}:{n}: use 'N step kinds' / 'N validator kinds' ({line.strip()[:80]})")
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("stale", ["registry/index.json", "registry/community.json", "trust_tier"])
def test_retired_names_are_gone(stale):
    bad = [f"{f.relative_to(REPO)}:{n}" for f in doc_files() for n, line, _ in lines_with_heading(f) if stale in line]
    assert not bad, f"retired name {stale!r} still in docs:\n" + "\n".join(bad)


def registered_mcp_tools() -> list[str]:
    text = (REPO / "gitd" / "mcp_server.py").read_text()
    return re.findall(r"^@mcp\.tool\(\)\s*\n(?:async )?def (\w+)", text, re.M)


def test_documented_mcp_tool_count_matches_the_server():
    tools = registered_mcp_tools()
    n = len(tools)
    assert n == len(set(tools)) and n > 0
    stale = []
    for f in doc_files() + [REPO / "site/src/pages/index.astro"]:
        if "release-notes" in f.as_posix() or f.name == "CHANGELOG.md":  # history says what was true then
            continue
        for ln, line, _ in lines_with_heading(f):
            for m in re.finditer(r"\b(\d{2,3}) (?:MCP |mobile )?tools\b", line):
                if 30 <= int(m.group(1)) != n and "(" not in line[m.end() : m.end() + 1]:
                    stale.append(f"{f.relative_to(REPO)}:{ln}: says {m.group(1)}, server registers {n}")
    stale = [s for s in stale if "SKILL_HUB_SPEC" not in s and "SEED_SKILLS" not in s]
    assert not stale, "\n".join(stale)


def test_mcp_server_page_lists_every_registered_tool():
    page = (REPO / "site/src/content/docs/features/mcp-server.md").read_text()
    documented = set(re.findall(r"^\| `(\w+)` \|", page, re.M))
    assert documented == set(registered_mcp_tools())


def test_getting_started_flow_links_to_the_next_page():
    docs = REPO / "site/src/content/docs"
    chain = [
        ("getting-started/introduction", "/getting-started/installation/"),
        ("getting-started/installation", "/getting-started/connect-phone/"),
        ("getting-started/connect-phone", "/getting-started/hello-world/"),
        ("getting-started/hello-world", "/skills/using-skills/"),
        ("skills/using-skills", "/skills/creating-skills/"),
        ("skills/creating-skills", "/skills/publishing/"),
    ]
    missing = [page for page, nxt in chain if nxt not in (docs / f"{page}.md").read_text()]
    assert not missing, f"pages that do not link to the next step: {missing}"


def test_v160_release_notes_use_generated_catalog_counts_and_label_history():
    notes = (REPO / "docs/releases/v1.6.0.md").read_text()
    # Short GitHub-style notes: catalog totals live in the generated registry, not hard-coded "currently has" claims.
    assert "The registry currently has" not in notes
    assert "The committed registry contains" not in notes
    assert f"**{len(registered_mcp_tools())} tools**" in notes


@pytest.mark.parametrize("name", [
    "docs/SKILL_CREATION_GUIDE.md",
    "skillhub/_guides/skill-creation-guide/SKILL.md",
    "site/src/content/docs/skills/skill-creation-guide.md",
    "site/src/content/docs/skills/creating-skills.md",
    "docs/skill-schema-v2.md",
    pytest.param("docs/SKILL_HUB_SPEC.md", marks=pytest.mark.skipif(
        not (REPO / "docs/SKILL_HUB_SPEC.md").exists(), reason="internal spec is not part of the public tree")),
])
def test_authoring_surfaces_explain_toolkit_and_content_bound_runs(name):
    text = (REPO / name).read_text()
    for phrase in ("one entry action", "3–6 focused primitives", "one read-state action",
                   "Toolkit", "three times after the final definition-file edit",
                   "gitd.skills.engine.nodes", "device.screencap_png()"):
        assert phrase in text, (name, phrase)


def test_new_benchmark_protocol_is_public_and_demo_specs_are_not_dangling():
    import json
    from gitd.skills.engine.bench import PROTOCOL_DOC
    assert not PROTOCOL_DOC.startswith("docs/reports/")
    assert (REPO / PROTOCOL_DOC).is_file()
    catalog = json.loads((REPO / "skillhub/demo-catalog.json").read_text())
    for clip in catalog["clips"]:
        spec = clip.get("source_spec")
        if spec:
            assert not spec.startswith("docs/reports/")
            assert (REPO / spec).is_file()
