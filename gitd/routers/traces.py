"""Local trace inspector API.

Powers the in-app Traces tab. Read-only endpoints over the `traces` and
`trace_spans` tables that the observability layer writes to.

Endpoint surface kept small and JSON-shaped for the Android adapter:
    GET  /api/traces                        list (filterable, paginated)
    GET  /api/traces/stats                  aggregate counters for the header bar
    GET  /api/traces/{trace_id}             full detail with all spans
    DELETE /api/traces                      truncate (debug — clears all)
    DELETE /api/traces/{trace_id}           single trace
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, func

router = APIRouter(prefix="/api/traces", tags=["traces"])


def _row_to_summary(t) -> dict:
    """Serialize one trace row → list-view summary (small payload)."""
    return {
        "id": t.id,
        "conversation_id": t.conversation_id or "",
        "provider": t.provider or "",
        "model": t.model or "",
        "device": t.device or "",
        "source": t.source or "",
        "status": t.status or "",
        "user_input": t.user_input or "",
        "final_output_preview": (t.final_output or "")[:200],
        "input_tokens": t.input_tokens or 0,
        "output_tokens": t.output_tokens or 0,
        "cost_usd": float(t.cost_usd or 0),
        "duration_ms": t.duration_ms or 0,
        "started_at": t.started_at,
        "ended_at": t.ended_at or "",
        "error_text": t.error_text or "",
    }


def _span_to_dict(s) -> dict:
    return {
        "id": s.id,
        "kind": s.kind,
        "name": s.name,
        "level": s.level or "DEFAULT",
        "input": _safe_json_load(s.input_json),
        "output": _safe_json_load(s.output_json),
        "started_at": s.started_at,
        "ended_at": s.ended_at or "",
        "duration_ms": s.duration_ms or 0,
    }


def _safe_json_load(s: Optional[str]):
    if not s:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s  # raw string fallback for truncated/garbled values


@router.get("", summary="List Traces")
def list_traces(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    provider: Optional[str] = Query(None, description="Filter by provider (claude-code, on-device, ollama, anthropic)"),
    source: Optional[str] = Query(None, description="Filter by source (mac, android)"),
    status: Optional[str] = Query(None, description="Filter by status (success, error, running, stopped)"),
    conversation_id: Optional[str] = Query(None, description="Filter to one conversation"),
):
    """Newest-first list. Each row carries enough for the list-view card."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace

    db = SessionLocal()
    try:
        q = db.query(Trace).order_by(desc(Trace.started_at))
        if provider:
            q = q.filter(Trace.provider == provider)
        if source:
            q = q.filter(Trace.source == source)
        if status:
            q = q.filter(Trace.status == status)
        if conversation_id:
            q = q.filter(Trace.conversation_id == conversation_id)

        total = q.count()
        rows = q.limit(limit).offset(offset).all()
        return {"total": total, "limit": limit, "offset": offset, "data": [_row_to_summary(r) for r in rows]}
    finally:
        db.close()


@router.get("/stats", summary="Trace Stats")
def trace_stats(
    since_hours: int = Query(24, ge=1, le=24 * 30),
):
    """Aggregate counters for the Traces tab header bar."""
    from datetime import datetime, timedelta, timezone

    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    db = SessionLocal()
    try:
        base_q = db.query(Trace).filter(Trace.started_at >= cutoff)
        total = base_q.count()
        errors = base_q.filter(Trace.status == "error").count()
        avg_duration = (
            db.query(func.avg(Trace.duration_ms)).filter(Trace.started_at >= cutoff, Trace.status == "success").scalar()
            or 0
        )
        total_cost = db.query(func.sum(Trace.cost_usd)).filter(Trace.started_at >= cutoff).scalar() or 0.0
        total_in = db.query(func.sum(Trace.input_tokens)).filter(Trace.started_at >= cutoff).scalar() or 0
        total_out = db.query(func.sum(Trace.output_tokens)).filter(Trace.started_at >= cutoff).scalar() or 0
        # Per-provider breakdown
        per_provider = base_q.with_entities(Trace.provider, func.count(Trace.id)).group_by(Trace.provider).all()
        return {
            "since_hours": since_hours,
            "total": total,
            "errors": errors,
            "success_rate": round((total - errors) / total, 3) if total else 1.0,
            "avg_duration_ms": int(avg_duration),
            "total_cost_usd": round(float(total_cost), 4),
            "total_input_tokens": int(total_in),
            "total_output_tokens": int(total_out),
            "by_provider": [{"provider": p or "?", "count": int(c)} for p, c in per_provider],
        }
    finally:
        db.close()


@router.get("/{trace_id}", summary="Get Trace With Spans")
def get_trace(trace_id: str):
    """Full detail view: trace metadata + ordered span timeline."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace, TraceSpan

    db = SessionLocal()
    try:
        t = db.get(Trace, trace_id)
        if not t:
            raise HTTPException(status_code=404, detail="trace not found")
        spans = db.query(TraceSpan).filter_by(trace_id=trace_id).order_by(TraceSpan.started_at, TraceSpan.id).all()
        return {
            "trace": {
                **_row_to_summary(t),
                "final_output": t.final_output or "",
            },
            "spans": [_span_to_dict(s) for s in spans],
        }
    finally:
        db.close()


@router.delete("/{trace_id}", summary="Delete Trace")
def delete_trace(trace_id: str):
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace

    db = SessionLocal()
    try:
        t = db.get(Trace, trace_id)
        if not t:
            raise HTTPException(status_code=404, detail="trace not found")
        db.delete(t)  # ON DELETE CASCADE cleans up spans
        db.commit()
        return {"ok": True, "deleted": trace_id}
    finally:
        db.close()


@router.delete("", summary="Clear All Traces (Debug)")
def clear_all_traces():
    """Wipe everything — useful when iterating on observability code."""
    from gitd.models.base import SessionLocal
    from gitd.models.trace import Trace, TraceSpan

    db = SessionLocal()
    try:
        n_spans = db.query(TraceSpan).delete()
        n_traces = db.query(Trace).delete()
        db.commit()
        return {"ok": True, "deleted_traces": n_traces, "deleted_spans": n_spans}
    finally:
        db.close()
