"""Rate-limit backoff + effort-scaled timeouts for LLM calls.

Purely additive robustness: on a clean call these helpers are a passthrough;
they only change behaviour when a provider raises a rate-limit / overloaded
error, in which case we wait and retry instead of failing the turn.

Distilled from the AndroidWorld agent harness (`_call_claude` / `_is_rate_limited`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

# Exponential backoff schedule (seconds). A run that trips the API's rate limit
# waits progressively longer rather than giving up on the first 429.
DEFAULT_BACKOFF = (15, 30, 60, 120, 240)

# Shorter schedule for INTERACTIVE (SSE) chats: a long silent wait makes idle
# proxies drop the stream and the UI look dead. Cap total backoff at ~105s and
# let the user retry rather than stalling a live chat for minutes.
INTERACTIVE_BACKOFF = (15, 30, 60)

# Max SSE silence during a backoff wait. Waits longer than this are sliced so a
# keepalive activity event goes out at least this often, keeping proxies + UI
# from treating the stream as dead mid-wait.
KEEPALIVE_SLICE_S = 10

_RATE_LIMIT_MARKERS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "429",
    "overloaded",
    "retry-after",
    "usage limit",
    "too many requests",
    "quota",
    "529",
)

# Wall-clock ceiling for a single LLM call, scaled by model tier. A bigger model
# reasons longer, so a fixed short timeout would cut it off mid-thought; a small
# model that hasn't returned in minutes is hung. Mirrors the effort→seconds map
# in the AW harness, keyed on Ghost's model names instead of an effort flag.
_EFFORT_TIMEOUTS = {
    "opus": 420,
    "sonnet": 300,
    "haiku": 240,
}
# Fallback for models we don't recognise (vLLM/gemma, on-device, future ids).
# MUST stay >= the SDK's own default (600s) so wiring an explicit timeout can
# never SHORTEN a call that previously relied on the SDK default — a vLLM model
# under load can legitimately take minutes to first token.
_DEFAULT_TIMEOUT = 600


def is_rate_limited(err: str | None) -> bool:
    """True if an error string looks like a provider rate-limit / overload."""
    s = (err or "").lower()
    return any(marker in s for marker in _RATE_LIMIT_MARKERS)


def effort_timeout(model: str | None) -> int:
    """Wall-clock timeout (seconds) for one LLM call, scaled by model tier.

    Matches on a substring so full ids (``claude-opus-4-...``,
    ``anthropic/claude-sonnet-4``) resolve to the right tier.
    """
    m = (model or "").lower()
    for tier, seconds in _EFFORT_TIMEOUTS.items():
        if tier in m:
            return seconds
    return _DEFAULT_TIMEOUT


def backoff_stream(
    fn: Callable[[], T],
    *,
    backoff: tuple[int, ...] = INTERACTIVE_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
):
    """Generator variant of :func:`call_with_backoff` for SSE provider loops.

    Yields ``{"type": "activity", "content": ...}`` events during rate-limit
    waits — sliced to at most ``KEEPALIVE_SLICE_S`` apart so a live chat stream
    never goes silent long enough for an idle proxy to drop it. The FINAL yielded
    item is ``{"__result__": <fn() return value>}``; callers pull that out and
    forward every other event to the client:

        for ev in backoff_stream(lambda: client.create(...)):
            if "__result__" in ev:
                resp = ev["__result__"]
            else:
                yield ev

    Same retry policy as :func:`call_with_backoff`: only rate-limit errors
    retry; anything else (and schedule exhaustion) re-raises for the caller's
    existing ``except`` to surface as an error event.
    """
    attempt = 0
    while True:
        try:
            yield {"__result__": fn()}
            return
        except Exception as e:  # noqa: BLE001 — re-raised below if not retryable
            if not is_rate_limited(str(e)) or attempt >= len(backoff):
                raise
            wait = backoff[attempt]
            remaining = wait
            while remaining > 0:
                yield {
                    "type": "activity",
                    "content": (f"⏳ Rate-limited — waiting {remaining}s (retry {attempt + 1}/{len(backoff)})..."),
                }
                slice_s = min(KEEPALIVE_SLICE_S, remaining)
                sleep(slice_s)
                remaining -= slice_s
            attempt += 1


def call_with_backoff(
    fn: Callable[[], T],
    *,
    backoff: tuple[int, ...] = DEFAULT_BACKOFF,
    on_wait: Callable[[int, int, str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn`` and, on a rate-limit error, wait + retry with backoff.

    Non-rate-limit exceptions propagate immediately — a bad request or auth
    failure should not be retried five times. On exhausting the schedule the
    last rate-limit exception is re-raised so callers surface a real error.

    ``on_wait(attempt, wait_seconds, err)`` is called before each sleep (for
    progress reporting). ``sleep`` is injectable so tests don't actually wait.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — re-raised below if not retryable
            if not is_rate_limited(str(e)) or attempt >= len(backoff):
                raise
            wait = backoff[attempt]
            if on_wait is not None:
                on_wait(attempt + 1, wait, str(e))
            else:
                log.warning(
                    "LLM rate-limited (%s); backoff %ss (%d/%d)",
                    str(e)[:80],
                    wait,
                    attempt + 1,
                    len(backoff),
                )
            sleep(wait)
            attempt += 1
