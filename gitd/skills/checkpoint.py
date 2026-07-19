"""Human-in-the-loop checkpoint step (feat/checkpoint-step).

A `checkpoint` recorded-step pauses a running skill at a gate a bot must not
clear on its own (captcha / SMS code / email code / login-2FA). The workflow
suspends, the run is marked ``awaiting_human`` and surfaced on the live stream,
and it resumes when **whichever fires first**:
  - a human posts to /api/skills/runs/{id}/resume  (always-available override), or
  - an auto-detect success condition (url_contains / screen_has) is met.
On ``timeout_s`` (default 600s; 0/None = wait indefinitely) it ends as
``timed_out`` — resumable/retryable, never a silent pass or fail.

The poll loop below is pure and dependency-injected (read_signal / check_success
/ set_state / notify / now / sleep) so it is unit-testable without a device or DB.
The engine wires the real callbacks in RecordedStepAction._run_checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_TIMEOUT_S = 600
VALID_REASONS = {"captcha", "sms", "email", "login", "generic"}


@dataclass
class CheckpointOutcome:
    resolved: bool                 # True → resume the workflow; False → stop it
    resolution: str                # 'human' | 'auto' | 'timed_out' | 'aborted'
    error: str | None = None
    data: dict = field(default_factory=dict)


def run_checkpoint(
    *,
    reason: str,
    prompt: str,
    success: dict | None,
    timeout_s: float | None,
    read_signal: Callable[[], str | None],
    check_success: Callable[[dict], bool],
    set_state: Callable[[str, dict | None], None],
    notify: Callable[[str, str], None],
    now: Callable[[], float],
    sleep: Callable[[float], None],
    poll: float = 2.0,
) -> CheckpointOutcome:
    """Block until the checkpoint is cleared, auto-detected, aborted, or times out.

    Each cycle checks (in order) the manual signal — the always-available human
    override — then the auto-detect condition, then the timeout; "first to fire
    wins" across cycles. ``timeout_s`` falsy (0/None) waits indefinitely.
    """
    reason = reason if reason in VALID_REASONS else "generic"
    entered = now()
    set_state("awaiting_human", {"reason": reason, "prompt": prompt, "success": success or {}, "timeout_s": timeout_s})
    notify(reason, prompt)

    while True:
        sig = read_signal()
        if sig == "abort":
            set_state("aborted", None)
            return CheckpointOutcome(False, "aborted", f"checkpoint aborted by human ({reason})")
        if sig == "resume":
            set_state("running", None)
            return CheckpointOutcome(True, "human", data={"checkpoint": reason})

        if success and check_success(success):
            set_state("running", None)
            return CheckpointOutcome(True, "auto", data={"checkpoint": reason})

        if timeout_s and (now() - entered) >= timeout_s:
            set_state("timed_out", None)
            return CheckpointOutcome(False, "timed_out", f"checkpoint timed_out after {timeout_s}s ({reason})")

        sleep(poll)


def screen_condition_met(device: Any, success: dict) -> bool:
    """Best-effort, cross-platform auto-detect for a checkpoint success condition.

    - ``screen_has``: substring present anywhere in the current UI tree.
    - ``url_contains``: substring in the current browser URL, falling back to the
      UI tree (the address bar text usually appears there on both platforms).
    """
    if not success:
        return False

    needle = success.get("screen_has")
    if needle:
        try:
            xml = device.dump_xml() or ""
            if needle.lower() in xml.lower():
                return True
        except Exception:
            pass

    url_sub = success.get("url_contains")
    if url_sub:
        try:
            from gitd.services.browser import get_current_url

            info = get_current_url(device.serial)
            url = info.get("url", "") if isinstance(info, dict) else ""
            if url and url_sub.lower() in url.lower():
                return True
        except Exception:
            pass
        try:
            xml = device.dump_xml() or ""
            if url_sub.lower() in xml.lower():
                return True
        except Exception:
            pass

    return False
