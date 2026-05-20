"""Claude Code agent chat provider — real-time streaming with tool call visibility."""

import json
import os
import subprocess
import threading

from gitd.services.agent_chat import ChatMessage, ChatSession
from gitd.services.device_context import get_phone_state, get_screen_tree
from gitd.services.observability import (
    record_generation,
    record_tool_result,
    set_trace_output,
    trace_chat_turn,
)


def chat_claude_code(session: ChatSession, user_message: str):
    """Use claude CLI with --print --output-format stream-json --verbose.
    Streams tool calls, text, and usage in real-time."""
    session.messages.append(ChatMessage(role="user", content=user_message))

    yield {"type": "activity", "content": "📱 Reading screen..."}
    context_parts = []
    foreground_pkg = ""
    try:
        state = get_phone_state(session.device)
        if state:
            foreground_pkg = state.get("packageName", "") or ""
            context_parts.append(f"[Foreground app: {state.get('currentApp', '?')} ({foreground_pkg})]")
        # Skip injecting the chat-app's own screen tree — it'd be the user's chat
        # bubble (incl. prior answers) and tempts the model to "answer from screen"
        # instead of actually performing the task.
        if foreground_pkg != "com.ghostinthedroid.app":
            tree = get_screen_tree(session.device)
            if tree and tree != "(empty screen)":
                context_parts.append(f"[Current screen]\n{tree[:1500]}")
    except Exception:
        pass
    context = "\n".join(context_parts)

    prompt = f"""You are controlling Android phone serial={session.device}.
{context}

Task: {user_message}

Rules:
- The phone is currently showing the chat app the user is talking to you from. You MUST actually drive the phone to complete the task — do not answer from memory or prior conversation context.
- Use the MCP android-agent tools (launch_app, tap_element, get_screen_tree, screenshot, swipe, etc.) to control the phone.
- For app tasks, start with `launch_app` to open the target app. Do not assume any app is already open.
- After each action, verify the new state with `get_screen_tree` or `screenshot`.
- Only after you've actually observed the result on the phone, answer the user. Be concise."""

    yield {"type": "activity", "content": "🧠 Starting Claude Code..."}

    project_dir = str(__import__("pathlib").Path(__file__).parent.parent.parent)

    # On-device: proxy to remote host that has claude CLI + MCP tools
    remote_host = os.environ.get("GHOST_REMOTE_HOST", "")
    if remote_host or not __import__("shutil").which("claude"):
        yield from _chat_claude_code_remote(session, prompt, remote_host or "http://localhost:5055")
        return

    try:
        proc = subprocess.Popen(
            [
                "claude",
                "--print",
                "--model",
                session.model or "sonnet",
                "--output-format",
                "stream-json",
                "--verbose",
                "--dangerously-skip-permissions",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            cwd=project_dir,
            env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
            # New session so we can SIGTERM the whole process group (claude
            # spawns node + MCP-tool child processes; killing just the parent
            # leaves those orphaned and still tapping the phone).
            start_new_session=True,
        )
    except FileNotFoundError:
        yield {"type": "error", "content": "claude CLI not found. Set GHOST_REMOTE_HOST to proxy."}
        return

    # Register so the /stop/{sid} endpoint can find this proc by session id
    # without relying on the nuclear `pkill -f claude.*--print...` fallback.
    from gitd.services.agent_chat import _active_procs

    _active_procs[session.id] = proc

    proc.stdin.write(prompt)
    proc.stdin.close()

    # Open Langfuse trace for this turn (no-op if observability disabled)
    _trace_cm = trace_chat_turn(
        session_id=getattr(session, "id", "") or "",
        user_message=user_message,
        provider="claude-code",
        model=session.model or "sonnet",
        device=session.device,
        source="mac",
    )
    trace = _trace_cm.__enter__()
    tool_spans: dict[str, object] = {}  # tool_use_id → span

    # Read stdout lines in a thread so we can yield events as they arrive
    lines_queue: list[str] = []
    finished = threading.Event()

    def _reader():
        try:
            for line in proc.stdout:
                lines_queue.append(line.rstrip())
        except Exception:
            pass
        finished.set()

    threading.Thread(target=_reader, daemon=True).start()

    processed_idx = 0
    full_text = ""
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    while not finished.is_set():
        finished.wait(timeout=0.5)

        while processed_idx < len(lines_queue):
            line = lines_queue[processed_idx]
            processed_idx += 1
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "system" and event.get("subtype") == "init":
                # Init event — shows connected MCP servers and tools
                mcp_servers = event.get("mcp_servers", [])
                connected = [s["name"] for s in mcp_servers if s.get("status") == "connected"]
                if connected:
                    yield {"type": "activity", "content": f"🔌 MCP: {', '.join(connected)}"}

            elif etype == "assistant":
                msg = event.get("message", {})
                content_blocks = msg.get("content", [])
                usage = msg.get("usage", {})

                # Update token counts
                if usage:
                    total_input_tokens = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                    total_output_tokens = usage.get("output_tokens", 0)
                    yield {"type": "tokens", "input": total_input_tokens, "output": total_output_tokens}

                for block in content_blocks:
                    btype = block.get("type", "")

                    if btype == "text" and block.get("text"):
                        text = block["text"]
                        if text not in full_text:
                            full_text += text
                            session.messages.append(ChatMessage(role="assistant", content=text))
                            yield {"type": "text", "content": text}

                    elif btype == "tool_use":
                        tool_name = block.get("name", "")
                        tool_args = block.get("input", {})
                        tool_id = block.get("id", "")
                        # Strip mcp prefix for display
                        display_name = (
                            tool_name.replace("mcp__android-agent__", "")
                            .replace("mcp__playwright__", "pw/")
                            .replace("mcp__claude_ai_Gmail__", "gmail/")
                        )
                        session.messages.append(
                            ChatMessage(role="tool_call", tool_name=display_name, tool_args=tool_args, content="")
                        )
                        yield {"type": "tool_call", "name": display_name, "args": tool_args}
                        yield {"type": "activity", "content": f"⚡ {display_name}..."}
                        if trace is not None and tool_id:
                            try:
                                tool_spans[tool_id] = trace.span(name=f"tool:{display_name}", input={"args": tool_args})
                            except Exception:
                                pass

                    elif btype == "tool_result":
                        content_parts = block.get("content", [])
                        result_text = ""
                        for cp in content_parts if isinstance(content_parts, list) else []:
                            if isinstance(cp, dict) and cp.get("type") == "text":
                                result_text += cp.get("text", "")
                            elif isinstance(cp, str):
                                result_text += cp
                        if result_text:
                            session.messages.append(ChatMessage(role="tool_result", content=result_text[:500]))
                            yield {"type": "tool_result", "name": "", "result": result_text[:300]}
                        is_err = bool(block.get("is_error"))
                        record_tool_result(
                            tool_spans.pop(block.get("tool_use_id", ""), None),
                            result_text,
                            error=is_err,
                        )
                        yield {"type": "activity", "content": "🤔 Thinking..."}

                    elif btype == "thinking":
                        # Extended thinking — surface the actual reasoning text
                        # so the UI can render it (in addition to the activity ping).
                        thinking_text = block.get("thinking", "")
                        if thinking_text:
                            # Persist alongside text/tool_use blocks so it survives
                            # save_session_to_db and reappears on resumeConversation —
                            # otherwise thinking bubbles are live-only and vanish.
                            session.messages.append(ChatMessage(role="thinking", content=thinking_text))
                            yield {"type": "thinking", "content": thinking_text}
                        else:
                            yield {"type": "activity", "content": "🧠 Reasoning..."}

            elif etype == "result":
                # Final result with cost info
                usage = event.get("usage", {})
                total_cost = event.get("total_cost_usd", 0)
                total_input_tokens = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                total_output_tokens = usage.get("output_tokens", 0)
                yield {"type": "tokens", "input": total_input_tokens, "output": total_output_tokens, "cost": total_cost}

                # Final text result
                result_text = event.get("result", "")
                if result_text and result_text not in full_text:
                    full_text += result_text
                    session.messages.append(ChatMessage(role="assistant", content=result_text))
                    yield {"type": "text", "content": result_text}

    # Process remaining
    while processed_idx < len(lines_queue):
        line = lines_queue[processed_idx]
        processed_idx += 1
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "result":
                result_text = event.get("result", "")
                total_cost = event.get("total_cost_usd", 0)
                if result_text and result_text not in full_text:
                    session.messages.append(ChatMessage(role="assistant", content=result_text))
                    yield {"type": "text", "content": result_text}
                yield {"type": "tokens", "input": total_input_tokens, "output": total_output_tokens, "cost": total_cost}
        except json.JSONDecodeError:
            pass

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    # Unregister now that the process is done — leaving a stale entry would
    # make a later stop_agent try to killpg() a dead pid (harmless, but
    # noisy in logs).
    _active_procs.pop(session.id, None)

    # Record final generation + close trace
    try:
        set_trace_output(trace, full_text)
        record_generation(
            trace,
            model=session.model or "sonnet",
            prompt=prompt,
            output=full_text,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_usd=total_cost,
        )
    finally:
        try:
            _trace_cm.__exit__(None, None, None)
        except Exception:
            pass

    if not full_text:
        yield {"type": "error", "content": "No response from Claude Code"}

    yield {"type": "done"}


def _chat_claude_code_remote(session, prompt: str, remote_host: str):
    """Proxy Claude Code request to a remote host running the ghost backend.

    The remote host has `claude` CLI + MCP android-agent tools configured.
    Tool calls from Claude Code execute on the remote host's MCP server,
    which talks to the device via ADB (USB or wireless).

    We open a *shadow* trace on the phone side too, mirroring the events as
    they stream past — so the in-app Traces tab shows claude-code runs even
    though the real LLM trace lives on the Mac. Without this, the tab would
    appear empty for everything except on-device runs.
    """
    import requests

    # Open phone-local trace so the in-app Traces tab sees this run.
    _trace_cm = trace_chat_turn(
        session_id=getattr(session, "id", "") or "",
        user_message=prompt[-2000:],  # the prompt has full screen context — keep tail
        provider="claude-code",
        model=session.model or "sonnet",
        device=session.device,
        source="android",  # this code runs in Chaquopy
    )
    trace = _trace_cm.__enter__()
    open_spans: dict[str, object] = {}  # last-tool-name → span (best-effort match since remote events lack ids)
    full_text = ""
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    yield {"type": "activity", "content": f"🔗 Connecting to {remote_host}..."}

    # When the phone user hits Stop, this generator gets GeneratorExit. We
    # need to propagate that to the Mac so its claude subprocess actually
    # dies — closing our `requests` connection alone isn't enough because
    # Mac's chat_claude_code generator only notices the broken pipe AFTER
    # claude has streamed its current chunk (which may include several more
    # tool calls). The fix: capture Mac's session_id from the first SSE
    # `session` event, and on GeneratorExit POST to Mac's /stop/{sid}.
    remote_sid: str = ""
    resp = None
    try:
        resp = requests.post(
            f"{remote_host}/api/agent-chat/message",
            json={
                "content": prompt,
                "device": session.device,
                "provider": "claude-code",
                "model": session.model or "sonnet",
            },
            timeout=300,
            stream=True,
        )

        for line in resp.iter_lines():
            if not line:
                continue
            text_line = line.decode()
            if text_line.startswith("data: "):
                try:
                    event = json.loads(text_line[6:])
                    etype = event.get("type", "")

                    if etype == "session":
                        # First event from Mac carries the remote session_id.
                        # Capture it so a phone-side Stop can hit Mac's
                        # /stop/{sid} endpoint and actually kill the claude
                        # subprocess.
                        remote_sid = event.get("session_id", "") or ""
                        yield event
                    elif etype == "text":
                        chunk = event.get("content", "")
                        full_text += chunk
                        session.messages.append(ChatMessage(role="assistant", content=chunk))
                        yield event
                    elif etype == "tool_call":
                        tool_name = event.get("name", "")
                        tool_args = event.get("args", {})
                        session.messages.append(
                            ChatMessage(
                                role="tool_call",
                                tool_name=tool_name,
                                tool_args=tool_args,
                                content="",
                            )
                        )
                        if trace is not None:
                            try:
                                open_spans[tool_name] = trace.span(name=f"tool:{tool_name}", input={"args": tool_args})
                            except Exception:
                                pass
                        yield event
                    elif etype == "tool_result":
                        result_text = event.get("result", "")
                        tool_name = event.get("name", "")
                        session.messages.append(
                            ChatMessage(role="tool_result", content=result_text, tool_name=tool_name)
                        )
                        # The remote stream sends tool_result without a tool_id;
                        # close the most recent span for that tool name.
                        span = open_spans.pop(tool_name, None) or (open_spans.popitem()[1] if open_spans else None)
                        record_tool_result(span, result_text)
                        yield event
                    elif etype == "tokens":
                        total_input_tokens = int(event.get("input", 0) or 0)
                        total_output_tokens = int(event.get("output", 0) or 0)
                        total_cost = float(event.get("cost", 0) or 0)
                        yield event
                    elif etype == "thinking":
                        thinking_text = event.get("content", "")
                        if thinking_text:
                            session.messages.append(ChatMessage(role="thinking", content=thinking_text))
                        yield event
                    elif etype in ("activity", "screenshot", "error"):
                        yield event
                    elif etype == "done":
                        break
                except json.JSONDecodeError:
                    pass

    except GeneratorExit:
        # Phone user hit Stop. Propagate to Mac so its claude subprocess
        # actually dies — without this, Mac keeps streaming tool calls and
        # the phone keeps getting tapped even though the UI says "stopped".
        if remote_sid:
            try:
                requests.post(
                    f"{remote_host}/api/agent-chat/stop/{remote_sid}",
                    timeout=4,
                )
            except Exception:
                pass
        raise
    except requests.ConnectionError:
        yield {"type": "error", "content": f"Cannot reach {remote_host}. Start the backend on your Mac: python3 run.py"}
    except Exception as e:
        yield {"type": "error", "content": str(e)}
    finally:
        # Always close the upstream HTTP stream so Mac's send_message
        # finally-block fires (which calls stop_agent on its session).
        try:
            if resp is not None:
                resp.close()
        except Exception:
            pass
        try:
            set_trace_output(trace, full_text)
            record_generation(
                trace,
                model=session.model or "sonnet",
                prompt=prompt[-4000:],
                output=full_text,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                cost_usd=total_cost,
            )
        finally:
            try:
                _trace_cm.__exit__(None, None, None)  # noqa: E701
            except Exception:
                pass  # noqa: E701

    yield {"type": "done"}
