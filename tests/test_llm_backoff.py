"""Tests for the rate-limit backoff + effort-timeout helpers."""

import pytest

from gitd.services.llm_backoff import (
    backoff_stream,
    call_with_backoff,
    effort_timeout,
    is_rate_limited,
)


@pytest.mark.parametrize(
    "err",
    [
        "Error code: 429 Too Many Requests",
        "overloaded_error: the model is overloaded",
        "rate limit exceeded",
        "RATE_LIMIT",
        "usage limit reached",
        "529 server overloaded",
        "quota exceeded for this org",
    ],
)
def test_is_rate_limited_true(err):
    assert is_rate_limited(err)


@pytest.mark.parametrize(
    "err",
    ["", None, "400 bad request", "invalid api key", "connection reset", "not found"],
)
def test_is_rate_limited_false(err):
    assert not is_rate_limited(err)


def test_effort_timeout_scales_by_tier():
    assert effort_timeout("claude-opus-4-8") == 420
    assert effort_timeout("anthropic/claude-sonnet-4") == 300
    assert effort_timeout("claude-haiku-4-5") == 240


def test_effort_timeout_default_never_shortens_below_sdk_default():
    # Regression guard (neutral-review PR #37 FIX-2): unknown models — vLLM,
    # gemma, on-device, future ids — previously relied on the SDK's own 600s
    # default. The fallback MUST be >= 600 so wiring an explicit timeout can
    # never SHORTEN a call that used to work (a vLLM model can exceed 180s to
    # first token under load).
    assert effort_timeout("unsloth/gemma-4-E4B-it") >= 600
    assert effort_timeout("gemma-4-e2b-q4km-gguf") >= 600
    assert effort_timeout("") >= 600
    assert effort_timeout(None) >= 600


def test_call_with_backoff_passthrough_on_success():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    slept = []
    assert call_with_backoff(fn, sleep=slept.append) == "ok"
    assert calls == [1]  # called exactly once, no retries
    assert slept == []  # never slept


def test_call_with_backoff_retries_then_succeeds():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("429 Too Many Requests")
        return "recovered"

    slept = []
    result = call_with_backoff(fn, backoff=(1, 2, 3), sleep=slept.append)
    assert result == "recovered"
    assert attempts["n"] == 3
    assert slept == [1, 2]  # two backoff waits before the third attempt succeeded


def test_call_with_backoff_non_rate_limit_raises_immediately():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        raise ValueError("400 invalid request")

    slept = []
    with pytest.raises(ValueError, match="400 invalid request"):
        call_with_backoff(fn, sleep=slept.append)
    assert attempts["n"] == 1  # not retried
    assert slept == []


def test_call_with_backoff_exhausts_and_reraises():
    def fn():
        raise RuntimeError("overloaded")

    slept = []
    with pytest.raises(RuntimeError, match="overloaded"):
        call_with_backoff(fn, backoff=(1, 2), sleep=slept.append)
    assert slept == [1, 2]  # exhausted the whole schedule


def test_call_with_backoff_on_wait_callback():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("rate limit")
        return "ok"

    waits = []
    call_with_backoff(
        fn,
        backoff=(5, 10),
        on_wait=lambda attempt, wait, err: waits.append((attempt, wait)),
        sleep=lambda _: None,
    )
    assert waits == [(1, 5)]


# ── backoff_stream (SSE keepalive variant, PR #37 FIX-1) ──────────────────────


def test_backoff_stream_success_yields_only_result():
    events = list(backoff_stream(lambda: "ok", sleep=lambda _: None))
    assert events == [{"__result__": "ok"}]  # no activity events on a clean call


def test_backoff_stream_emits_keepalive_activity_during_wait():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("429 overloaded")
        return "recovered"

    slept = []
    events = list(backoff_stream(fn, backoff=(25,), sleep=slept.append))

    activity = [e for e in events if e.get("type") == "activity"]
    results = [e for e in events if "__result__" in e]
    # 25s wait sliced into <=10s keepalives → 3 activity pings (25,15,5 remaining)
    assert len(activity) == 3
    assert all("Rate-limited" in e["content"] for e in activity)
    # sleeps sum to the full wait and none exceed the keepalive slice
    assert sum(slept) == 25
    assert max(slept) <= 10
    assert results == [{"__result__": "recovered"}]


def test_backoff_stream_non_rate_limit_raises():
    def fn():
        raise ValueError("400 bad request")

    with pytest.raises(ValueError, match="400 bad request"):
        list(backoff_stream(fn, sleep=lambda _: None))


def test_backoff_stream_exhausts_and_reraises():
    def fn():
        raise RuntimeError("overloaded")

    with pytest.raises(RuntimeError, match="overloaded"):
        list(backoff_stream(fn, backoff=(5, 10), sleep=lambda _: None))
