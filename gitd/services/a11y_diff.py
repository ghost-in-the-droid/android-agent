"""Differential accessibility state — a before/after UI-tree diff.

A perception aid distilled from the AndroidWorld agent harness (``_a11y_diff``):
after a UI action we show the model *what changed* (which elements appeared /
disappeared) instead of making it re-read the whole tree and infer the delta.
DroidRun-style; purely additive — the diff is appended to a tool result, it
never alters the action that ran.

Operates on the normalized element dicts returned by
:func:`gitd.services.device_context.get_interactive_elements` — each element is
``{idx, text, content_desc, resource_id, class, bounds, center, clickable,
scrollable}`` — so it is cross-platform (Android + iOS share that shape).
"""

from __future__ import annotations

# How many added/removed entries to spell out before collapsing to a count.
_MAX_LISTED = 6
# Position-bucket size (px). Two elements whose centers land in the same
# ~40px bucket are treated as the same slot, so sub-pixel jitter between two
# dumps of an unchanged screen does not read as a change.
_POS_BUCKET = 40


def element_label(el: dict) -> str:
    """Human label for an element: visible text, else its a11y content-desc."""
    return (el.get("text") or el.get("content_desc") or "").strip()


def element_key(el: dict) -> tuple:
    """Identity of an element for diffing: label + type + coarse position.

    Deliberately coarse (label truncated, center bucketed) so an unchanged
    screen dumped twice produces identical keys despite coordinate jitter —
    matching the AW harness's ``(label[:30], ui_type, cx//40, cy//40)`` key.
    """
    center = el.get("center") or {}
    cx = int(center.get("x", 0)) // _POS_BUCKET
    cy = int(center.get("y", 0)) // _POS_BUCKET
    return (element_label(el)[:30], el.get("class", ""), cx, cy)


def diff_elements(prev: list[dict] | None, curr: list[dict] | None) -> str:
    """Return a compact text diff of which elements appeared / disappeared.

    Returns ``""`` when there is no previous state to compare against (the first
    action of a session has nothing to diff), and ``"A11y diff: no change."``
    when the two states are equivalent — both are cheap, unambiguous signals for
    the caller to decide whether to surface anything.
    """
    if not prev:
        return ""
    curr = curr or []
    prev_keys = {element_key(e) for e in prev}
    curr_keys = {element_key(e) for e in curr}
    added = [e for e in curr if element_key(e) not in prev_keys]
    removed = [e for e in prev if element_key(e) not in curr_keys]
    if not added and not removed:
        return "A11y diff: no change."

    parts = ["A11y diff (since last action):"]
    for e in added[:_MAX_LISTED]:
        parts.append(f"  + '{element_label(e)}' ({e.get('class', '')})")
    if len(added) > _MAX_LISTED:
        parts.append(f"  + …{len(added) - _MAX_LISTED} more new")
    for e in removed[:_MAX_LISTED]:
        parts.append(f"  - '{element_label(e)}' ({e.get('class', '')})")
    if len(removed) > _MAX_LISTED:
        parts.append(f"  - …{len(removed) - _MAX_LISTED} more gone")
    return "\n".join(parts)
