"""One-shot vision sub-agent — a fresh LLM call over cached frames (bencher #4).

For image-heavy subtasks (transcribing a playing video, reading a burst of
frames) the master agent shouldn't carry N screenshots in its own context. This
spawns a SEPARATE, stateless Anthropic vision call over the frames and returns
only its text answer, keeping the master's context lean.

Pairs with ``screenshot_sequence`` (bencher #5), which captures the frames via
per-frame screencap and caches them for this to read.

Backend: the Anthropic API (the vision path). Requires ``ANTHROPIC_API_KEY`` — if
absent (e.g. running under the claude-code subscription provider, which has no API
key), it degrades gracefully with an explanatory string rather than raising, so a
master turn that calls it never crashes.

Cost note: each call sends up to ``MAX_SUB_AGENT_FRAMES`` images to the API. Frames
are subsampled to the caller's ``max_frames`` (capped here) to bound spend.
"""

from __future__ import annotations

import os

SUB_AGENT_PROMPT = (
    "You are a focused vision sub-agent. You are given a set of image frames (in "
    "time order) and a task from the main agent. Do ONLY that task and reply with a "
    "concise, exact result — no preamble, no explanation. For transcription: output "
    "exactly what is asked (e.g. the comma-separated strings in order), reading each "
    "frame's text character-for-character. If consecutive frames show the same text, "
    "list it ONCE."
)

# Cost/latency ceiling: never send more than this many images in one sub-call,
# regardless of what the caller asks for.
MAX_SUB_AGENT_FRAMES = 60

# Vision-capable default; override with SUB_AGENT_MODEL. Sonnet is a good
# cost/quality point for frame transcription (cheaper than Opus, strong vision).
_DEFAULT_MODEL = "claude-sonnet-5"


def _model() -> str:
    return os.environ.get("SUB_AGENT_MODEL", "").strip() or _DEFAULT_MODEL


def _subsample(frames: list[str], max_frames: int) -> list[str]:
    """Uniformly subsample ``frames`` down to at most ``max_frames`` (order-preserving)."""
    cap = max(1, min(int(max_frames), MAX_SUB_AGENT_FRAMES))
    if len(frames) <= cap:
        return list(frames)
    idxs = sorted({int(i * len(frames) / cap) for i in range(cap)})
    return [frames[i] for i in idxs]


def _anthropic_vision_call(system: str, content: list, model: str) -> str:
    """Single stateless Anthropic vision call; returns the concatenated text.

    Separated out so tests can monkeypatch it without an API key or network.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    parts = [block.text for block in resp.content if getattr(block, "type", None) == "text"]
    return "".join(parts).strip()


def run_sub_agent(task: str, frames_b64: list[str], *, model: str | None = None, max_frames: int = 60) -> str:
    """Run the vision sub-agent over ``frames_b64`` for ``task``; return its text.

    Never raises: missing key / API errors come back as an explanatory string so a
    master agent turn keeps going. Frames are base64 JPEG (as produced by
    ``get_screenshot_b64`` / ``screenshot_sequence``).
    """
    if not task or not task.strip():
        return "sub_agent: missing 'task'"
    if not frames_b64:
        return "sub_agent: no frames available — run screenshot_sequence first"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return (
            "sub_agent unavailable: no ANTHROPIC_API_KEY set. sub_agent runs a one-shot "
            "Anthropic vision call, which needs an API key (it is not available under the "
            "claude-code subscription provider). Set ANTHROPIC_API_KEY to enable it."
        )

    frames = _subsample(frames_b64, max_frames)
    content: list = []
    for i, fb in enumerate(frames):
        content.append({"type": "text", "text": f"[Frame {i + 1}/{len(frames)}]"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": fb}})
    content.append({"type": "text", "text": task})

    try:
        answer = _anthropic_vision_call(SUB_AGENT_PROMPT, content, model or _model())
    except Exception as e:  # noqa: BLE001 — surfaced to the master as text, never crashes the turn
        return f"sub_agent error: {e}"
    return answer or "sub_agent: (empty response)"
