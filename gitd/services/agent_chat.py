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
    """Kill the running agent subprocess AND all its children.

    Two layers of kill so a runaway claude can't keep tapping the phone after
    the user hits Stop:
      1. Typed kill via _active_procs[session_id] — sends SIGTERM (then SIGKILL)
         to the whole process group (chat_claude_code uses start_new_session=True
         so claude+node+MCP-tool children share a pgid).
      2. Nuclear pkill on the claude --print command line as a safety net for
         processes that escaped the group (e.g., claude re-execed via node).
    """
    import os as _os
    import signal as _sig

    proc = _active_procs.pop(session_id, None)
    if proc:
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
            # Fallback to plain kill if pgid lookup failed
            try:
                proc.kill()
            except Exception:
                pass
    # Nuclear safety net — pkill anything matching the claude --print pattern.
    # Catches procs that re-execed (PID changed), procs from a different
    # session that crashed mid-stream, and the case where _active_procs lost
    # track because chat_claude_code registered after Popen but before adding
    # to the dict.
    try:
        subprocess.run(
            ["pkill", "-9", "-f", "claude.*--print.*--output-format.*stream-json"],
            capture_output=True,
            timeout=3,
        )
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
    elif provider == "ollama":
        yield from _chat_ollama(session, user_message)
    elif provider == "on-device":
        from gitd.services.agent_chat_ondevice import chat_ondevice

        yield from chat_ondevice(session, user_message)
    else:
        yield {"type": "error", "content": f"Unknown provider: {provider}"}


# ── Claude Code (free, local CLI) ────────────────────────────────────────────


def _chat_claude_code(session: ChatSession, user_message: str):
    """Use claude CLI with MCP android-agent tools — streams output line-by-line."""
    session.messages.append(ChatMessage(role="user", content=user_message))

    # Build context
    yield {"type": "activity", "content": "📱 Reading screen..."}
    context_parts = []
    try:
        tree = get_screen_tree(session.device)
        if tree and tree != "(empty screen)":
            context_parts.append(f"[Current screen]\n{tree[:1500]}")
        state = get_phone_state(session.device)
        if state:
            context_parts.append(f"[App: {state.get('currentApp', '?')} ({state.get('packageName', '?')})]")
    except Exception:
        pass
    context = "\n".join(context_parts)

    prompt = f"""You are controlling an Android phone (serial: {session.device}).
{context}

The user wants: {user_message}

IMPORTANT: Use the MCP android-agent tools for ALL phone interactions. Never use Bash/shell for ADB — the MCP tools handle everything. Bash is only for non-phone tasks.
Key tools:
- get_screen_tree: read what's on screen (ALWAYS call this before tapping)
- tap_element(idx): tap by element index from the tree
- tap(x,y): tap by coordinates
- swipe(x1,y1,x2,y2): scroll/swipe
- type_text(text): type into focused field
- screenshot: see the screen visually
- search_apps(query): find apps by name
- launch_app(package): open an app
- press_back / press_home: navigation

After each action the screen tree is auto-included in the result.
Keep going until the task is done."""

    yield {"type": "activity", "content": "🧠 Starting agent..."}

    # Use claude CLI with full tool access via MCP
    # The .mcp.json in the project root gives it android-agent tools
    try:
        proc = subprocess.Popen(
            [
                "claude",
                "--print",
                "--model",
                session.model or "sonnet",
                "--output-format",
                "stream-json",
                "--dangerously-skip-permissions",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(__import__("pathlib").Path(__file__).parent.parent.parent),
            env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        )
    except FileNotFoundError:
        yield {"type": "error", "content": "claude CLI not found. Install: npm i -g @anthropic-ai/claude-code"}
        return

    _active_procs[session.id] = proc

    proc.stdin.write(prompt)
    proc.stdin.close()

    full_text = ""
    current_tool = ""

    try:
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue

            # Try to parse as JSON (stream-json format)
            try:
                event = json.loads(line)
                etype = event.get("type", "")

                if etype == "assistant":
                    # Full assistant message with content blocks
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "text" and block.get("text"):
                            text = block["text"]
                            full_text += text
                            session.messages.append(ChatMessage(role="assistant", content=text))
                            yield {"type": "text", "content": text}
                        elif block.get("type") == "tool_use":
                            current_tool = block.get("name", "")
                            args = block.get("input", {})
                            session.messages.append(
                                ChatMessage(role="tool_call", tool_name=current_tool, tool_args=args, content="")
                            )
                            yield {"type": "tool_call", "name": current_tool, "args": args}
                            yield {"type": "activity", "content": f"⚡ {current_tool}..."}

                elif etype == "content_block_start":
                    cb = event.get("content_block", {})
                    if cb.get("type") == "tool_use":
                        current_tool = cb.get("name", "")
                        yield {"type": "tool_call", "name": current_tool, "args": cb.get("input", {})}
                        yield {"type": "activity", "content": f"⚡ {current_tool}..."}
                    elif cb.get("type") == "text":
                        yield {"type": "activity", "content": "💬 Writing..."}

                elif etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        text = delta["text"]
                        full_text += text
                        yield {"type": "text", "content": text}

                elif etype == "result":
                    # Final result
                    for block in event.get("result", {}).get("content", []):
                        if block.get("type") == "text" and block.get("text"):
                            text = block["text"]
                            if text not in full_text:
                                full_text += text
                                session.messages.append(ChatMessage(role="assistant", content=text))
                                yield {"type": "text", "content": text}

                elif etype == "tool_result":
                    result_text = ""
                    for block in event.get("content", []):
                        if block.get("type") == "text":
                            result_text += block.get("text", "")
                    if result_text:
                        session.messages.append(
                            ChatMessage(role="tool_result", content=result_text[:500], tool_name=current_tool)
                        )
                        yield {"type": "tool_result", "name": current_tool, "result": result_text[:500]}
                    yield {"type": "activity", "content": "🤔 Thinking..."}

                continue
            except json.JSONDecodeError:
                pass

            # Not JSON — plain text line (fallback for --print without stream-json)
            if line and line not in full_text:
                full_text += line + "\n"

    except Exception as e:
        yield {"type": "error", "content": f"Stream error: {e}"}

    # Wait for process to finish
    _active_procs.pop(session.id, None)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    # If streaming didn't produce output, fall back to --print
    if not full_text:
        yield {"type": "activity", "content": "⏳ Fallback mode..."}
        try:
            proc2 = subprocess.run(
                ["claude", "--print", "--model", session.model or "sonnet", "--dangerously-skip-permissions"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(__import__("pathlib").Path(__file__).parent.parent.parent),
                env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
            )
            if proc2.stdout.strip():
                session.messages.append(ChatMessage(role="assistant", content=proc2.stdout.strip()))
                yield {"type": "text", "content": proc2.stdout.strip()}
            elif proc2.stderr:
                yield {"type": "error", "content": proc2.stderr[:500]}
        except subprocess.TimeoutExpired:
            yield {"type": "error", "content": "Claude Code timed out (5min)"}

    yield {"type": "done"}


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

                result = execute_tool(tool_name, tool_args)
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
        "open_app":   ("launch_app",  {"app_name": "package"}),
        "click":      ("tap",         {"x": "x", "y": "y"}),
        "tap":        ("tap",         {}),
        "long_press": ("long_press",  {}),
        "type_text":  ("input_text",  {"text": "text"}),
        "input_text": ("input_text",  {}),
        "swipe":      ("swipe",       {}),
        "key_event":  ("key_event",   {"key": "key"}),
        "screenshot": ("screenshot",  {}),
        "wait":       ("wait",        {"duration_ms": "ms"}),
        "force_stop": ("force_stop",  {}),
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
            tool_name = call.get("tool", "")
            # Two shapes seen in the wild:
            #   {"tool": "X", "args": {...}}            (gemma-4-e2b, llama)
            #   {"tool": "X", "package": "...", ...}    (ghost-gemma, qwen)
            # Accept both: prefer nested args, else take the rest of the dict as kwargs.
            raw_args = call.get("args")
            if isinstance(raw_args, dict):
                tool_args = dict(raw_args)
            else:
                tool_args = {k: v for k, v in call.items() if k != "tool"}
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
