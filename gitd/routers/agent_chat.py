"""Agent Chat routes — interactive natural language phone control."""
import json
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query
from starlette.responses import StreamingResponse

router = APIRouter(prefix="/api/agent-chat", tags=["agent-chat"])


@router.post("/session", summary="Create Agent Chat Session")
def create_session(data: dict = Body({})):
    """Create a new agent chat session for a device."""
    from gitd.services.agent_chat import create_session
    device = data.get("device", "")
    if not device:
        raise HTTPException(status_code=400, detail="device required")
    session = create_session(
        device=device,
        provider=data.get("provider", "anthropic"),
        model=data.get("model", ""),
        system_prompt=data.get("system_prompt", ""),
    )
    return {"ok": True, "session_id": session.id, "device": session.device, "model": session.model}


@router.get("/sessions", summary="List Active Sessions")
def list_sessions():
    from gitd.services.agent_chat import list_sessions
    return list_sessions()


@router.get("/session/{sid}", summary="Get Session History")
def get_session(sid: str):
    from gitd.services.agent_chat import get_session
    session = get_session(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": session.id, "device": session.device, "model": session.model,
        "messages": [
            {"role": m.role, "content": m.content, "tool_name": m.tool_name,
             "tool_args": m.tool_args, "image_b64": m.image_b64[:100] if m.image_b64 else ""}
            for m in session.messages
        ],
    }


@router.delete("/session/{sid}", summary="Delete Session")
def delete_session(sid: str):
    from gitd.services.agent_chat import delete_session
    delete_session(sid)
    return {"ok": True}


@router.post("/stop/{sid}", summary="Stop Running Agent")
def stop_agent(sid: str):
    """Kill the running agent subprocess for a session."""
    from gitd.services.agent_chat import stop_agent
    stop_agent(sid)
    return {"ok": True}


@router.post("/message", summary="Send Message (SSE Stream)")
def send_message(data: dict = Body({})):
    """Send a message to the agent. Returns SSE stream of events."""
    from gitd.services.agent_chat import (
        get_session, chat_turn, create_session, save_session_to_db,
    )

    sid = data.get("session_id", "")
    message = data.get("content", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="content required")

    session = get_session(sid) if sid else None
    # Auto-create session if device provided but no session
    if not session:
        device = data.get("device", "")
        if not device:
            raise HTTPException(status_code=400, detail="session_id or device required")
        session = create_session(
            device=device,
            provider=data.get("provider", "anthropic"),
            model=data.get("model", ""),
        )

    def generate():
        # Send session ID first so frontend can use it for stop
        yield f"data: {json.dumps({'type': 'session', 'session_id': session.id})}\n\n"
        try:
            for event in chat_turn(session, message):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        # Persist conversation after streaming completes
        try:
            save_session_to_db(session)
        except Exception:
            pass  # Don't break the stream for persistence errors

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Conversation persistence endpoints ─────────────────────────────────────

@router.get("/conversations", summary="List Saved Conversations")
def list_conversations_endpoint(device: Optional[str] = Query(None)):
    """List saved conversations, optionally filtered by device."""
    from gitd.services.agent_chat import list_conversations
    return list_conversations(device=device)


@router.post("/conversation/{cid}/resume", summary="Resume Conversation")
def resume_conversation(cid: str):
    """Load a saved conversation into an active session so it can be continued."""
    from gitd.services.agent_chat import load_conversation, get_session

    # If already loaded in memory, just return it
    existing = get_session(cid)
    if existing:
        return {
            "ok": True,
            "session_id": existing.id,
            "device": existing.device,
            "provider": existing.provider,
            "model": existing.model,
            "message_count": len(existing.messages),
            "messages": [
                {"role": m.role, "content": m.content, "tool_name": m.tool_name, "tool_args": m.tool_args}
                for m in existing.messages
            ],
        }

    session = load_conversation(cid)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "ok": True,
        "session_id": session.id,
        "device": session.device,
        "provider": session.provider,
        "model": session.model,
        "message_count": len(session.messages),
        "messages": [
            {"role": m.role, "content": m.content, "tool_name": m.tool_name, "tool_args": m.tool_args}
            for m in session.messages
        ],
    }


@router.delete("/conversation/{cid}", summary="Delete Conversation")
def delete_conversation_endpoint(cid: str):
    """Delete a conversation and its messages from the database."""
    from gitd.services.agent_chat import delete_conversation
    delete_conversation(cid)
    return {"ok": True}
