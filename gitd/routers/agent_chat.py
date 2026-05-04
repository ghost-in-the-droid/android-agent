"""Agent Chat routes — interactive natural language phone control."""

import json
import logging
import threading
from typing import Optional

import requests
from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from gitd.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-chat", tags=["agent-chat"])

OLLAMA_URL = settings.ollama_base_url


# ── Request models ──────────────────────────────────────────────────────────


class OllamaModelRequest(BaseModel):
    model: str


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
        "id": session.id,
        "device": session.device,
        "model": session.model,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "tool_name": m.tool_name,
                "tool_args": m.tool_args,
                "image_b64": m.image_b64[:100] if m.image_b64 else "",
            }
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
        chat_turn,
        create_session,
        get_session,
        save_session_to_db,
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
        except (GeneratorExit, Exception) as e:
            if not isinstance(e, GeneratorExit):
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            # ALWAYS clean up — whether stream completed normally or was aborted
            try:
                stop_agent(session.id)
            except Exception:
                pass
            try:
                save_session_to_db(session)
            except Exception:
                pass

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
    from gitd.services.agent_chat import get_session, load_conversation

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


@router.get("/providers", summary="List Chat Providers")
def list_providers():
    """Return available providers with models. Ollama models are discovered live."""
    from gitd.services.agent_chat import get_providers

    return get_providers()


@router.post("/warmup", summary="Pre-fill on-device KV cache")
def warmup_on_device(data: dict = Body({})):
    """
    Pre-bake the system + tool list prefix into the on-device LLM's KV cache
    so the user's first chat turn lands as a "turn 2" with full prefix
    reuse. Saves ~120 s of cold prefill on Snapdragon-class CPUs with the
    default 1.3K-token system prompt.

    The Android app should POST this once at launch (idempotent; subsequent
    calls are near-free if the prefix is already cached). No-op for
    non-llama.cpp runtimes.

    Body: {"device": "<adb_serial>", "model": "gemma-4-e2b-gguf"}
    """
    from gitd.services.agent_chat import DEFAULT_SYSTEM
    from gitd.services.agent_chat_ondevice import _kotlin_llm
    from gitd.services.agent_tools import TOOLS

    device = (data.get("device") or "").strip()
    model_id = (data.get("model") or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="model required")

    llm = _kotlin_llm()
    if llm is None:
        return {"ok": False, "warmed": 0, "reason": "Chaquopy bridge missing"}

    try:
        if not bool(llm.ensureLoaded(model_id)):
            return {"ok": False, "warmed": 0, "reason": f"model {model_id} not loaded"}
    except Exception as e:
        return {"ok": False, "warmed": 0, "reason": f"ensureLoaded failed: {e}"}

    # Build the same stable prefix _chat_ondevice uses. ondevice_stable_prefix
    # is the single source of truth — keeping it shared ensures the warmup
    # KV cache key matches the prefix the chat path actually decodes.
    from gitd.services.agent_chat_ondevice import ondevice_stable_prefix
    tool_list = "\n".join(
        f"- {t['name']}: {t['description']}  params: {list(t.get('input_schema', {}).get('properties', {}).keys())}"
        for t in TOOLS
    )
    system = DEFAULT_SYSTEM.replace("{tool_list}", tool_list)
    stable_prefix = ondevice_stable_prefix(system, device)

    # Disk-persistence: hash the prefix to a deterministic filename. If a
    # previously-saved KV state with the same hash exists, restore it
    # (~hundred ms) instead of re-prefilling (~2 minutes). The hash covers
    # both the system prompt and the device id, so a model swap or system
    # prompt edit invalidates the cache automatically.
    import hashlib
    import os
    cache_dir = "/data/data/com.ghostinthedroid.app/files/ondevice/kv-cache"
    os.makedirs(cache_dir, exist_ok=True)
    h = hashlib.sha256()
    h.update(model_id.encode())
    h.update(b"\n")
    h.update(stable_prefix.encode())
    cache_path = os.path.join(cache_dir, f"warmup-{h.hexdigest()[:16]}.bin")

    # Try restore first.
    try:
        loaded = int(getattr(llm, "loadState")(model_id, cache_path))
    except Exception:
        loaded = -1
    if loaded > 0:
        return {"ok": True, "warmed": loaded, "model": model_id, "from_cache": True}

    # Cold path: do the full prefill.
    try:
        warmed = int(llm.warmup(model_id, stable_prefix))
    except Exception as e:
        return {"ok": False, "warmed": 0, "reason": f"warmup failed: {e}"}

    # Save for next launch (best-effort; failure doesn't break the warmup).
    try:
        getattr(llm, "saveState")(model_id, cache_path)
    except Exception:
        pass

    return {"ok": True, "warmed": warmed, "model": model_id, "from_cache": False}


# ── Ollama model management ──────────────────────────────────────────────

# Track background pull operations
_pull_status: dict[str, dict] = {}  # model -> {"status": "pulling"|"done"|"error", "error": "..."}


def _ollama_request(method: str, path: str, **kwargs) -> requests.Response:
    """Make a request to the Ollama API. Raises on connection failure."""
    url = f"{OLLAMA_URL}{path}"
    try:
        return requests.request(method, url, **kwargs)
    except requests.ConnectionError:
        raise HTTPException(status_code=503, detail="Ollama not reachable. Start it: ollama serve")


@router.get("/ollama/status", summary="Ollama Model Status")
def ollama_status():
    """Return all installed Ollama models with loaded/unloaded status and VRAM usage."""
    try:
        tags = _ollama_request("GET", "/api/tags", timeout=3).json()
        ps = _ollama_request("GET", "/api/ps", timeout=3).json()
    except HTTPException:
        return {"ok": False, "error": "Ollama not running", "models": []}

    loaded = {m["name"]: m for m in ps.get("models", [])}
    models = []
    for m in tags.get("models", []):
        name = m["name"]
        lm = loaded.get(name)
        models.append(
            {
                "name": name,
                "size_gb": round(m.get("size", 0) / 1e9, 1),
                "parameter_size": m.get("details", {}).get("parameter_size", ""),
                "family": m.get("details", {}).get("family", ""),
                "quantization": m.get("details", {}).get("quantization_level", ""),
                "status": "loaded" if lm else "unloaded",
                "vram_gb": round(lm["size_vram"] / 1e9, 1) if lm else 0,
                "expires_at": lm.get("expires_at", "") if lm else "",
            }
        )
    return {"ok": True, "models": models}


@router.post("/ollama/load", summary="Load Ollama Model")
def ollama_load(req: OllamaModelRequest):
    """Load a model into VRAM. Sends an empty generate to warm up."""
    r = _ollama_request(
        "POST",
        "/api/generate",
        json={"model": req.model, "prompt": "", "keep_alive": "10m"},
        timeout=120,
    )
    if r.status_code != 200:
        error = r.json().get("error", r.text[:200])
        if "not found" in error.lower():
            return {"ok": False, "error": f"Model not found. Run: ollama pull {req.model}"}
        return {"ok": False, "error": error}
    return {"ok": True, "model": req.model, "status": "loaded"}


@router.post("/ollama/pull", summary="Pull Ollama Model")
def ollama_pull(req: OllamaModelRequest):
    """Pull (download) a model from the Ollama registry. Non-blocking — runs in background."""
    if req.model in _pull_status and _pull_status[req.model].get("status") == "pulling":
        return {"ok": True, "model": req.model, "status": "already_pulling"}

    _pull_status[req.model] = {"status": "pulling"}

    def _do_pull():
        try:
            r = requests.post(
                f"{OLLAMA_URL}/api/pull",
                json={"name": req.model, "stream": False},
                timeout=1800,
            )
            if r.status_code == 200:
                _pull_status[req.model] = {"status": "done"}
                log.info("Pulled Ollama model: %s", req.model)
            else:
                _pull_status[req.model] = {"status": "error", "error": r.json().get("error", "unknown")}
        except Exception as e:
            _pull_status[req.model] = {"status": "error", "error": str(e)}

    threading.Thread(target=_do_pull, daemon=True).start()
    return {"ok": True, "model": req.model, "status": "pulling"}


@router.get("/ollama/pull/{model:path}", summary="Check Pull Status")
def ollama_pull_status(model: str):
    """Check the status of a background model pull."""
    status = _pull_status.get(model, {"status": "unknown"})
    return {"model": model, **status}


@router.post("/ollama/unload", summary="Unload Ollama Model")
def ollama_unload(req: OllamaModelRequest):
    """Unload a model from VRAM (keep_alive=0)."""
    try:
        _ollama_request(
            "POST",
            "/api/generate",
            json={"model": req.model, "keep_alive": 0},
            timeout=10,
        )
    except HTTPException:
        return {"ok": False, "error": "Ollama not running"}
    return {"ok": True, "model": req.model, "status": "unloaded"}
