"""Control channel for v2 `checkpoint:` steps (human-in-the-loop gates).

The poll loop is the v1.5 engine's ``gitd.skills.checkpoint.run_checkpoint``
(ported verbatim from origin/main). It takes three side-effect callbacks, which
a channel object provides:

    read_signal() -> "resume" | "abort" | None   # human override, polled every cycle
    set_state(status, checkpoint | None)          # awaiting_human | running | aborted | timed_out
    notify(reason, prompt)                        # surface the gate to a human

Two channels:

* ``SkillRunChannel(run_id)``: the same callbacks as origin/main
  ``gitd/skills/base.py`` ``RecordedStepAction._run_checkpoint`` (``_set_state``
  / ``_read_signal`` / ``_notify``): ``SkillRun.status`` + ``checkpoint_json``,
  ``SkillRun.resume_signal`` written by ``POST /api/skills/runs/{run_id}/resume``
  (origin/main ``gitd/routers/skills.py`` ``api_skill_run_resume``). Those
  columns arrive with v1.5 C1 (origin/main ``gitd/models/skill_compat.py``);
  until then DB access fails softly (logged, read_signal returns None), exactly
  like main's closures.
* ``LocalChannel``: in-process ``resume()`` / ``abort()`` (thread-safe), for
  embedding, tests and CLI runs without a SkillRun row.

Selection (``channel_for``): an explicit ``ctx.extras["_checkpoint_channel"]``
wins, else ``SkillRunChannel`` when the run has ``ctx.extras["_run_id"]`` (set by
``run_action(run_id=...)``), else ``None`` (no human channel; the step then
gates on its success validator only, or is skipped like main when it has none).
"""
from __future__ import annotations

import json
import logging
import sys
import threading

log = logging.getLogger("skills.engine.hitl")

CHANNEL_KEY = "_checkpoint_channel"
RUN_ID_KEY = "_run_id"
RECORD_KEY = "_checkpoints"          # ctx.extras list of {reason, prompt, resolution, ...}


class SkillRunChannel:
    """Shared-DB channel, shaped 1:1 like origin/main's RecordedStepAction._run_checkpoint closures."""

    def __init__(self, run_id: int):
        self.run_id = run_id

    def set_state(self, status: str, checkpoint: dict | None) -> None:
        try:
            from gitd.models.base import SessionLocal
            from gitd.models.skill_compat import SkillRun

            db = SessionLocal()
            try:
                row = db.get(SkillRun, self.run_id)
                if row:
                    row.status = status
                    if checkpoint is not None:
                        row.checkpoint_json = json.dumps(checkpoint)
                    if status in ("awaiting_human", "running"):
                        row.resume_signal = None  # clear stale/consumed signal
                    db.commit()
            finally:
                db.close()
        except Exception:
            log.exception("[checkpoint] set_state failed")

    def read_signal(self) -> str | None:
        try:
            from gitd.models.base import SessionLocal
            from gitd.models.skill_compat import SkillRun

            db = SessionLocal()
            try:
                row = db.get(SkillRun, self.run_id)
                return row.resume_signal if row else None
            finally:
                db.close()
        except Exception:
            log.exception("[checkpoint] read_signal failed")
            return None

    def read_answer(self):
        from .ask import NO_ANSWER
        signal = self.read_signal()
        if signal and signal.startswith("answer:"):
            return json.loads(signal[7:])
        return NO_ANSWER

    def notify(self, reason: str, prompt: str) -> None:
        line = f"[checkpoint] AWAITING HUMAN: {reason}: {prompt or '(no prompt)'} (run {self.run_id})"
        log.warning(line)
        print(line, flush=True)  # surfaces in the run's captured output / live log


class LocalChannel:
    """In-process channel: thread-safe resume/abort; states and notices recorded for inspection."""

    def __init__(self, *, echo: bool = True):
        self._signal: str | None = None
        self._lock = threading.Lock()
        self.states: list[tuple[str, dict | None]] = []
        self.notices: list[tuple[str, str]] = []
        self.echo = echo

    def answer(self, value) -> None:
        with self._lock:
            self._answer = value

    def read_answer(self):
        from .ask import NO_ANSWER
        with self._lock:
            value = getattr(self, '_answer', NO_ANSWER)
            self._answer = NO_ANSWER
            return value

    def resume(self) -> None:
        with self._lock:
            self._signal = "resume"

    def abort(self) -> None:
        with self._lock:
            self._signal = "abort"

    def read_signal(self) -> str | None:
        with self._lock:
            sig, self._signal = self._signal, None
            return sig

    def set_state(self, status: str, checkpoint: dict | None) -> None:
        self.states.append((status, checkpoint))

    def notify(self, reason: str, prompt: str) -> None:
        self.notices.append((reason, prompt))
        log.warning("[checkpoint] AWAITING HUMAN: %s: %s", reason, prompt)
        if self.echo:
            print(f"[checkpoint] AWAITING HUMAN: {reason}: {prompt or '(no prompt)'}", file=sys.stderr, flush=True)


def channel_for(ctx):
    """The run's human channel, or None when nothing can deliver a resume/abort."""
    ch = ctx.extras.get(CHANNEL_KEY)
    if ch is not None:
        return ch
    run_id = ctx.extras.get(RUN_ID_KEY)
    if run_id is not None:
        ch = ctx.extras[CHANNEL_KEY] = SkillRunChannel(run_id)
        return ch
    return None
