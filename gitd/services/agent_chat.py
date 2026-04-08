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
    "ollama": {"label": "Ollama (local)", "models": []},
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
    """Kill the running agent subprocess AND all its children."""
    proc = _active_procs.pop(session_id, None)
    if proc:
        try:
            proc.kill()
        except Exception:
            pass
    # Nuclear option: kill ALL claude --print processes (only agent chat uses this)
    # This catches cases where the PID changed (node re-exec) or psutil can't find it
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


def _chat_ollama(session: ChatSession, user_message: str):
    """Use local Ollama model."""
    import requests

    session.messages.append(ChatMessage(role="user", content=user_message))

    context = ""
    try:
        tree = get_screen_tree(session.device)
        state = get_phone_state(session.device)
        context = f"[Screen]\n{tree[:1500]}\n[App: {state.get('currentApp', '?')}]\n\n"
    except Exception:
        pass

    tool_list = "\n".join(f"- {t['name']}: {t['description']}" for t in TOOLS)
    system = DEFAULT_SYSTEM.replace("{tool_list}", tool_list)

    try:
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": session.model or "llama3",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"{context}Device: {session.device}\n\n{user_message}"},
                ],
                "stream": False,
            },
            timeout=120,
        )
        reply = r.json().get("message", {}).get("content", "")

        if reply:
            session.messages.append(ChatMessage(role="assistant", content=reply))
            yield {"type": "text", "content": reply}

            # Parse tool calls from response (same format as claude-code)
            import re

            tool_pattern = re.compile(r"```tool\s*\n(.*?)\n```", re.DOTALL)
            for match in tool_pattern.finditer(reply):
                try:
                    call = json.loads(match.group(1).strip())
                    tool_name = call.get("tool", "")
                    tool_args = call.get("args", {})
                    tool_args.setdefault("device", session.device)
                    result = execute_tool(tool_name, tool_args)
                    yield {"type": "tool_call", "name": tool_name, "args": tool_args}
                    yield {"type": "tool_result", "name": tool_name, "result": result[:500]}
                except Exception:
                    pass
    except Exception as e:
        yield {"type": "error", "content": str(e)}

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
