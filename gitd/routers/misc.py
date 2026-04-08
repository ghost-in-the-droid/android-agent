"""Misc routes: health, logs, restart, index page."""

import logging
import os
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
def index():
    """Redirect root to API docs."""
    return RedirectResponse(url="/docs")


# ── Server log buffer ────────────────────────────────────────────────────────

_log_buffer: deque = deque(maxlen=500)
_log_seq: int = 0
_log_lock = threading.Lock()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def log_append(level: str, msg: str):
    """Append a log entry to the in-memory ring buffer."""
    global _log_seq
    msg = _ANSI_RE.sub("", msg).rstrip()
    if not msg:
        return
    with _log_lock:
        _log_seq += 1
        _log_buffer.append(
            {
                "seq": _log_seq,
                "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "level": level,
                "msg": msg,
            }
        )


class _BufferLogHandler(logging.Handler):
    """Captures Python log records into the ring buffer."""

    def emit(self, record):
        log_append(record.levelname, self.format(record))


def setup_log_capture():
    """Wire up log capture for uvicorn and app loggers. Call once at startup."""
    handler = _BufferLogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    # Capture uvicorn access + error logs
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.addHandler(handler)
    # Capture app-level logs
    app_logger = logging.getLogger("gitd")
    app_logger.addHandler(handler)
    # Also capture root logger prints that go through logging
    root = logging.getLogger()
    root.addHandler(handler)


@router.get("/api/logs", summary="Get Server Logs")
def api_logs(request: Request, since: int = 0, limit: int = 50):
    """Return buffered server logs. Accepts `from` or `since` as sequence cursor."""
    # `from` is a Python keyword — read it from query string manually
    seq_cursor = since
    if request and "from" in request.query_params:
        try:
            seq_cursor = int(request.query_params["from"])
        except (ValueError, TypeError):
            pass
    with _log_lock:
        lines = [e for e in _log_buffer if e["seq"] > seq_cursor][-limit:]
        seq = _log_seq
    return {"lines": lines, "seq": seq}


# ── Server restart ───────────────────────────────────────────────────────────


@router.post("/api/server/restart", summary="Restart Server Process")
def api_server_restart():
    """Restart the server process."""

    def _restart():
        time.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=_restart, daemon=True).start()
    return {"ok": True, "message": "Restarting..."}
