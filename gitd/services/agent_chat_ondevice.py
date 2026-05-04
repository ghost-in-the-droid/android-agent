"""On-device LLM provider — runs Gemma (or any registered model) via MediaPipe.

Bridges to Kotlin singleton `OnDeviceLLM` through Chaquopy. Falls back gracefully
when running outside Chaquopy (e.g., dev tests on a Mac).

Model selection:
    session.model is the registry id, e.g. "gemma-4-e2b-it" / "gemma-2-2b-it".
"""

from __future__ import annotations

from typing import Iterator

from gitd.services.agent_chat import (
    DEFAULT_SYSTEM,
    MAX_TURNS,
    ChatMessage,
    ChatSession,
    _parse_tool_calls,
)
from gitd.services.agent_tools import TOOLS, execute_tool
from gitd.services.device_context import get_phone_state, get_screen_tree
from gitd.services.observability import (
    record_generation,
    record_tool_result,
    set_trace_output,
    trace_chat_turn,
)


def _kotlin_llm():
    """Return the Kotlin OnDeviceLLM singleton, or None if Chaquopy is missing."""
    try:
        from java import jclass  # type: ignore[import-not-found]
        return jclass("com.ghostinthedroid.app.ondevice.OnDeviceLLM").INSTANCE
    except Exception:
        return None


def chat_ondevice(session: ChatSession, user_message: str) -> Iterator[dict]:
    """Run a tool-using turn against an on-device Gemma model."""
    session.messages.append(ChatMessage(role="user", content=user_message))

    llm = _kotlin_llm()
    if llm is None:
        yield {
            "type": "error",
            "content": "On-device LLM only available inside the ghost-app (Chaquopy bridge missing)",
        }
        return

    model_id = session.model or "gemma-3-1b-it"

    yield {"type": "activity", "content": f"🧠 Loading {model_id}..."}
    try:
        loaded = bool(llm.ensureLoaded(model_id))
    except Exception as e:
        yield {"type": "error", "content": f"On-device load crashed: {e}"}
        return
    if not loaded:
        yield {
            "type": "error",
            "content": (
                f"Model '{model_id}' not downloaded yet. "
                f"Open Settings → On-Device → Download to fetch it (~1-3 GB)."
            ),
        }
        return

    yield {"type": "activity", "content": "📱 Reading screen..."}
    screen_block = ""
    try:
        tree = get_screen_tree(session.device)
        state = get_phone_state(session.device)
        screen_block = f"\n\n[Screen]\n{tree[:1500]}\n[App: {state.get('currentApp', '?')}]"
    except Exception:
        pass

    tool_list = "\n".join(
        f"- {t['name']}: {t['description']}  params: {list(t.get('input_schema', {}).get('properties', {}).keys())}"
        for t in TOOLS
    )
    system = DEFAULT_SYSTEM.replace("{tool_list}", tool_list)

    # Prompt structure tuned for KV prefix reuse:
    #   [SYSTEM]              ← invariant across turns + sessions
    #   {tools list}          ← invariant
    #   [USER]                ← invariant
    #   Device: ...           ← invariant per session
    #   {user_message}        ← changes per turn (small)
    #   [Screen]              ← changes per turn (large)
    #   {screen tree}
    # Putting the dynamic screen tree LAST means the long stable prefix
    # (system + tools + device + user message) is fully cached on every
    # subsequent turn, even when the screen state changes between turns.
    # NOTE: warmup() exists on OnDeviceLLM and bakes the stable system+tools
    # prefix into the KV cache before any user input — but it has to run
    # BEFORE this chat call, in the background at app start. Calling it
    # inline here just serialises the cold prefill in front of the user's
    # first response, doubling the perceived latency. The right wiring is
    # a Kotlin coroutine in MainActivity that fires `OnDeviceLLM.warmup(
    # selected_model_id, stable_prefix)` right after the on-device model is
    # selected. With that in place, the first chat turn lands at ~13 s
    # instead of ~140 s, same as turn 2+. For now the unwired path gives
    # turn-2+ the 10× win and the user pays the cold cost on turn 1.

    history: list[str] = [
        f"[SYSTEM]\n{system}",
        f"[USER]\nDevice: {session.device}\n\n{user_message}{screen_block}",
    ]

    with trace_chat_turn(
        session_id=getattr(session, "id", "") or "",
        user_message=user_message,
        provider="on-device",
        model=model_id,
        device=session.device,
        source="android",  # this code path runs inside Chaquopy on the phone
    ) as trace:
        last_reply = ""
        for turn in range(MAX_TURNS):
            prompt = "\n\n".join(history) + "\n\n[ASSISTANT]\n"
            yield {"type": "activity", "content": f"🧠 Inferring (turn {turn + 1})..."}

            # Try streaming first — yields token-by-token so the UI can show
            # the response building char-by-char ("ghost is typing"). Falls
            # back to one-shot generate if the JNI doesn't expose the
            # streaming API yet (MediaPipe runtime, older builds).
            reply = ""
            streamed = False
            try:
                if int(llm.generateStart(model_id, prompt)) > 0:
                    streamed = True
                    while True:
                        piece = str(llm.generateStep())
                        # JNI sentinel for end-of-stream is a single NUL byte.
                        if piece == "" or piece == "\x00":
                            break
                        reply += piece
                        yield {"type": "text_delta", "content": piece}
            except Exception as e:
                yield {"type": "error", "content": f"On-device streaming error: {e}"}
                return

            if not streamed:
                # Fallback: one-shot generate (no live streaming).
                try:
                    reply = str(llm.generate(model_id, prompt))
                except Exception as e:
                    yield {"type": "error", "content": f"On-device inference error: {e}"}
                    return

            # Native error sentinel — surface and stop.
            if reply.startswith("[on-device error") or reply.startswith("[llama_jni:"):
                yield {"type": "error", "content": reply}
                return
            # Empty reply = model emitted EOG/<end_of_turn> as the first token.
            # That means "no further actions" — finish the turn cleanly rather
            # than treating it as a failure.
            if not reply.strip():
                break

            session.messages.append(ChatMessage(role="assistant", content=reply))
            # Final full-text event for clients that didn't subscribe to
            # text_delta deltas (or to keep the protocol backward-compatible).
            yield {"type": "text", "content": reply}
            history.append(f"[ASSISTANT]\n{reply}")
            record_generation(trace, model=model_id, prompt=prompt, output=reply)
            last_reply = reply

            tool_calls = _parse_tool_calls(reply)
            if not tool_calls:
                break

            tool_results = []
            for call in tool_calls:
                tool_name = call.get("tool", "")
                tool_args = call.get("args", {})
                tool_args.setdefault("device", session.device)

                session.messages.append(
                    ChatMessage(role="tool_call", tool_name=tool_name, tool_args=tool_args, content="")
                )
                yield {"type": "tool_call", "name": tool_name, "args": tool_args}
                yield {"type": "activity", "content": f"⚡ {tool_name}..."}

                span = trace.span(name=f"tool:{tool_name}", input={"args": tool_args}) if trace else None
                try:
                    result = execute_tool(tool_name, tool_args)
                    session.messages.append(
                        ChatMessage(role="tool_result", content=result[:500], tool_name=tool_name)
                    )
                    yield {"type": "tool_result", "name": tool_name, "result": result[:500]}
                    tool_results.append(f"[{tool_name}] {result[:800]}")
                    record_tool_result(span, result)
                except Exception as e:
                    err = f"Tool error: {e}"
                    session.messages.append(
                        ChatMessage(role="tool_result", content=err, tool_name=tool_name)
                    )
                    yield {"type": "tool_result", "name": tool_name, "result": err}
                    tool_results.append(f"[{tool_name}] ERROR: {err}")
                    record_tool_result(span, err, error=True)

            history.append("[USER]\nTool results:\n" + "\n".join(tool_results))

        set_trace_output(trace, last_reply)

    yield {"type": "done"}
