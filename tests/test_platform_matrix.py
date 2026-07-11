"""Tests for the generated platform-support matrix (docs emitter)."""

from gitd.services.tool_platforms import (
    TOOL_PLATFORM_SUPPORT,
    render_matrix_markdown,
    tools_for_support,
)


def test_matrix_covers_every_tool_exactly_once():
    md = render_matrix_markdown()
    for name in TOOL_PLATFORM_SUPPORT:
        assert f"| `{name}` |" in md
    # one row per tool (no dup across groups)
    assert md.count("| `") == sum(len(tools_for_support(s)) for s in TOOL_PLATFORM_SUPPORT_SUPPORTS)


def test_badges_match_support_class():
    md = render_matrix_markdown()
    # a cross-platform tool → ✅ on both
    assert "| `tap` | ✅ | ✅ |" in md
    # android-only → n/a on iOS
    assert "| `shell` | ✅ | ⚠️ n/a |" in md


def test_generated_header_and_legend_present():
    md = render_matrix_markdown()
    assert "GENERATED from gitd/services/tool_platforms.py" in md
    assert "hardware-confirmed on iOS" in md  # honesty overlay reminder
    assert md.endswith("\n")


def test_deterministic_output():
    assert render_matrix_markdown() == render_matrix_markdown()


def test_pipe_in_notes_is_escaped():
    # notes are cell content; a raw | would break the table
    md = render_matrix_markdown()
    for line in md.splitlines():
        if line.startswith("| `"):
            # exactly 5 pipes = 4 columns, unless an escaped \| appears
            assert line.replace("\\|", "").count("|") == 5


# support classes present in the registry (module-level for the count assertion)
TOOL_PLATFORM_SUPPORT_SUPPORTS = ("cross_platform", "ios_supported", "ios_planned", "android_only")
