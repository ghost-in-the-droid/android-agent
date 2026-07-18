"""Allow-list classification regression tests (#666 / iOS reconciliation).

SAFE_DEVICE_TOOLS is the fail-closed allow-list gating run_flow and the
framework adapters. These tests pin the two invariants that make it safe to
keep adding tools:

* every dispatchable tool is classified — either vetted-safe or explicitly
  exec-capable. A new TOOLS entry that lands in neither set fails CI, forcing
  a deliberate classification instead of silent exposure (or silent blocking).
* the exec-capable set can never leak into the safe set.
"""

from gitd.services.agent_tools import EXEC_CAPABLE_TOOLS, SAFE_DEVICE_TOOLS, TOOLS


def test_every_tool_is_classified():
    """A tool in TOOLS but in neither set is a classification hole — fail CI."""
    names = {t["name"] for t in TOOLS}
    unclassified = names - SAFE_DEVICE_TOOLS - EXEC_CAPABLE_TOOLS
    assert not unclassified, (
        f"Unclassified tools {sorted(unclassified)}: add each to SAFE_DEVICE_TOOLS "
        "(vetted safe) or EXEC_CAPABLE_TOOLS (exec-capable) in agent_tools.py"
    )


def test_safe_and_exec_sets_are_disjoint():
    overlap = SAFE_DEVICE_TOOLS & EXEC_CAPABLE_TOOLS
    assert not overlap, f"Tools classified both safe and exec-capable: {sorted(overlap)}"


def test_allowlist_names_exist_in_dispatch():
    """No stale allow-list entries pointing at tools that no longer exist."""
    names = {t["name"] for t in TOOLS}
    assert SAFE_DEVICE_TOOLS <= names, f"Stale safe entries: {sorted(SAFE_DEVICE_TOOLS - names)}"
    assert EXEC_CAPABLE_TOOLS <= names, f"Stale exec entries: {sorted(EXEC_CAPABLE_TOOLS - names)}"


def test_exec_vectors_stay_denied():
    """The known exec-capable tools (incl. every iOS-added one) never go safe."""
    for tool in (
        "shell",
        "run_skill",
        "run_workflow",
        "run_action",
        "create_skill",
        "launch_intent",
        "explore_app",
        "fix_device_health",
    ):
        assert tool in EXEC_CAPABLE_TOOLS, f"{tool} missing from EXEC_CAPABLE_TOOLS"
        assert tool not in SAFE_DEVICE_TOOLS, f"exec-capable {tool} leaked into SAFE_DEVICE_TOOLS"


def test_flow_allowlist_is_the_same_object():
    """run_flow must gate on the identical frozenset (#668), not a copy that can drift."""
    from gitd.mcp_server import FLOW_ALLOWED_TOOLS

    assert FLOW_ALLOWED_TOOLS is SAFE_DEVICE_TOOLS
