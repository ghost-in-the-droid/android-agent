"""Tests for local tracing — observability storage layer + /api/traces endpoints.

Run:
    .venv/bin/pytest tests/test_traces.py -v

These tests run against a throwaway SQLite file (redirected via DB_PATH in
tests/conftest.py, verified by the _verify_db_isolated guard) — NOT the real
data/gitd.db. Each test truncates the trace tables via the ``fresh_db`` fixture
for a clean slate. They cover:

- The observability helpers (`trace_chat_turn`, `record_generation`, …) write
  the right rows with the right values.
- Token/cost accumulation across multiple `record_generation` calls in one trace.
- Status transitions (success / error).
- The router endpoints (list, stats, detail, delete) return the expected shape
  and respect filters.
- Edge cases: empty queries, missing trace, FK-free conversation_id.
"""

from __future__ import annotations

import os
import time
from typing import Iterator

import pytest


@pytest.fixture
def fresh_db() -> Iterator[None]:
    """Truncate the trace tables before (and after) each test for a clean slate.

    Safe because tests/conftest.py has redirected DB_PATH to a throwaway file
    before gitd was imported, so these deletes hit the temp test DB, never the
    real data/gitd.db.
    """
    from gitd.models.base import engine
    from gitd.models import Base
    from gitd.models.trace import Trace, TraceSpan
    Base.metadata.create_all(engine)  # idempotent, ensures tables exist
    from gitd.models.base import SessionLocal
    db = SessionLocal()
    try:
        db.query(TraceSpan).delete()
        db.query(Trace).delete()
        db.commit()
    finally:
        db.close()
    yield
    # Post-test cleanup so subsequent runs / unrelated tests don't see our rows
    db = SessionLocal()
    try:
        db.query(TraceSpan).delete()
        db.query(Trace).delete()
        db.commit()
    finally:
        db.close()


# ── Storage layer ────────────────────────────────────────────────────────────

def test_basic_trace_roundtrip(fresh_db):
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace, TraceSpan
    from gitd.services.observability import (
        trace_chat_turn, record_generation, record_tool_result, set_trace_output,
    )

    with trace_chat_turn(session_id="conv-1", user_message="hi",
                         provider="claude-code", model="sonnet",
                         device="dev1", source="mac") as t:
        s = t.span(name="tool:web_search", input={"args": {"q": "x"}})
        record_tool_result(s, "ok")
        record_generation(t, model="sonnet", prompt="p", output="r",
                          input_tokens=100, output_tokens=20, cost_usd=0.001)
        set_trace_output(t, "final reply")

    db = SessionLocal()
    try:
        traces = db.query(Trace).all()
        assert len(traces) == 1
        tr = traces[0]
        assert tr.provider == "claude-code"
        assert tr.model == "sonnet"
        assert tr.source == "mac"
        assert tr.status == "success"
        assert tr.user_input == "hi"
        assert tr.final_output == "final reply"
        assert tr.input_tokens == 100
        assert tr.output_tokens == 20
        assert tr.cost_usd == pytest.approx(0.001)
        assert tr.duration_ms >= 0

        spans = db.query(TraceSpan).filter_by(trace_id=tr.id).all()
        kinds = sorted([s.kind for s in spans])
        assert kinds == ["generation", "tool"]
        tool = next(s for s in spans if s.kind == "tool")
        assert tool.name == "tool:web_search"
        assert tool.level == "DEFAULT"
    finally:
        db.close()


def test_token_accumulation_across_generations(fresh_db):
    """on-device gemma calls record_generation per turn — totals should sum."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace
    from gitd.services.observability import trace_chat_turn, record_generation

    with trace_chat_turn(session_id="c", user_message="hi", provider="on-device",
                         model="g4-e4b", device="d", source="android") as t:
        record_generation(t, model="g4-e4b", prompt="p1", output="r1",
                          input_tokens=50, output_tokens=10, cost_usd=0.0)
        record_generation(t, model="g4-e4b", prompt="p2", output="r2",
                          input_tokens=70, output_tokens=15, cost_usd=0.0)
        record_generation(t, model="g4-e4b", prompt="p3", output="r3",
                          input_tokens=80, output_tokens=5, cost_usd=0.0)

    db = SessionLocal()
    try:
        tr = db.query(Trace).first()
        assert tr.input_tokens == 200
        assert tr.output_tokens == 30
    finally:
        db.close()


def test_error_status_on_exception(fresh_db):
    """If the wrapped block raises, trace.status should flip to 'error'."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace
    from gitd.services.observability import trace_chat_turn

    with pytest.raises(RuntimeError, match="boom"):
        with trace_chat_turn(session_id="c", user_message="hi", provider="x",
                             model="m", device="d", source="mac"):
            raise RuntimeError("boom")

    db = SessionLocal()
    try:
        tr = db.query(Trace).first()
        assert tr.status == "error"
        assert "boom" in tr.error_text
    finally:
        db.close()


def test_tool_error_marks_span_error(fresh_db):
    from gitd.models.base import SessionLocal
    from gitd.models.trace import TraceSpan
    from gitd.services.observability import (
        trace_chat_turn, record_tool_result,
    )

    with trace_chat_turn(session_id="c", user_message="x", provider="x",
                         model="m", device="d", source="mac") as t:
        s_ok = t.span(name="tool:a", input={})
        record_tool_result(s_ok, "fine")
        s_err = t.span(name="tool:b", input={})
        record_tool_result(s_err, "boom", error=True)

    db = SessionLocal()
    try:
        spans = {s.name: s for s in db.query(TraceSpan).all()}
        assert spans["tool:a"].level == "DEFAULT"
        assert spans["tool:b"].level == "ERROR"
    finally:
        db.close()


def test_orphan_conversation_id_does_not_break(fresh_db):
    """conversation_id is a soft reference, not a FK — non-existent IDs are fine."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace
    from gitd.services.observability import trace_chat_turn

    with trace_chat_turn(session_id="never-existed", user_message="hi",
                         provider="x", model="m", device="d", source="mac"):
        pass

    db = SessionLocal()
    try:
        assert db.query(Trace).count() == 1
    finally:
        db.close()


def test_truncation_keeps_rows_bounded(fresh_db):
    """Huge tool inputs/outputs shouldn't blow the row size."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import TraceSpan
    from gitd.services.observability import (
        trace_chat_turn, record_tool_result,
    )

    huge = "X" * 50_000
    with trace_chat_turn(session_id="c", user_message="x", provider="x",
                         model="m", device="d", source="mac") as t:
        s = t.span(name="tool:big", input={"giant": huge})
        record_tool_result(s, huge)

    db = SessionLocal()
    try:
        sp = db.query(TraceSpan).filter_by(name="tool:big").first()
        # Truncated to ~4000 chars + ellipsis marker
        assert len(sp.input_json) < 5000
        assert len(sp.output_json) < 5000
        assert "[truncated]" in sp.input_json
    finally:
        db.close()


# ── API endpoints ────────────────────────────────────────────────────────────

@pytest.fixture
def client(fresh_db):
    """FastAPI TestClient against the gitd app."""
    from fastapi.testclient import TestClient
    from gitd.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


def _seed(provider="claude-code", source="mac", status_set="success"):
    """Helper — create one full trace in the DB and return its id."""
    from gitd.services.observability import (
        trace_chat_turn, record_tool_result, record_generation, set_trace_output,
    )
    if status_set == "error":
        try:
            with trace_chat_turn(session_id="c", user_message="bad",
                                 provider=provider, model="m1",
                                 device="d", source=source) as t:
                s = t.span(name="tool:thing", input={})
                record_tool_result(s, "err", error=True)
                raise RuntimeError("simulated")
        except RuntimeError:
            pass
        # Find the most recent and return its id
        from gitd.models.base import SessionLocal
        from gitd.models.trace import Trace
        db = SessionLocal()
        try:
            return db.query(Trace).order_by(Trace.started_at.desc()).first().id
        finally:
            db.close()

    with trace_chat_turn(session_id="c", user_message="hi",
                         provider=provider, model="m1",
                         device="d", source=source) as t:
        s = t.span(name="tool:thing", input={"x": 1})
        record_tool_result(s, "ok")
        record_generation(t, model="m1", prompt="p", output="r",
                          input_tokens=5, output_tokens=3, cost_usd=0.001)
        set_trace_output(t, "out")
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace
    db = SessionLocal()
    try:
        return db.query(Trace).order_by(Trace.started_at.desc()).first().id
    finally:
        db.close()


def test_list_endpoint_returns_paginated(client):
    for _ in range(3):
        _seed()
    r = client.get("/api/traces?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["data"]) == 2
    assert all("provider" in t for t in body["data"])


def test_list_endpoint_filters_by_provider(client):
    _seed(provider="claude-code", source="mac")
    _seed(provider="on-device", source="android")
    _seed(provider="ollama", source="mac")

    r = client.get("/api/traces?provider=on-device")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["data"][0]["provider"] == "on-device"


def test_list_endpoint_filters_by_status_error(client):
    _seed(status_set="success")
    _seed(status_set="error")
    r = client.get("/api/traces?status=error")
    body = r.json()
    assert body["total"] == 1
    assert body["data"][0]["status"] == "error"


def test_stats_endpoint(client):
    _seed(provider="claude-code")
    _seed(provider="claude-code")
    _seed(provider="on-device", status_set="error")

    r = client.get("/api/traces/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["errors"] == 1
    assert body["success_rate"] == pytest.approx(2 / 3, rel=1e-3)
    providers = {p["provider"]: p["count"] for p in body["by_provider"]}
    assert providers["claude-code"] == 2
    assert providers["on-device"] == 1


def test_detail_endpoint_includes_spans(client):
    tid = _seed()
    r = client.get(f"/api/traces/{tid}")
    assert r.status_code == 200
    body = r.json()
    assert body["trace"]["id"] == tid
    assert body["trace"]["final_output"] == "out"
    kinds = sorted(s["kind"] for s in body["spans"])
    assert kinds == ["generation", "tool"]
    tool = next(s for s in body["spans"] if s["kind"] == "tool")
    assert tool["input"] == {"args": None} or "x" in (tool["input"] or {})


def test_detail_endpoint_404_on_unknown(client):
    r = client.get("/api/traces/does-not-exist")
    assert r.status_code == 404


def test_delete_single_trace(client):
    tid = _seed()
    r = client.delete(f"/api/traces/{tid}")
    assert r.status_code == 200
    assert r.json()["deleted"] == tid
    r2 = client.get(f"/api/traces/{tid}")
    assert r2.status_code == 404


def test_clear_all_traces(client):
    for _ in range(3):
        _seed()
    r = client.delete("/api/traces")
    assert r.status_code == 200
    body = r.json()
    assert body["deleted_traces"] == 3
    list_r = client.get("/api/traces")
    assert list_r.json()["total"] == 0
