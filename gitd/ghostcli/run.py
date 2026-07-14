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

# Per-tool emoji for the streamed tool-call line. Without this every call renders
# the same generic 🧰 and a demo reads as a flat wall; a distinct glyph per action
# makes the agent's moves legible at a glance. Unmapped tools fall back to 🧰.
_TOOL_EMOJI = {
    # input / interaction
    "tap": "👆", "tap_element": "👆", "long_press": "🤏",
    "type_text": "⌨️", "type_unicode": "⌨️", "paste_text": "📋",
    "press_key": "🎹", "press_back": "🔙", "press_home": "🏠", "browser_back": "🔙",
    "swipe": "📜",
    # screen / vision
    "screenshot": "📸", "screenshot_annotated": "📸", "screenshot_cropped": "📸",
    "screenshot_sequence": "🎞️", "get_screen_tree": "🌲", "get_screen_xml": "📄",
    "get_elements": "🔲", "classify_screen": "🧠", "find_on_screen": "🔍",
    "ocr_screen": "🔠", "ocr_region": "🔠",
    "extract_visible_text": "📃", "extract_articles": "📰", "read_news": "📰",
    # apps / navigation
    "launch_app": "🚀", "launch_intent": "🚀", "force_stop": "🛑",
    "list_apps": "📱", "list_packages": "📦", "search_apps": "🔎", "app_state": "ℹ️",
    "open_url": "🌐", "get_current_url": "🔗",
    # device / system
    "list_devices": "📱", "device_health": "🩺", "fix_device_health": "🔧",
    "get_phone_state": "📊", "shell": "⚙️", "wait": "⏳", "wait_for_text": "⏳",
    "speak_text": "🔊", "open_camera": "📷",
    # notifications / clipboard
    "get_notifications": "🔔", "open_notifications": "🔔", "clear_notifications": "🔕",
    "clipboard_get": "📋", "clipboard_set": "📋",
    # recording / stream
    "start_screen_recording": "⏺️", "stop_screen_recording": "⏹️",
    "screen_recording_status": "📹", "get_stream_info": "📡",
    # web / search
    "web_search": "🔎",
    # skills / agent orchestration
    "list_skills": "🧩", "create_skill": "✨", "run_action": "▶️", "explore_app": "🧭",
    "chain": "⛓️", "sub_agent": "🤖", "run_flow": "🔀", "run_workflow": "🔀",
    "toggle_overlay": "🖼️",
    # crashes
    "list_crashes": "💥", "get_crash": "💥",
    # crm / leads
    "lookup_lead": "🔎", "list_unread_leads": "📥",
    "crm_lookup_contact": "🔎", "crm_list_unread_messages": "📥",
}


def _tool_emoji(name: str) -> str:
    """Emoji for a tool-call line; 🧰 for anything unmapped."""
    return _TOOL_EMOJI.get(name, "🧰")


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
                _emit(f"\n  {_tool_emoji(name)}  {name}\n")
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
