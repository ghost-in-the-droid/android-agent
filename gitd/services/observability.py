"""Observability — local SQLite tracing (always on) + optional Langfuse forward.

Two storage backends, fronted by the same helpers so the chat providers don't
care which is wired:

- **Local** (`gitd.db` `traces` + `trace_spans`) — always on. Powers the in-app
  Traces tab. Survives Mac reboots, works offline, no external deps.
- **Langfuse** — opt-in, activated when `LANGFUSE_PUBLIC_KEY` is set. Useful for
  centralized cross-device aggregation, leaderboards, eval scoring.

Both write the same trace shape, so flipping between them is just a config
change. Tracing every chat turn means every helper here gets called dozens
of times per session — they MUST be cheap and exception-safe.

Public surface (unchanged from prior version, so wiring in chat providers
doesn't move):
    trace_chat_turn(...)        contextmanager — opens trace handle
    span_tool_call(...)         contextmanager — opens span handle (rarely used; helpers below cover the common case)
    record_generation(...)      records llm-call generation under a trace
    record_tool_result(...)     ends a tool span with output (success or error)
    set_trace_output(...)       sets the trace's final assistant reply
"""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _truncate(s: Any, limit: int = 4000) -> str:
    """JSON-stringify and truncate. Keeps the DB rows bounded."""
    try:
        text = s if isinstance(s, str) else json.dumps(s, default=str)
    except Exception:
        text = str(s)
    return text if len(text) <= limit else text[:limit] + "…[truncated]"


# ── Trace handle — what the providers see ─────────────────────────────────────

class _TraceHandle:
    """Lightweight wrapper passed to `with` blocks. Holds local trace_id and
    optional Langfuse handle. Methods called by the chat providers fan out to
    both storages; failures in either are swallowed so observability can never
    crash a chat turn.
    """

    __slots__ = ("local_id", "lf_handle", "_open_spans", "_started")

    def __init__(self, local_id: str, lf_handle: Optional[Any]):
        self.local_id = local_id
        self.lf_handle = lf_handle
        self._open_spans: dict[str, dict] = {}  # span_key → state
        self._started = time.time()

    # -- spans --
    def span(self, *, name: str, input: Any = None, kind: str = "tool") -> "_SpanHandle":
        """Open a span. Returned handle is what's passed to record_tool_result.

        Caller controls the shape of `input` — pass it through to Langfuse
        verbatim; existing callers already wrap as {"args": tool_args}."""
        local_span = _local_span_open(self.local_id, kind=kind, name=name, input_obj=input)
        lf_span = None
        if self.lf_handle is not None:
            try:
                lf_span = self.lf_handle.span(name=name, input=input)
            except Exception:
                pass
        return _SpanHandle(local_id=local_span, lf_handle=lf_span)

    # -- generations (single-shot, no open/close pair) --
    def record_generation(self, *, model: str, prompt: str, output: str,
                          input_tokens: int = 0, output_tokens: int = 0,
                          cost_usd: float = 0.0) -> None:
        _local_generation(
            self.local_id, model=model, prompt=prompt, output=output,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        )
        if self.lf_handle is not None:
            try:
                self.lf_handle.generation(
                    name="llm-call", model=model, input=prompt, output=output,
                    usage={
                        "input": input_tokens, "output": output_tokens,
                        "total": input_tokens + output_tokens, "unit": "TOKENS",
                    },
                    metadata={"cost_usd": cost_usd} if cost_usd else None,
                )
            except Exception:
                pass

    # -- final output --
    def set_output(self, output: str) -> None:
        _local_trace_set_output(self.local_id, output)
        if self.lf_handle is not None:
            try:
                self.lf_handle.update(output=output)
            except Exception:
                pass


class _SpanHandle:
    __slots__ = ("local_id", "lf_handle", "_started")

    def __init__(self, local_id: int, lf_handle: Optional[Any]):
        self.local_id = local_id
        self.lf_handle = lf_handle
        self._started = time.time()


# ── Local SQLite writers ──────────────────────────────────────────────────────

def _local_trace_open(*, conversation_id: str, provider: str, model: str,
                      device: str, source: str, user_input: str) -> str:
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace
    trace_id = uuid.uuid4().hex
    db = SessionLocal()
    try:
        db.add(Trace(
            id=trace_id,
            conversation_id=conversation_id or None,
            provider=provider, model=model, device=device, source=source,
            user_input=_truncate(user_input, 8000),
            status="running",
            started_at=_now_iso(),
        ))
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        db.close()
    return trace_id


def _local_trace_close(trace_id: str, *, status: str, duration_ms: int,
                       error_text: str = "") -> None:
    """Close a trace — only touches lifecycle fields. Token/cost totals are
    accumulated by `_local_trace_accumulate_tokens` during the run, so we
    must not overwrite them here."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace
    db = SessionLocal()
    try:
        t = db.get(Trace, trace_id)
        if t:
            t.status = status
            t.duration_ms = duration_ms
            t.error_text = _truncate(error_text, 2000) if error_text else ""
            t.ended_at = _now_iso()
            db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        db.close()


def _local_trace_set_output(trace_id: str, output: str) -> None:
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace
    db = SessionLocal()
    try:
        t = db.get(Trace, trace_id)
        if t:
            t.final_output = _truncate(output, 16000)
            db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        db.close()


def _local_span_open(trace_id: str, *, kind: str, name: str, input_obj: Any) -> int:
    from gitd.models.base import SessionLocal
    from gitd.models.trace import TraceSpan
    db = SessionLocal()
    span_id = 0
    try:
        span = TraceSpan(
            trace_id=trace_id, kind=kind, name=name,
            input_json=_truncate(input_obj) if input_obj is not None else "",
            started_at=_now_iso(),
        )
        db.add(span)
        db.commit()
        span_id = span.id
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        db.close()
    return span_id


def _local_span_close(span_id: int, *, output_obj: Any, error: bool, duration_ms: int) -> None:
    from gitd.models.base import SessionLocal
    from gitd.models.trace import TraceSpan
    if not span_id:
        return
    db = SessionLocal()
    try:
        s = db.get(TraceSpan, span_id)
        if s:
            s.output_json = _truncate(output_obj) if output_obj is not None else ""
            s.level = "ERROR" if error else "DEFAULT"
            s.ended_at = _now_iso()
            s.duration_ms = duration_ms
            db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        db.close()


def _local_generation(trace_id: str, *, model: str, prompt: str, output: str,
                      input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    """LLM generations are stored as spans with kind='generation'. Single-shot
    write — no open/close needed since we already have all the data."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import TraceSpan
    db = SessionLocal()
    try:
        now = _now_iso()
        db.add(TraceSpan(
            trace_id=trace_id, kind="generation", name="llm-call",
            input_json=_truncate({"prompt": prompt, "model": model}, 16000),
            output_json=_truncate({
                "output": output,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cost_usd": cost_usd,
            }, 16000),
            started_at=now, ended_at=now,
        ))
        db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        db.close()


# ── Optional Langfuse client ──────────────────────────────────────────────────

_lf_client = None
_lf_init_done = False


def _lf_get_client():
    """Lazily build a Langfuse client. If LANGFUSE_PUBLIC_KEY isn't set, returns
    None forever and we skip the remote path entirely."""
    global _lf_client, _lf_init_done
    if _lf_init_done:
        return _lf_client
    _lf_init_done = True
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not pk or not sk:
        return None
    try:
        from langfuse import Langfuse
        _lf_client = Langfuse(
            public_key=pk, secret_key=sk,
            host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
        )
    except Exception:
        _lf_client = None
    return _lf_client


def is_langfuse_enabled() -> bool:
    return _lf_get_client() is not None


# ── Public API — what the chat providers call ─────────────────────────────────

@contextmanager
def trace_chat_turn(*, session_id: str, user_message: str, provider: str,
                    model: str, device: str, source: str = "mac") -> Iterator[Optional[_TraceHandle]]:
    """Open a trace for a full chat turn. Always returns a handle (never None
    now that local tracing is always on). The handle's methods fan out to both
    backends; the caller doesn't need to know which is enabled."""
    local_id = _local_trace_open(
        conversation_id=session_id, provider=provider, model=model,
        device=device, source=source, user_input=user_message,
    )

    lf_handle = None
    lf = _lf_get_client()
    if lf is not None:
        try:
            lf_handle = lf.trace(
                name=f"chat:{provider}",
                session_id=session_id,
                input={"message": user_message},
                metadata={"provider": provider, "model": model, "device": device, "source": source},
                tags=[provider, source],
            )
        except Exception:
            pass

    handle = _TraceHandle(local_id=local_id, lf_handle=lf_handle)
    started = time.time()
    error_text = ""
    status = "success"
    try:
        yield handle
    except Exception as e:
        status = "error"
        error_text = str(e)
        raise
    finally:
        duration_ms = int((time.time() - started) * 1000)
        _local_trace_close(
            local_id, status=status, duration_ms=duration_ms,
            error_text=error_text,
        )
        if lf is not None:
            try:
                if lf_handle is not None:
                    lf_handle.update(metadata={"duration_s": round(duration_ms / 1000, 2)})
                lf.flush()
            except Exception:
                pass


@contextmanager
def span_tool_call(trace: Optional[_TraceHandle], tool_name: str,
                   tool_args: Any) -> Iterator[Optional[_SpanHandle]]:
    """Less-used helper — most providers manage span lifecycle inline so they
    can attach the result to the right span by tool_use_id. Kept for symmetry."""
    if trace is None:
        yield None
        return
    span = trace.span(name=f"tool:{tool_name}", input=tool_args)
    started = time.time()
    try:
        yield span
    finally:
        _local_span_close(
            span.local_id, output_obj=None, error=False,
            duration_ms=int((time.time() - started) * 1000),
        )


def record_generation(trace: Optional[_TraceHandle], *, model: str, prompt: str,
                      output: str, input_tokens: int = 0, output_tokens: int = 0,
                      cost_usd: float = 0.0) -> None:
    if trace is None:
        return
    trace.record_generation(
        model=model, prompt=prompt, output=output,
        input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
    )
    # Also update the trace-level token + cost totals so the list view shows them.
    _local_trace_accumulate_tokens(trace.local_id, input_tokens, output_tokens, cost_usd)


def _local_trace_accumulate_tokens(trace_id: str, input_tokens: int,
                                   output_tokens: int, cost_usd: float) -> None:
    """For multi-turn LLM models that emit several `record_generation` calls
    per trace (e.g. on-device Gemma's tool loop), accumulate totals."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace
    if not (input_tokens or output_tokens or cost_usd):
        return
    db = SessionLocal()
    try:
        t = db.get(Trace, trace_id)
        if t:
            t.input_tokens = (t.input_tokens or 0) + int(input_tokens)
            t.output_tokens = (t.output_tokens or 0) + int(output_tokens)
            t.cost_usd = (t.cost_usd or 0.0) + float(cost_usd)
            db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    finally:
        db.close()


def record_tool_result(span: Optional[_SpanHandle], result: str,
                       error: bool = False) -> None:
    if span is None:
        return
    duration_ms = int((time.time() - span._started) * 1000)
    _local_span_close(span.local_id, output_obj={"result": result[:4000]},
                      error=error, duration_ms=duration_ms)
    if span.lf_handle is not None:
        try:
            span.lf_handle.update(
                output={"result": result[:2000]},
                level="ERROR" if error else "DEFAULT",
            )
            span.lf_handle.end()
        except Exception:
            pass


def set_trace_output(trace: Optional[_TraceHandle], output: str) -> None:
    if trace is None or not output:
        return
    trace.set_output(output)


# Back-compat alias for old code paths.
def is_enabled() -> bool:
    """Local tracing is always enabled. Kept for callers that gate logic on this."""
    return True
