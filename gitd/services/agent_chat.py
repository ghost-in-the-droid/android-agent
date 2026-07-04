"""Agent chat service — manages sessions, runs the agent loop with tool execution.

Supports multiple LLM providers:
  - claude-code: Free, local, uses `claude` CLI (default)
  - anthropic: Claude API with native tool_use
  - openrouter: Any model via OpenRouter
  - ollama: Local models
"""

import json
import logging
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from gitd.services.agent_tools import TOOLS, execute_tool, get_screenshot_b64
from gitd.services.device_context import get_phone_state, get_screen_tree

log = logging.getLogger(__name__)

DEFAULT_SYSTEM = """You are an Android automation agent with full control over a physical Android device.

You can see the screen (via screenshots and UI tree), interact with it (tap, swipe, type),
manage apps (install, uninstall, launch), run shell commands, and execute automation skills.

## Available tools:
{tool_list}

## How to use tools:
To call a tool, output a JSON block like this:
```tool
{{"tool": "tool_name", "args": {{"param": "value"}}}}
```

You can call multiple tools in sequence. After each tool call, I'll show you the result.

## Guidelines:
- Always use get_screen_tree first to understand what's on screen
- Use element indices from the tree for precise tapping (tap_element)
- After actions, verify results with get_screen_tree
- Keep responses concise"""

ANTHROPIC_SYSTEM = """You are an Android automation agent with full control over a physical Android device.

You can see the screen (via screenshots and UI tree), interact with it (tap, swipe, type),
manage apps (install, uninstall, launch), run shell commands, and execute automation skills.

Guidelines:
- Always use get_screen_tree first to understand what's on screen before tapping
- Use element indices from the tree for precise tapping (tap_element)
- After performing actions, use get_screen_tree to verify the result
- Keep responses concise — show what you did and the result"""

MAX_TURNS = 15

PROVIDERS = {
    "claude-code": {"label": "Claude Code (free)", "models": ["sonnet", "opus", "haiku"]},
    "anthropic": {"label": "Claude API", "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514"]},
    "openrouter": {"label": "OpenRouter", "models": ["anthropic/claude-sonnet-4", "google/gemini-2.5-pro"]},
    "ollama": {
        "label": "Ollama (local)",
        "models": [
            "llama3.2:3b",
            "llama3.2:1b",
            "gemma3:4b",
            "qwen3:4b",
            "phi4-mini:3.8b",
            "mistral:7b",
        ],
    },
    # On-device — runs the model in-process via MediaPipe (.task) or
    # llama.cpp JNI (.gguf). The Kotlin OnDeviceModelRegistry is the source of
    # truth for ids; we ship a default subset here and overlay live ids below.
    "on-device": {
        "label": "On-device (Gemma)",
        "models": ["gemma-3-1b-it", "gemma-2-2b-it", "gemma-4-e2b-q4km-gguf"],
    },
    # vLLM — full-precision Gemma 4 served from the GPU box,
    # routed via Mac SSH tunnel + adb reverse so the phone hits it as if it
    # were on localhost. Same OpenAI-compatible shape as openrouter; we just
    # point the client at config.vllm_base_url instead.
    "vllm": {
        "label": "vLLM (remote GPU)",
        "models": [
            "unsloth/gemma-4-E2B-it",
            "unsloth/gemma-4-E2B-it-bnb-4bit",
            "unsloth/gemma-4-E4B-it",
            "unsloth/gemma-4-E4B-it-bnb-4bit",
        ],
    },
}


@dataclass
class ChatMessage:
    role: str
    content: str
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_id: str = ""
    image_b64: str = ""


@dataclass
class ChatSession:
    id: str
    device: str
    provider: str = "claude-code"
    model: str = "sonnet"
    messages: list = field(default_factory=list)
    api_messages: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    auto_screenshot: bool = True


_sessions: dict[str, ChatSession] = {}
_active_procs: dict[str, subprocess.Popen] = {}  # session_id -> running subprocess


def stop_agent(session_id: str):
    """Kill the running agent subprocess AND all its children — THIS session only.

    chat_claude_code launches claude with start_new_session=True, so claude and
    its node + MCP-tool children share one process group (pgid == the claude
    pid). Killing that group through the proc handle registered in
    _active_procs[session_id] is a complete, session-scoped stop: SIGTERM the
    group, then SIGKILL if it doesn't exit within 2s. A re-exec (execve) keeps
    the same pgid, so a changed PID doesn't escape this.

    We deliberately do NOT fall back to `pkill -f claude...stream-json`: that
    pattern matches EVERY claude stream-json process on the box, so stopping
    session A would reap session B mid-tap. Worse, the router calls stop_agent
    in the finally of every stream (including non-claude providers that never
    register a proc), so a normal completion on one session would nuke every
    other live agent. Multi-session is a headline capability — keep stops
    isolated to their own process group.
    """
    import os as _os
    import signal as _sig

    proc = _active_procs.pop(session_id, None)
    if proc is None:
        # No process for this session (e.g. anthropic/ollama providers, or
        # already stopped). Nothing to kill — and crucially, no global sweep.
        return
    try:
        pgid = _os.getpgid(proc.pid)
        _os.killpg(pgid, _sig.SIGTERM)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _os.killpg(pgid, _sig.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    except Exception:
        # pgid lookup failed (proc already reaped) — best-effort plain kill.
        try:
            proc.kill()
        except Exception:
            pass
    log.info("Stopped agent for session %s", session_id)


def create_session(device: str, provider: str = "claude-code", model: str = "", system_prompt: str = "") -> ChatSession:
    sid = str(uuid.uuid4())[:8]
    default_model = PROVIDERS.get(provider, {}).get("models", ["sonnet"])[0] if not model else model
    session = ChatSession(id=sid, device=device, provider=provider, model=default_model or "sonnet")
    _sessions[sid] = session
    return session


def get_session(sid: str) -> ChatSession | None:
    return _sessions.get(sid)


def list_sessions() -> list[dict]:
    return [
        {"id": s.id, "device": s.device, "provider": s.provider, "model": s.model, "messages": len(s.messages)}
        for s in _sessions.values()
    ]


def delete_session(sid: str):
    _sessions.pop(sid, None)


# ── Persistence (DB) ───────────────────────────────────────────────────────


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_session_to_db(session: ChatSession):
    """Persist a ChatSession to the database (upsert conversation + append new messages)."""
    from gitd.models.base import SessionLocal
    from gitd.models.chat import ChatConversation, ChatMessageRow

    db = SessionLocal()
    try:
        conv = db.query(ChatConversation).filter_by(id=session.id).first()
        now = _utcnow_iso()

        if not conv:
            # Auto-generate title from first user message
            title = ""
            for msg in session.messages:
                if msg.role == "user" and msg.content:
                    title = msg.content[:50]
                    break
            conv = ChatConversation(
                id=session.id,
                device=session.device,
                provider=session.provider,
                model=session.model,
                title=title,
                created_at=now,
                updated_at=now,
                message_count=0,
            )
            db.add(conv)

        conv.updated_at = now
        conv.message_count = len(session.messages)

        # Only insert messages that haven't been saved yet
        existing_count = db.query(ChatMessageRow).filter_by(conversation_id=session.id).count()
        for msg in session.messages[existing_count:]:
            db.add(
                ChatMessageRow(
                    conversation_id=session.id,
                    role=msg.role,
                    content=msg.content or "",
                    tool_name=msg.tool_name or "",
                    tool_args=json.dumps(msg.tool_args) if msg.tool_args else "{}",
                    tool_id=msg.tool_id or "",
                    created_at=now,
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        log.exception("Failed to save session %s to DB", session.id)
    finally:
        db.close()


def list_conversations(device: str | None = None) -> list[dict]:
    """Return saved conversations, newest first."""
    from gitd.models.base import SessionLocal
    from gitd.models.chat import ChatConversation

    db = SessionLocal()
    try:
        q = db.query(ChatConversation)
        if device:
            q = q.filter_by(device=device)
        rows = q.order_by(ChatConversation.updated_at.desc()).all()
        return [
            {
                "id": r.id,
                "device": r.device,
                "provider": r.provider,
                "model": r.model,
                "title": r.title,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "message_count": r.message_count,
            }
            for r in rows
        ]
    finally:
        db.close()


def load_conversation(conversation_id: str) -> ChatSession | None:
    """Load a conversation from DB into an active ChatSession (placed in _sessions)."""
    from gitd.models.base import SessionLocal
    from gitd.models.chat import ChatConversation, ChatMessageRow

    db = SessionLocal()
    try:
        conv = db.query(ChatConversation).filter_by(id=conversation_id).first()
        if not conv:
            return None

        rows = db.query(ChatMessageRow).filter_by(conversation_id=conversation_id).order_by(ChatMessageRow.id).all()

        messages = []
        api_messages = []
        for r in rows:
            tool_args = {}
            if r.tool_args and r.tool_args != "{}":
                try:
                    tool_args = json.loads(r.tool_args)
                except (json.JSONDecodeError, TypeError):
                    pass
            messages.append(
                ChatMessage(
                    role=r.role,
                    content=r.content or "",
                    tool_name=r.tool_name or "",
                    tool_args=tool_args,
                    tool_id=r.tool_id or "",
                    image_b64="",
                )
            )

            # Rebuild api_messages for anthropic provider
            if conv.provider == "anthropic":
                if r.role == "user":
                    api_messages.append({"role": "user", "content": r.content or ""})
                elif r.role == "assistant":
                    api_messages.append({"role": "assistant", "content": r.content or ""})
                # tool_call and tool_result are harder to reconstruct exactly,
                # so for anthropic the resumed session may lose tool history.
                # Claude-code is stateless per turn so this is fine.

        session = ChatSession(
            id=conv.id,
            device=conv.device,
            provider=conv.provider,
            model=conv.model,
            messages=messages,
            api_messages=api_messages,
        )
        _sessions[conv.id] = session
        return session
    finally:
        db.close()


def delete_conversation(conversation_id: str):
    """Delete a conversation and its messages from the database."""
    from gitd.models.base import SessionLocal
    from gitd.models.chat import ChatConversation, ChatMessageRow

    db = SessionLocal()
    try:
        db.query(ChatMessageRow).filter_by(conversation_id=conversation_id).delete()
        db.query(ChatConversation).filter_by(id=conversation_id).delete()
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Failed to delete conversation %s", conversation_id)
    finally:
        db.close()
    # Also remove from in-memory sessions if present
    _sessions.pop(conversation_id, None)


def get_providers() -> list[dict]:
    """Return providers with models. Ollama models are discovered live from the local server."""
    import requests

    result = []
    for pid, info in PROVIDERS.items():
        models = list(info["models"])
        if pid == "ollama":
            try:
                r = requests.get("http://localhost:11434/api/tags", timeout=3)
                installed = [m["name"] for m in r.json().get("models", [])]
                if installed:
                    models = installed
            except Exception:
                pass  # Ollama not running — return defaults
        result.append({"id": pid, "label": info["label"], "models": models})
    return result


def chat_turn(session: ChatSession, user_message: str):
    """Run one agent turn. Yields SSE event dicts."""
    provider = session.provider
    if provider == "anthropic":
        yield from _chat_anthropic(session, user_message)
    elif provider == "claude-code":
        from gitd.services.agent_chat_claude_code import chat_claude_code

        yield from chat_claude_code(session, user_message)
    elif provider == "openrouter":
        yield from _chat_openrouter(session, user_message)
    elif provider == "vllm":
        yield from _chat_vllm(session, user_message)
    elif provider == "ollama":
        yield from _chat_ollama(session, user_message)
    elif provider == "on-device":
        from gitd.services.agent_chat_ondevice import chat_ondevice

        yield from chat_ondevice(session, user_message)
    else:
        yield {"type": "error", "content": f"Unknown provider: {provider}"}


# ── Anthropic API (native tool_use) ──────────────────────────────────────────


def _chat_anthropic(session: ChatSession, user_message: str):
    """Use Anthropic API with native tool calling."""
    import anthropic

    session.messages.append(ChatMessage(role="user", content=user_message))
    session.api_messages.append({"role": "user", "content": _build_vision_content(session, user_message)})

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    for turn in range(MAX_TURNS):
        try:
            resp = client.messages.create(
                model=session.model,
                max_tokens=4096,
                system=ANTHROPIC_SYSTEM,
                messages=session.api_messages,
                tools=TOOLS,
            )
        except Exception as e:
            yield {"type": "error", "content": str(e)}
            return

        has_tool_use = False
        tool_results = []

        for block in resp.content:
            if block.type == "text":
                session.messages.append(ChatMessage(role="assistant", content=block.text))
                yield {"type": "text", "content": block.text}
            elif block.type == "tool_use":
                has_tool_use = True
                tool_name = block.name
                tool_args = dict(block.input)
                tool_args.setdefault("device", session.device)

                session.messages.append(
                    ChatMessage(
                        role="tool_call", tool_name=tool_name, tool_args=tool_args, tool_id=block.id, content=""
                    )
                )
                yield {"type": "tool_call", "name": tool_name, "args": tool_args}

                # Catch tool failures (e.g. ADBError on an offline/unauthorized
                # device) so they become a tool_result the model can react to,
                # not an uncaught raise that breaks the SSE stream. Every
                # tool_use MUST get a matching tool_result or the next turn's
                # Anthropic request is malformed — so the error text flows into
                # the same result path below. Mirrors the vllm/ollama loops.
                try:
                    result = execute_tool(tool_name, tool_args)
                except Exception as e:
                    result = f"Tool error: {e}"
                image_b64 = ""
                if tool_name in ("screenshot", "screenshot_annotated", "screenshot_cropped"):
                    image_b64 = get_screenshot_b64(tool_args.get("device", session.device)) or ""

                session.messages.append(
                    ChatMessage(
                        role="tool_result", content=result, tool_name=tool_name, tool_id=block.id, image_b64=image_b64
                    )
                )
                yield {"type": "tool_result", "name": tool_name, "result": result[:500]}
                if image_b64:
                    yield {"type": "screenshot", "image": image_b64}

                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result[:5000]})

        session.api_messages.append({"role": "assistant", "content": resp.content})
        if has_tool_use:
            session.api_messages.append({"role": "user", "content": tool_results})
        else:
            break

    yield {"type": "done"}


# ── OpenRouter ───────────────────────────────────────────────────────────────


def _chat_openrouter(session: ChatSession, user_message: str):
    """Use OpenRouter with OpenAI-compatible tool calling."""
    from openai import OpenAI

    session.messages.append(ChatMessage(role="user", content=user_message))

    client = OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )

    # Convert tools to OpenAI format
    oai_tools = [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
        }
        for t in TOOLS
    ]

    # Build messages
    context = ""
    try:
        tree = get_screen_tree(session.device)
        state = get_phone_state(session.device)
        context = f"[Screen]\n{tree[:1500]}\n[App: {state.get('currentApp', '?')}]\n\n"
    except Exception:
        pass

    messages = [
        {"role": "system", "content": ANTHROPIC_SYSTEM},
        {"role": "user", "content": f"{context}Device: {session.device}\n\n{user_message}"},
    ]

    try:
        resp = client.chat.completions.create(
            model=session.model or "anthropic/claude-sonnet-4",
            messages=messages,
            tools=oai_tools,
            max_tokens=4096,
        )
        msg = resp.choices[0].message

        if msg.content:
            session.messages.append(ChatMessage(role="assistant", content=msg.content))
            yield {"type": "text", "content": msg.content}

        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)
                tool_args.setdefault("device", session.device)

                session.messages.append(
                    ChatMessage(role="tool_call", tool_name=tool_name, tool_args=tool_args, content="")
                )
                yield {"type": "tool_call", "name": tool_name, "args": tool_args}

                result = execute_tool(tool_name, tool_args)
                session.messages.append(ChatMessage(role="tool_result", content=result, tool_name=tool_name))
                yield {"type": "tool_result", "name": tool_name, "result": result[:500]}

    except Exception as e:
        yield {"type": "error", "content": str(e)}

    yield {"type": "done"}


# ── vLLM (OpenAI-compatible, remote GPU via SSH) ──────────────────────────────


def _chat_vllm(session: ChatSession, user_message: str):
    """Use a vLLM server (default: remote GPU via SSH tunnel + adb reverse) with
    OpenAI-compatible tool calling and multi-turn agent loop.

    Same OpenAI surface as _chat_openrouter, but unlike that one we DO loop on
    tool results — the whole point of routing to a real GPU is to put a smarter
    model into the actual agent loop (open Settings → tap Wi-Fi → ...), not
    just emit a single round of tool calls.
    """
    from openai import OpenAI

    from gitd.config import settings

    session.messages.append(ChatMessage(role="user", content=user_message))

    client = OpenAI(
        api_key=os.environ.get("GITD_VLLM_API_KEY", settings.vllm_api_key) or "EMPTY",
        base_url=os.environ.get("GITD_VLLM_BASE_URL", settings.vllm_base_url),
    )

    oai_tools = [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
        }
        for t in TOOLS
    ]

    # Initial screen context.
    context = ""
    try:
        tree = get_screen_tree(session.device)
        state = get_phone_state(session.device)
        context = f"[Screen]\n{tree[:1500]}\n[App: {state.get('currentApp', '?')}]\n\n"
    except Exception:
        pass

    messages: list[dict] = [
        {"role": "system", "content": ANTHROPIC_SYSTEM},
        {"role": "user", "content": f"{context}Device: {session.device}\n\n{user_message}"},
    ]

    model = session.model or "unsloth/gemma-4-E4B-it"

    for turn in range(MAX_TURNS):
        yield {"type": "activity", "content": f"🧠 Inferring (turn {turn + 1})..."}

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=oai_tools,
                max_tokens=2048,
            )
        except Exception as e:
            yield {
                "type": "error",
                "content": (
                    f"vLLM unreachable at {client.base_url}. "
                    f"Start the server on your GPU host and ensure the SSH tunnel + "
                    f"`adb reverse tcp:8000 tcp:8000` are up. ({e})"
                ),
            }
            yield {"type": "done"}
            return

        msg = resp.choices[0].message

        if msg.content:
            session.messages.append(ChatMessage(role="assistant", content=msg.content))
            yield {"type": "text", "content": msg.content}

        # OpenAI-shape tool_calls. If absent, the model is done.
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            break

        # Append the assistant turn to the rolling conversation BEFORE running
        # tools so the next request sees the assistant's tool_calls in
        # context (OpenAI shape requires this).
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                tool_args = {}
            tool_args.setdefault("device", session.device)

            session.messages.append(ChatMessage(role="tool_call", tool_name=tool_name, tool_args=tool_args, content=""))
            yield {"type": "tool_call", "name": tool_name, "args": tool_args}

            try:
                result = execute_tool(tool_name, tool_args)
            except Exception as e:
                result = f"Tool error: {e}"
            session.messages.append(ChatMessage(role="tool_result", content=result[:500], tool_name=tool_name))
            yield {"type": "tool_result", "name": tool_name, "result": result[:500]}

            # Feed result back to the model for the next turn.
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tool_name,
                    "content": result[:1500],
                }
            )

    yield {"type": "done"}


# ── Ollama ───────────────────────────────────────────────────────────────────


def _parse_tool_calls(text: str) -> list[dict]:
    """Extract tool calls from LLM output.

    Handles a fair amount of slop because small models — especially raw Gemma 4 —
    emit f-string-style doubled braces, half-quoted keys, trailing ``, " "``
    junk, missing/extra closing braces, and similar near-misses.

    Accepted shapes:
      - {"tool": "X", "args": {...}}           (canonical)
      - {"tool": "X", "kwarg1": ..., ...}      (flat — e.g. ghost-gemma trained)
      - {"action_type": "X", ...}              (action-schema — translated to tool)
    """
    import re

    if not text:
        return []

    calls: list[dict] = []

    # Map from action-schema "action_type" → ("tool", arg-key-rewrites). For raw
    # Gemma 4 emitting the action schema we trained on, this lets the dispatcher
    # see canonical tool calls without retraining the parser side.
    action_to_tool = {
        "open_app": ("launch_app", {"app_name": "package"}),
        "click": ("tap", {"x": "x", "y": "y"}),
        "tap": ("tap", {}),
        "long_press": ("long_press", {}),
        "type_text": ("input_text", {"text": "text"}),
        "input_text": ("input_text", {}),
        "swipe": ("swipe", {}),
        "key_event": ("key_event", {"key": "key"}),
        "screenshot": ("screenshot", {}),
        "wait": ("wait", {"duration_ms": "ms"}),
        "force_stop": ("force_stop", {}),
    }

    def _coerce_action(d: dict) -> dict | None:
        action = d.get("action_type")
        if not isinstance(action, str):
            return None
        mapping = action_to_tool.get(action)
        if not mapping:
            return None
        tool_name, key_map = mapping
        args = {}
        for k, v in d.items():
            if k == "action_type":
                continue
            args[key_map.get(k, k)] = v
        return {"tool": tool_name, "args": args}

    def _try_dict(d: object) -> bool:
        if not isinstance(d, dict):
            return False
        if "tool" in d:
            calls.append(d)
            return True
        coerced = _coerce_action(d)
        if coerced:
            calls.append(coerced)
            return True
        return False

    def _try_loads(raw: str) -> bool:
        try:
            return _try_dict(json.loads(raw))
        except (ValueError, TypeError):
            return False

    def _attempt_repairs(raw: str) -> bool:
        """Run a chain of cleanups, retrying json.loads at every checkpoint."""
        candidate = raw

        # Doubled braces (Gemma f-string artefact) → singles. Only run when at
        # least one ``{{`` is present — otherwise we'd corrupt valid JSON like
        # ``{"a":{"b":1}}`` which has trailing ``}}`` for nested closes.
        # Do it ONCE only; iterating collapses legitimate triples like ``}}}``
        # (which is ``}}`` + ``}`` in the doubled convention) past the right
        # shape.
        if "{{" in candidate:
            new = candidate.replace("{{", "{").replace("}}", "}")
            if new != candidate:
                candidate = new
                if _try_loads(candidate):
                    return True

        # Strip dangling-comma "junk pairs" like ``, " "`` or ``, ""`` that some
        # models tack on before a closing brace.
        cleaned = re.sub(r',\s*"[^"]*"\s*(?=[,}])', "", candidate)
        if cleaned != candidate:
            candidate = cleaned
            if _try_loads(candidate):
                return True

        # Drop trailing ``,`` before ``}`` / ``]``.
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        if cleaned != candidate:
            candidate = cleaned
            if _try_loads(candidate):
                return True

        # Truncate to the first balanced brace span — handles trailing prose
        # or extra closing braces.
        depth = 0
        start = candidate.find("{")
        if start >= 0:
            for i in range(start, len(candidate)):
                ch = candidate[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        if _try_loads(candidate[start : i + 1]):
                            return True
                        break

        return False

    # 1) ```tool / ```json fenced blocks (prompt asks for these)
    for match in re.finditer(r"```(?:tool|json)?\s*\n?(.*?)\n?```", text, re.DOTALL):
        raw = match.group(1).strip()
        if not raw:
            continue
        if _try_loads(raw):
            continue
        _attempt_repairs(raw)

    if calls:
        return calls

    # 2) No fences — scan for inline JSON objects mentioning "tool" or
    #    "action_type". Greedy: match every {...} and try each.
    for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL):
        raw = match.group(0)
        if '"tool"' not in raw and '"action_type"' not in raw:
            continue
        if _try_loads(raw):
            continue
        _attempt_repairs(raw)

    if calls:
        return calls

    # 3) Last-ditch fallback — Gemma at temp 0 routinely emits inline doubled
    #    braces with a mismatched count of closing `}` (e.g. five `}` for two
    #    `{{`). The step-2 regex above can't match a `{{` start because it
    #    expects a non-brace character after the first `{`. Collapse doubled
    #    braces over the whole text and try the same scan again.
    if "{{" in text or "}}" in text:
        flattened = text.replace("{{", "{").replace("}}", "}")
        for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", flattened, re.DOTALL):
            raw = match.group(0)
            if '"tool"' not in raw and '"action_type"' not in raw:
                continue
            if _try_loads(raw):
                continue
            _attempt_repairs(raw)

    return calls


def normalize_tool_call(call: dict) -> tuple[str, dict]:
    """Split a parsed tool call into ``(tool_name, args)``.

    Two shapes are seen in the wild and every provider must accept both:
      - ``{"tool": "X", "args": {...}}``          (gemma-4-e2b, llama, canonical)
      - ``{"tool": "X", "package": "...", ...}``   (ghost-gemma trained, qwen — flat)

    Prefer the nested ``args`` dict; otherwise treat the rest of the dict
    (every key except ``tool``) as kwargs. Returns a fresh dict the caller
    can mutate (e.g. ``setdefault("device", ...)``) without touching ``call``.
    """
    tool_name = call.get("tool", "")
    raw_args = call.get("args")
    if isinstance(raw_args, dict):
        args = dict(raw_args)
    else:
        args = {k: v for k, v in call.items() if k != "tool"}
    return tool_name, args


def _chat_ollama(session: ChatSession, user_message: str):
    """Use local Ollama model with multi-turn tool execution loop."""
    import requests

    session.messages.append(ChatMessage(role="user", content=user_message))

    # Build screen context
    context = ""
    try:
        tree = get_screen_tree(session.device)
        state = get_phone_state(session.device)
        context = f"[Screen]\n{tree[:1500]}\n[App: {state.get('currentApp', '?')}]\n\n"
    except Exception:
        pass

    # Build tool list with param names so the LLM knows what args to send
    tool_list = "\n".join(
        f"- {t['name']}: {t['description']}  params: {list(t.get('input_schema', {}).get('properties', {}).keys())}"
        for t in TOOLS
    )
    system = DEFAULT_SYSTEM.replace("{tool_list}", tool_list)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{context}Device: {session.device}\n\n{user_message}"},
    ]

    model = session.model or "llama3.2:3b"

    # Gemma 4 (and other reasoning models) emit chain-of-thought into a
    # separate `thinking` field. The agent loop wants direct JSON tool calls,
    # so disable thinking for the action loop. Surface any thinking that does
    # arrive as a `thinking` event so the UI can show it.
    is_thinking_model = any(t in model.lower() for t in ("gemma-4", "gemma4", "ghost-gemma", "qwen3", "deepseek-r1"))

    for turn in range(MAX_TURNS):
        try:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": 4096, "num_predict": 512},
            }
            if is_thinking_model:
                payload["think"] = False
            r = requests.post(
                "http://localhost:11434/api/chat",
                json=payload,
                timeout=120,
            )
            data = r.json()
            if r.status_code != 200:
                error = data.get("error", r.text[:200])
                if "not found" in error.lower():
                    yield {
                        "type": "error",
                        "content": f"Model '{model}' not found. Pull it first: ollama pull {model}",
                    }
                else:
                    yield {"type": "error", "content": f"Ollama error: {error}"}
                return
            msg = data.get("message", {}) or {}
            reply = msg.get("content", "") or ""
            thinking = msg.get("thinking", "") or ""
            if thinking:
                yield {"type": "thinking", "content": thinking}
            # Fallback: if think:false was ignored and content is empty but thinking has the answer
            if not reply and thinking:
                reply = thinking
        except requests.ConnectionError:
            yield {
                "type": "error",
                "content": "Ollama not reachable at localhost:11434. Start it: ollama serve",
            }
            return
        except Exception as e:
            yield {"type": "error", "content": str(e)}
            return

        if not reply:
            break

        session.messages.append(ChatMessage(role="assistant", content=reply))
        yield {"type": "text", "content": reply}
        messages.append({"role": "assistant", "content": reply})

        # Parse and execute tool calls
        tool_calls = _parse_tool_calls(reply)
        if not tool_calls:
            break  # No tools requested — done

        tool_results = []
        for call in tool_calls:
            tool_name, tool_args = normalize_tool_call(call)
            tool_args.setdefault("device", session.device)

            session.messages.append(ChatMessage(role="tool_call", tool_name=tool_name, tool_args=tool_args, content=""))
            yield {"type": "tool_call", "name": tool_name, "args": tool_args}

            try:
                result = execute_tool(tool_name, tool_args)
                session.messages.append(ChatMessage(role="tool_result", content=result[:500], tool_name=tool_name))
                yield {"type": "tool_result", "name": tool_name, "result": result[:500]}
                tool_results.append(f"[{tool_name}] {result[:800]}")
            except Exception as e:
                err = f"Tool error: {e}"
                session.messages.append(ChatMessage(role="tool_result", content=err, tool_name=tool_name))
                yield {"type": "tool_result", "name": tool_name, "result": err}
                tool_results.append(f"[{tool_name}] ERROR: {err}")

        # Feed tool results back for next turn
        messages.append({"role": "user", "content": "Tool results:\n" + "\n".join(tool_results)})

    yield {"type": "done"}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_vision_content(session: ChatSession, text: str) -> list:
    """Build user content with screenshot for vision-capable providers."""
    content = []
    if session.auto_screenshot and session.device:
        try:
            tree = get_screen_tree(session.device)
            if tree and tree != "(empty screen)":
                content.append({"type": "text", "text": f"[Current screen]\n{tree[:2000]}"})
        except Exception:
            pass
        try:
            state = get_phone_state(session.device)
            if state:
                content.append(
                    {"type": "text", "text": f"[App: {state.get('currentApp', '')} ({state.get('packageName', '')})]"}
                )
        except Exception:
            pass
        try:
            img = get_screenshot_b64(session.device)
            if img:
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img}})
        except Exception:
            pass
    content.append({"type": "text", "text": text})
    return content
