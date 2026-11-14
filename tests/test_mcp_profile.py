import json
import subprocess
import sys
import asyncio

from gitd import mcp_server as m


def test_skills_first_profile_keeps_skill_tools_and_drops_the_rest():
    hidden = set(m.profile_hidden("skills-first").split(","))
    served = {t.name for t in asyncio.run(m.mcp.list_tools())} - hidden
    assert {"find_skill", "run_skill", "run_skill_resume", "create_skill"} <= served
    assert served == m.PROFILE_KEEP["skills-first"]


def test_hand_only_profile_has_no_skill_tools():
    hidden = set(m.profile_hidden("hand-only").split(","))
    served = {t.name for t in asyncio.run(m.mcp.list_tools())} - hidden
    assert served == m.PROFILE_KEEP["hand-only"] and not any("skill" in n for n in served)


def test_unknown_profile_hides_nothing():
    assert m.profile_hidden("") == "" and m.profile_hidden("nope") == ""


def test_private_crm_tools_are_not_served():
    names = {t.name for t in asyncio.run(m.mcp.list_tools())}
    assert not names & {"lookup_lead", "list_unread_leads", "crm_lookup_contact", "crm_list_unread_messages"}


def test_soft_only_profile_withholds_run_skill_but_keeps_notes():
    hidden = set(m.profile_hidden("soft-only").split(","))
    served = {t.name for t in asyncio.run(m.mcp.list_tools())} - hidden
    assert {"find_skill", "get_skill_notes"} <= served and not served & {"run_skill", "run_skill_resume"}


def test_get_skill_notes_returns_soft_md_for_a_flat_skill():
    assert "SOFT skill" in m.get_skill_notes("markor") or "No SOFT.md" in m.get_skill_notes("markor")
    assert m.get_skill_notes("no-such-skill").startswith("No SOFT.md")


def test_find_skill_points_at_notes_not_the_hidden_replay():
    code = (
        "import json; from gitd import mcp_server as m; m.hide_tools(m.profile_hidden('soft-only'));"
        "print(m.find_skill('make a note called Shopping with milk and eggs', 1))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    hit = json.loads(out[out.index("[") :])[0]
    assert hit.get("notes_with") == "get_skill_notes" and "run_with" not in hit
