"""The bare-positional prompt path: ``ghost "<prompt>" --device asus``.

Thin driver — creates a chat session and streams :func:`chat_turn` events to the
terminal. All the real work (provider dispatch, tools, the agent loop) lives in
``gitd.services.agent_chat``; this only renders.
"""

from __future__ import annotations

import sys
import time

# mode → whether to attach screenshots to the model's perception. `reason` also
# gets vision today; effort-scaling is a later refinement.
_MODE_AUTOSHOT = {"fast": False, "vision": True, "reason": True}


def _emit(text: str, *, end: str = "") -> None:
    sys.stdout.write(text + end)
    sys.stdout.flush()


def run_task(prompt: str, device_ref: str, provider: str, model: str, mode: str, *, auto_picked: bool = False) -> int:
    """Run one NL task end-to-end. Returns a process exit code."""
    from gitd.services.agent_chat import chat_turn, create_session

    if auto_picked:
        _emit(f"⚠️  using the only connected device: {device_ref}\n")
    _emit(f"⚡  Model:   {model} (via {provider})\n")
    _emit(f"📱  Device:  {device_ref}\n\n")

    session = create_session(device=device_ref, provider=provider, model=model)
    session.auto_screenshot = _MODE_AUTOSHOT.get(mode, False)

    started = time.monotonic()
    tool_calls = 0
    had_error = False
    try:
        for event in chat_turn(session, prompt):
            etype = event.get("type")
            if etype == "text":
                _emit(str(event.get("content") or event.get("text") or ""))
            elif etype == "tool_call":
                tool_calls += 1
                name = event.get("name") or event.get("tool") or "tool"
                _emit(f"\n  🧰  {name}\n")
            elif etype == "thinking":
                pass  # keep the terminal clean; thinking is not surfaced
            elif etype == "error":
                had_error = True
                _emit(f"\n✗ {event.get('content') or event.get('error') or 'error'}\n")
            elif etype == "done":
                break
    except KeyboardInterrupt:
        _emit("\n⏹  interrupted\n")
        return 130
    except Exception as e:  # noqa: BLE001 — surface any run failure as a clean CLI error
        _emit(f"\n✗ run failed: {e}\n")
        return 1

    elapsed = time.monotonic() - started
    _emit(
        f"\n\n{'✗' if had_error else '✓'} done in {elapsed:.0f}s · {tool_calls} tool call{'s' if tool_calls != 1 else ''}\n"
    )
    return 1 if had_error else 0
