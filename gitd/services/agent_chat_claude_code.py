"""Claude Code agent chat provider — real-time streaming with tool call visibility."""
import json
import os
import subprocess
import threading
import time

from gitd.services.agent_chat import ChatMessage, ChatSession
from gitd.services.device_context import get_screen_tree, get_phone_state


def chat_claude_code(session: ChatSession, user_message: str):
    """Use claude CLI with --print --output-format stream-json --verbose.
    Streams tool calls, text, and usage in real-time."""
    session.messages.append(ChatMessage(role="user", content=user_message))

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

    prompt = f"""You are controlling Android phone serial={session.device}.
{context}

Task: {user_message}

You have MCP android-agent tools. Use them to accomplish the task.
After each action, verify with get_screen_tree or screenshot.
Keep going until done. Be concise."""

    yield {"type": "activity", "content": "🧠 Starting Claude Code..."}

    project_dir = str(__import__("pathlib").Path(__file__).parent.parent.parent)

    try:
        proc = subprocess.Popen(
            ["claude", "--print", "--model", session.model or "sonnet",
             "--output-format", "stream-json", "--verbose",
             "--dangerously-skip-permissions"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1,
            cwd=project_dir,
            env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        )
    except FileNotFoundError:
        yield {"type": "error", "content": "claude CLI not found"}
        return

    proc.stdin.write(prompt)
    proc.stdin.close()

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
    seen_text_len = 0  # track how much text we've already yielded to avoid duplicates
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
                        # Strip mcp prefix for display
                        display_name = tool_name.replace("mcp__android-agent__", "").replace("mcp__playwright__", "pw/").replace("mcp__claude_ai_Gmail__", "gmail/")
                        session.messages.append(ChatMessage(role="tool_call", tool_name=display_name, tool_args=tool_args, content=""))
                        yield {"type": "tool_call", "name": display_name, "args": tool_args}
                        yield {"type": "activity", "content": f"⚡ {display_name}..."}

                    elif btype == "tool_result":
                        content_parts = block.get("content", [])
                        result_text = ""
                        for cp in (content_parts if isinstance(content_parts, list) else []):
                            if isinstance(cp, dict) and cp.get("type") == "text":
                                result_text += cp.get("text", "")
                            elif isinstance(cp, str):
                                result_text += cp
                        if result_text:
                            session.messages.append(ChatMessage(role="tool_result", content=result_text[:500]))
                            yield {"type": "tool_result", "name": "", "result": result_text[:300]}
                        yield {"type": "activity", "content": "🤔 Thinking..."}

                    elif btype == "thinking":
                        # Extended thinking — show brief activity
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

    if not full_text:
        yield {"type": "error", "content": "No response from Claude Code"}

    yield {"type": "done"}
