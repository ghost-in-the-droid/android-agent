"""Turn an agent chat session into a skill (M4).

Bridges the persisted chat trace (ChatMessageRow, re-loaded by
``agent_chat.load_conversation``) to the skill writers
(``skill_creation.create_recorded_skill`` / ``create_soft_skill``) via the
trace distiller (``skills.trace_to_steps.distill_steps``).

This is the single canonical path used by every trigger surface — the native
in-chat agent tool, the ``claude-code`` MCP tool, and the REST endpoints /
UI button — so capture behaves identically regardless of provider. Kept
import-light (heavy imports are function-local) so the MCP server and router
can both call it cheaply.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from gitd.skills.trace_to_steps import distill_steps


def latest_conversation_id(device: str) -> str | None:
    """The most-recently-updated conversation id for a device.

    Used by the claude-code MCP self-trigger, where the tool call carries a
    device but not a conversation id — the active chat is the newest one.
    """
    from gitd.models.base import SessionLocal
    from gitd.models.chat import ChatConversation

    db = SessionLocal()
    try:
        conv = (
            db.query(ChatConversation)
            .filter_by(device=device)
            .order_by(ChatConversation.updated_at.desc())
            .first()
        )
        return conv.id if conv else None
    finally:
        db.close()


def _load_messages(conversation_id: str) -> list | None:
    """Re-load a conversation's ordered ChatMessage trace, or None if missing."""
    from gitd.services.agent_chat import load_conversation

    session = load_conversation(conversation_id)
    return session.messages if session is not None else None


def _guess_app_package(steps: list[dict]) -> str:
    """Best-effort target package: the last explicit launch in the trace."""
    pkg = ""
    for st in steps:
        if st.get("action") == "launch" and st.get("package"):
            pkg = st["package"]
    return pkg


def _summary(steps: list[dict]) -> str:
    if not steps:
        return "no replayable actions captured"
    counts = Counter(s["action"] for s in steps)
    parts = [f"{n} {a}" for a, n in counts.most_common()]
    return f"{len(steps)} steps: " + ", ".join(parts)


def draft_hard_skill(conversation_id: str) -> dict[str, Any]:
    """Distil a conversation's action trace into draft recorded steps (no write).

    Returns the steps + a guessed app_package + a human summary so the LLM (or
    the UI) can review/revise before committing. This is the 'draft' half of the
    draft -> review -> commit flow.
    """
    msgs = _load_messages(conversation_id)
    if msgs is None:
        raise ValueError(f"conversation not found: {conversation_id}")
    steps = distill_steps(msgs)
    return {
        "conversation_id": conversation_id,
        "steps": steps,
        "step_count": len(steps),
        "app_package": _guess_app_package(steps),
        "summary": _summary(steps),
    }


def commit_skill(
    *,
    kind: str,
    name: str,
    app_package: str = "",
    description: str = "",
    steps: list[dict] | None = None,
    guidance: str | None = None,
    conversation_id: str | None = None,
    skills_dir: str | None = None,
) -> dict[str, Any]:
    """Write a skill of the given kind. The commit half of the flow.

    HARD: uses ``steps`` if provided (the LLM/user's revised list); otherwise
    re-distils from ``conversation_id``. SOFT: writes the ``guidance`` markdown.
    """
    kind = (kind or "hard").strip().lower()
    if not name or not name.strip():
        raise ValueError("name required")

    if kind == "soft":
        if not guidance or not guidance.strip():
            raise ValueError("guidance required for a soft skill")
        from gitd.services.skill_creation import create_soft_skill

        return create_soft_skill(
            name=name,
            guidance=guidance,
            app_package=app_package,
            description=description,
            skills_dir=skills_dir,
        )

    if kind != "hard":
        raise ValueError(f"unknown skill kind: {kind}")

    # HARD — prefer the caller's revised steps; else distil from the conversation.
    if steps is None:
        if not conversation_id:
            raise ValueError("hard skill needs steps or conversation_id")
        draft = draft_hard_skill(conversation_id)
        steps = draft["steps"]
        if not app_package:
            app_package = draft["app_package"]
    if not steps:
        raise ValueError("no replayable steps to save")

    from gitd.services.skill_creation import create_recorded_skill

    return create_recorded_skill(
        name=name,
        steps=steps,
        app_package=app_package,
        description=description,
        skills_dir=skills_dir,
        kind="hard",
    )
