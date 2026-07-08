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
    normalize_tool_call,
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


# ── Gemma chat template ──────────────────────────────────────────────────────
# Gemma 4 uses <start_of_turn>user / <end_of_turn> / <start_of_turn>model
# markers. There's no separate system role — system content is prepended
# into the first user turn. Earlier we used a custom [SYSTEM]/[USER]/[ASSISTANT]
# scaffold, which the model cheerfully echoed back into its own output (it had
# never seen those tokens in fine-tuning), causing repetition loops where the
# model kept "writing" extra fake [USER] turns from inside its own reply.
# Switching to the canonical Gemma markers fixes coherence on multi-turn
# tool chains.


def ondevice_stable_prefix(system: str, device: str) -> str:
    """Stable prefix shared by warmup pre-fill and chat path. Anything beyond
    this point varies per turn and must NOT be in the warmup KV."""
    return f"<start_of_turn>user\n{system}\n\nDevice: {device}\n\n"


def _ondevice_first_turn(system: str, device: str, user_message: str, screen_block: str) -> str:
    return (
        ondevice_stable_prefix(system, device)
        + f"{user_message}{screen_block}<end_of_turn>\n"
        + "<start_of_turn>model\n"
    )


def _ondevice_tool_results_turn(tool_results: list[str]) -> str:
    return (
        "<end_of_turn>\n"
        "<start_of_turn>user\n"
        + "Tool results:\n"
        + "\n".join(tool_results)
        + "<end_of_turn>\n"
        + "<start_of_turn>model\n"
    )


def _kv_cache_path(model_id: str, stable_prefix: str) -> str:
    """Deterministic on-device path for the saved KV state of (model, prefix).
    Mirrors the warmup endpoint's logic so chat and warmup share the same file."""
    import hashlib
    import os

    cache_dir = "/data/data/com.ghostinthedroid.app/files/ondevice/kv-cache"
    os.makedirs(cache_dir, exist_ok=True)
    h = hashlib.sha256()
    h.update(model_id.encode())
    h.update(b"\n")
    h.update(stable_prefix.encode())
    return os.path.join(cache_dir, f"warmup-{h.hexdigest()[:16]}.bin")


def _ensure_kv_warmed(llm, model_id: str, stable_prefix: str) -> tuple[bool, int]:
    """Load the disk-persisted KV state for (model, prefix) into the JNI handle
    if a cache file exists. Returns (from_cache, n_tokens). Caller can fall
    back to a cold prefill via llm.warmup() if from_cache is False; we DON'T
    do that here because it'd add ~4 min latency to a chat turn — leave that
    to the explicit /warmup endpoint that fires from MainActivity at app start."""
    path = _kv_cache_path(model_id, stable_prefix)
    try:
        loaded = int(llm.loadState(model_id, path))
    except Exception:
        loaded = -1
    if loaded > 0:
        return True, loaded
    return False, 0


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
                f"Model '{model_id}' not downloaded yet. Open Settings → On-Device → Download to fetch it (~1-3 GB)."
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

    # If the warmup endpoint previously saved a KV state for this exact
    # (model, system+device) prefix, restore it now so the first generateStart
    # only has to decode the user_message + screen_block diff. Without this,
    # every model switch costs a ~4-minute cold prefill on the first chat
    # because ensureLoaded() doesn't know about the cache file. Idempotent —
    # if no file matches we just continue with an empty KV.
    stable_prefix = ondevice_stable_prefix(system, session.device)
    from_cache, kv_tokens = _ensure_kv_warmed(llm, model_id, stable_prefix)
    if from_cache:
        yield {"type": "activity", "content": f"⚡ KV cache hit ({kv_tokens} tokens)"}

    # Gemma chat template — see ondevice_stable_prefix() and friends above.
    # `prompt` accumulates over turns: the assistant reply + each tool-results
    # turn get appended in-place so the next iteration runs against the full
    # rolling conversation (KV prefix reuse means we only re-decode the diff).
    prompt = _ondevice_first_turn(system, session.device, user_message, screen_block)

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
                        # JNI protocol:
                        #   "\x00"  → end of stream (EOS or stop-tag hit)
                        #   ""      → no new text this step (the streamer is
                        #             holding back bytes that might form a
                        #             stop tag; keep polling)
                        #   anything else → stream as text_delta.
                        if piece == "\x00":
                            break
                        if piece == "":
                            continue
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
            # Append the assistant turn to the rolling conversation so the
            # next iteration sees the full chat history. `reply` already had
            # any trailing <end_of_turn> stripped by the JNI streaming loop;
            # we add it back so the model sees a clean turn boundary.
            prompt += reply
            record_generation(trace, model=model_id, prompt=prompt, output=reply)
            last_reply = reply

            tool_calls = _parse_tool_calls(reply)
            if not tool_calls:
                break

            tool_results = []
            for call in tool_calls:
                tool_name, tool_args = normalize_tool_call(call)
                tool_args.setdefault("device", session.device)

                session.messages.append(
                    ChatMessage(role="tool_call", tool_name=tool_name, tool_args=tool_args, content="")
                )
                yield {"type": "tool_call", "name": tool_name, "args": tool_args}
                yield {"type": "activity", "content": f"⚡ {tool_name}..."}

                span = trace.span(name=f"tool:{tool_name}", input={"args": tool_args}) if trace else None
                try:
                    result = execute_tool(tool_name, tool_args)
                    session.messages.append(ChatMessage(role="tool_result", content=result[:500], tool_name=tool_name))
                    yield {"type": "tool_result", "name": tool_name, "result": result[:500]}
                    tool_results.append(f"[{tool_name}] {result[:800]}")
                    record_tool_result(span, result)
                except Exception as e:
                    err = f"Tool error: {e}"
                    session.messages.append(ChatMessage(role="tool_result", content=err, tool_name=tool_name))
                    yield {"type": "tool_result", "name": tool_name, "result": err}
                    tool_results.append(f"[{tool_name}] ERROR: {err}")
                    record_tool_result(span, err, error=True)

            prompt += _ondevice_tool_results_turn(tool_results)

        set_trace_output(trace, last_reply)

    yield {"type": "done"}
