"""Distill a chat action-trace into replayable recorded-skill steps.

Consumes the ordered tool-call trace of an agent chat session (the same
``ChatMessage`` stream that ``agent_chat.py`` records in ``session.messages``,
or the persisted ``ChatMessageRow`` rows re-loaded by ``load_conversation``)
and produces a flat list of steps in the ``RecordedWorkflow`` schema consumed
by :class:`gitd.skills.base.RecordedStepAction`.

Design — ALLOW-LIST the actuating navigation/input tools. The agent tool
vocabulary grows over time and most tools are read-only (``screenshot``,
``ocr_*``, ``get_*``, ``find_on_screen``) or are side-effects that do not
belong in a deterministic UI replay (screen recording, camera, ``sub_agent``,
``create_skill``). Anything not in the allow-list is dropped. The mapping is
table-driven so the supported set is obvious and unit-testable, and works for
every provider — including ``claude-code``, whose MCP tool names are already
de-prefixed of ``mcp__android-agent__`` before they reach the trace.

Note: parameterization (``{placeholder}`` tokens) and pruning are deliberately
NOT done here — the distiller emits literal captured values. Turning literals
into parameters / dropping redundant steps is the LLM's job in the
draft -> review -> commit flow.
"""

from __future__ import annotations

import re
from typing import Any

# Coords in a tap_element result string: "...at (540, 800)"
_COORD_RE = re.compile(r"\((\d+),\s*(\d+)\)")
# Label in a tap_element result string: "Tapped element #3 'Search' at ..."
_LABEL_RE = re.compile(r"'([^']*)'")

_MAX_DESC = 160


def _get(msg: Any, key: str, default: Any = None) -> Any:
    """Read a field from a ChatMessage-like object OR a plain dict."""
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def _as_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ── Per-tool handlers: (args, result_text) -> recorded step dict | None ──────
# Returning None drops the step (e.g. a tap with no usable coordinates).


def _h_tap(args: dict, result: str) -> dict | None:
    x, y = _as_int(args.get("x")), _as_int(args.get("y"))
    if x is None or y is None:
        return None
    return {"action": "tap", "x": x, "y": y}


def _h_tap_element(args: dict, result: str) -> dict | None:
    # tap_element only carries an idx; the resolved coords live in the result
    # string ("...at (cx, cy)"). Recover them so replay is coordinate-stable.
    m = _COORD_RE.search(result or "")
    if not m:
        return None
    return {"action": "tap", "x": int(m.group(1)), "y": int(m.group(2))}


def _h_swipe(args: dict, result: str) -> dict | None:
    coords = [_as_int(args.get(k)) for k in ("x1", "y1", "x2", "y2")]
    if any(c is None for c in coords):
        return None
    x1, y1, x2, y2 = coords
    return {"action": "swipe", "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _h_type(args: dict, result: str) -> dict | None:
    text = args.get("text")
    if not text:
        return None
    # RecordedStepAction.type auto-detects non-ASCII -> type_unicode, so
    # type_text and type_unicode both map to the same recorded action.
    return {"action": "type", "text": str(text)}


def _h_key(args: dict, result: str) -> dict | None:
    key = args.get("key")
    if not key:
        return None
    return {"action": "key", "key": str(key)}


def _h_back(args: dict, result: str) -> dict | None:
    return {"action": "back"}


def _h_home(args: dict, result: str) -> dict | None:
    return {"action": "home"}


def _h_long_press(args: dict, result: str) -> dict | None:
    x, y = _as_int(args.get("x")), _as_int(args.get("y"))
    if x is None or y is None:
        return None
    step = {"action": "long_press", "x": x, "y": y}
    dur = _as_int(args.get("duration_ms"))
    if dur is not None:
        step["duration_ms"] = dur
    return step


def _h_launch(args: dict, result: str) -> dict | None:
    pkg = args.get("package")
    if not pkg:
        return None
    return {"action": "launch", "package": str(pkg)}


def _h_launch_intent(args: dict, result: str) -> dict | None:
    # 'action' is the recorded dispatch key, so the intent's own action goes
    # under 'intent_action' to avoid collision (honored by RecordedStepAction).
    step: dict = {"action": "launch_intent"}
    for src, dst in (
        ("action", "intent_action"),
        ("data", "data"),
        ("package", "package"),
        ("component", "component"),
        ("extras", "extras"),
    ):
        if args.get(src):
            step[dst] = args[src]
    if len(step) == 1:  # nothing but the dispatch key -> useless
        return None
    return step


def _h_open_url(args: dict, result: str) -> dict | None:
    url = args.get("url")
    if not url:
        return None
    return {"action": "open_url", "url": str(url)}


def _h_wait(args: dict, result: str) -> dict | None:
    secs = args.get("seconds")
    secs = _as_int(secs) if secs is not None else None
    return {"action": "wait", "seconds": secs if secs is not None else 2}


# The allow-list. Every actuating navigation/input tool maps to a handler.
# Tools absent from this table are dropped by distill_steps.
_HANDLERS = {
    "tap": _h_tap,
    "tap_element": _h_tap_element,
    "swipe": _h_swipe,
    "type_text": _h_type,
    "type_unicode": _h_type,
    "press_key": _h_key,
    "press_back": _h_back,
    "press_home": _h_home,
    "long_press": _h_long_press,
    "launch_app": _h_launch,
    "launch_intent": _h_launch_intent,
    "open_url": _h_open_url,
    "wait": _h_wait,
}


def actuating_tools() -> set[str]:
    """The set of chat tools the distiller knows how to replay."""
    return set(_HANDLERS)


def _clip(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= _MAX_DESC else text[: _MAX_DESC - 1] + "…"


def distill_steps(messages: list[Any]) -> list[dict]:
    """Turn an ordered chat message trace into recorded-skill steps.

    ``messages`` is any ordered iterable of ChatMessage-like objects or dicts
    with ``role`` / ``tool_name`` / ``tool_args`` / ``tool_id`` / ``content``.
    Each ``role == "tool_call"`` for an allow-listed tool becomes one step; the
    matching ``role == "tool_result"`` (by ``tool_id``, else the next result)
    supplies data the call args lack (e.g. tap_element coords). The nearest
    preceding assistant ``text`` becomes the step ``description``.
    """
    msgs = list(messages)

    # Index tool_results by tool_id, and keep a positional fallback list.
    result_by_id: dict[str, str] = {}
    for m in msgs:
        if _get(m, "role") == "tool_result":
            tid = _get(m, "tool_id") or ""
            if tid:
                result_by_id[tid] = _get(m, "content") or ""

    steps: list[dict] = []
    last_assistant = ""
    for i, m in enumerate(msgs):
        role = _get(m, "role")
        if role == "assistant":
            txt = _get(m, "content") or ""
            if txt.strip():
                last_assistant = txt
            continue
        if role != "tool_call":
            continue

        name = _get(m, "tool_name") or ""
        handler = _HANDLERS.get(name)
        if handler is None:
            continue

        args = _get(m, "tool_args") or {}
        tid = _get(m, "tool_id") or ""
        result = result_by_id.get(tid, "")
        if not result:  # no tool_id match -> next tool_result positionally
            for m2 in msgs[i + 1 :]:
                if _get(m2, "role") == "tool_result":
                    result = _get(m2, "content") or ""
                    break

        step = handler(args, result)
        if step is None:
            continue

        # Description: prefer the tap_element label, else the last assistant text.
        desc = ""
        if name == "tap_element":
            lm = _LABEL_RE.search(result or "")
            if lm and lm.group(1):
                desc = lm.group(1)
        if not desc and last_assistant:
            desc = _clip(last_assistant)
        if desc:
            step["description"] = desc

        steps.append(step)

    return steps
