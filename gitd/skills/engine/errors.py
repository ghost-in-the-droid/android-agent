"""Typed errors raised by the skill engine.

Prod-grade agents debug on error messages. Every error includes:
  - what went wrong (message)
  - where in the flow (skill/action/step_index)
  - what state was observed (payload dict — agent-parseable)
  - what to try next (hint field where actionable)

All engine errors subclass SkillError. Runner catches SkillError and reports
structurally; catches Exception and wraps as SkillError(EngineBug).
"""
from __future__ import annotations



class SkillError(Exception):
    """Base for all skill-engine errors. Structural payload for agent-parseable output."""

    def __init__(
        self,
        message: str,
        *,
        skill: str = "",
        action: str = "",
        step_index: int = -1,
        step: dict | None = None,
        payload: dict | None = None,
        hint: str = "",
    ):
        self.message = message
        self.skill = skill
        self.action = action
        self.step_index = step_index
        self.step = step or {}
        self.payload = payload or {}
        self.hint = hint
        super().__init__(self._format())

    def _format(self) -> str:
        loc = ""
        if self.skill or self.action:
            loc = f" at {self.skill}/{self.action}"
            if self.step_index >= 0:
                loc += f" step[{self.step_index}]"
        out = f"{self.__class__.__name__}: {self.message}{loc}"
        if self.hint:
            out += f"\n  hint: {self.hint}"
        return out

    def as_dict(self) -> dict:
        return {
            "kind": self.__class__.__name__,
            "message": self.message,
            "skill": self.skill,
            "action": self.action,
            "step_index": self.step_index,
            "step": self.step,
            "payload": self.payload,
            "hint": self.hint,
        }


# ── Schema errors (loader-time) ─────────────────────────────────────────────

class SchemaError(SkillError):
    """skill.yaml doesn't conform to Schema v2."""


class SkillNotFoundError(SkillError, FileNotFoundError):
    """A skill ref or path resolved to nothing (not a path, not installed, not in the repo hub).

    Also a FileNotFoundError so pre-hub callers catching that keep working.
    """


class UnknownStepError(SkillError):
    """A step declares an `action:` or top-level key not in the dispatch registry."""


class UnknownValidatorKindError(SkillError):
    """A validator declares a `kind:` not in the validator registry."""


# ── Runtime errors ──────────────────────────────────────────────────────────

class StepFailedError(SkillError):
    """A step returned success=False (or raised) and no retry recovered."""


class ValidatorFailedError(SkillError):
    """end_state_validator returned False; action's terminal state not reached."""


class ParamError(SkillError):
    """Action called with missing required param, wrong type, or bad enum value."""


class InterpolationError(SkillError):
    """A {param} or {context.attr} reference in a step string couldn't be resolved."""


class DispatchError(SkillError):
    """Step handler raised an unexpected exception (likely engine bug or bad step schema)."""


class TimeoutError_(SkillError):
    """A wait_for / checkpoint / retry-cycle exceeded its timeout."""
    # Named with underscore to avoid shadowing builtin


class UnknownPopupError(SkillError):
    """Popup Layer 4 safety-net: an unknown modal blocked a step and dismiss cascade failed."""


class CheckpointAbortedError(SkillError):
    """HITL/external-code checkpoint was manually aborted via /runs/<id>/resume {action:abort}."""


class CheckpointTimeoutError(SkillError):
    """A v2 `checkpoint:` step was not cleared (human resume or success validator) within timeout_s.

    Deliberately not a TimeoutError_: the runner's unknown-popup retry must not re-run a human gate.
    payload: {reason, prompt, timeout_s, resolution: "timed_out"}.
    """


class CompositionError(SkillError):
    """run_skill hit max recursion depth or a circular call."""


# ── Engine-bug wrapper ──────────────────────────────────────────────────────

class EngineBug(SkillError):
    """Wraps an unexpected exception. Indicates an engine bug — file an issue."""


class AskTimeoutError(SkillError):
    """An ask timed out or no answer provider was available."""


class AskInvalidAnswerError(SkillError):
    """An answer does not satisfy the declared schema."""
