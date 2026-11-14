"""Action runner — orchestrates one action's execution.

Public API:
    result = run_action(skill, "get_active_account", params={}, device_serial="<serial>")
    # result.success, result.data, result.error, result.duration_ms, result.trace

Flow:
    1. Resolve + validate params against action.params[]
    2. Populate RunContext w/ params + device + skill's popup detectors
    3. Run pre_hooks[] in order
    4. Iterate steps[]:
       - Interpolate step (resolve {param} + {context.attr})
       - Dispatch to handler
       - Catch StepFailedError / TimeoutError_ / any → abort or wrap
    5. Evaluate end_state_validator
    6. Report structured RunResult
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from gitd.bots.common.package_policy import PackagePolicyError
from gitd.skills.engine.ask import NeedsInput
from gitd.skills.engine.context import RunContext
from gitd.skills.engine.dispatch import _fast_dump, dispatch, skill_dismiss_popups
from gitd.skills.engine.errors import (
    EngineBug,
    ParamError,
    SkillError,
    StepFailedError,
    TimeoutError_,
    UnknownPopupError,
    ValidatorFailedError,
)
from gitd.skills.engine.interpolate import interpolate
from gitd.skills.engine.loader import Param, SkillDef
from gitd.skills.engine.os_popups import sweep_if_system_dialog as os_popup_sweep
from gitd.skills.engine.pyimport import CTX_SKILL_KEY, ident_for_skill
from gitd.skills.engine.unknown_popup import (
    capture_unknown_popup,
    looks_like_new_popup,
    try_dismiss_cascade,
)
from gitd.skills.engine.validators import evaluate as evaluate_validator

from . import privacy
from .state import probe_state

log = logging.getLogger("skills.engine.runner")


@dataclass
class TraceEntry:
    step_index: int
    step: dict
    started_at: float
    duration_ms: float
    error: str | None = None
    ask: dict | None = None
    note: str | None = None  # e.g. "dry run: skipped", "checkpoint captcha: resolved (human)"

    def as_dict(self) -> dict:
        return {
            "step_index": self.step_index,
            "step": self.step,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "note": self.note,
            "ask": self.ask,
        }


@dataclass
class RunResult:
    success: bool
    status: str = field(default="completed", kw_only=True)
    resume_token: str | None = field(default=None, kw_only=True)
    prompt: str | None = field(default=None, kw_only=True)
    schema: dict | None = field(default=None, kw_only=True)
    attachments: dict | None = field(default=None, kw_only=True)
    needs_state: str | None = field(default=None, kw_only=True)
    fingerprint: dict | None = field(default=None, kw_only=True)  # distance report when the caller checked the device
    skill: str
    action: str
    data: dict = field(default_factory=dict)
    error: dict | None = None  # SkillError.as_dict() or None
    duration_ms: float = 0
    trace: list[TraceEntry] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "success": self.success,
            **({"needs_state": self.needs_state} if self.needs_state else {}),
            "status": self.status,
            "resume_token": self.resume_token,
            "prompt": self.prompt,
            "schema": self.schema,
            "attachments": self.attachments,
            "fingerprint": self.fingerprint,
            "skill": self.skill,
            "action": self.action,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "trace": [t.as_dict() for t in self.trace],
        }


def _package_guard(fn):
    import inspect
    from functools import wraps

    signature = inspect.signature(fn)

    @wraps(fn)
    def guarded(*args, **kwargs):
        import os

        from gitd.bots.common.package_policy import (
            PackagePolicyError,
            denied_packages,
            package_session,
            require_package,
        )

        if not denied_packages():
            return fn(*args, **kwargs)
        values = signature.bind(*args, **kwargs).arguments
        skill = values["skill"]
        try:
            # Even a dry run must refuse a denied skill's declared app, but it
            # never probes or changes a device.
            require_package(skill.fingerprint.app_package)
            for package in skill.fingerprint.apps:
                require_package(package)
            if values.get("dry_run"):
                return fn(*args, **kwargs)
            serial = values.get("device_serial") or os.environ.get("GHOST_DEVICE", "")
            with package_session(serial, settle=True):
                return fn(*args, **kwargs)
        except PackagePolicyError as exc:
            return RunResult(success=False, skill=skill.name, action=values["action_name"],
                             status="refused", error={"kind": "package_denied", "message": str(exc)})

    return guarded


def _device_guard(fn):
    """Resolve device_serial through the shared device normalizer before any policy or device use."""
    from gitd.bots.common.device import normalize_device_param

    def refused(exc, arguments):
        skill = arguments.get("skill")
        return RunResult(success=False, skill=getattr(skill, "name", ""), action=arguments.get("action_name", ""),
                         status="refused",
                         error={"kind": "device_ref", "message": str(exc)})

    return normalize_device_param(fn, param="device_serial", on_error=refused)


@_device_guard
@_package_guard
def run_action(
    skill: SkillDef,
    action_name: str,
    params: dict | None = None,
    device_serial: str = "",
    trace: bool = True,
    *,
    state_params: dict | None = None,
    dry_run: bool = False,
    run_id: int | None = None,
    checkpoint_channel=None,
    _resume_state=None,
    progress_callback=None,
) -> RunResult:
    """Run an action, satisfying required states (auto-login runner: beta).

    state_params maps provider action names to caller-supplied parameter mappings.
    No prompts, global state cache, or guessed credentials. One attempt per state.
    """
    options = {
        "dry_run": dry_run,
        "run_id": run_id,
        "checkpoint_channel": checkpoint_channel,
        "_resume_state": _resume_state,
        "progress_callback": progress_callback,
    }
    state_params = {} if state_params is None else state_params
    params = {} if params is None else params
    if action_name not in skill.action_names():
        return RunResult(
            success=False,
            skill=skill.name,
            action=action_name,
            error={
                "kind": "param_error",
                "message": f"Action {action_name!r} not defined on skill {skill.name!r}. "
                f"Available: [{', '.join(skill.action_names())}]",
            },
        )
    if (
        not isinstance(params, dict)
        or not isinstance(state_params, dict)
        or any(
            name not in skill.action_names() or not isinstance(values, dict) for name, values in state_params.items()
        )
    ):
        return RunResult(
            success=False,
            skill=skill.name,
            action=action_name,
            error={
                "kind": "param_error",
                "message": "Params must be mappings; state_params keys must name provider actions",
            },
        )
    secret_values = [
        mapping[p.name]
        for name, mapping in [(action_name, params), *state_params.items()]
        if isinstance(mapping, dict)
        for p in skill.action(name).params
        if p.secret and p.name in mapping
    ]
    enabled = any(p.secret for a in skill.actions for p in a.params)
    with privacy.secret_scope(secret_values, enabled):
        attempted = set((options.get("_resume_state") or {}).get("state_attempts", []))
        device = None

        def needs(action, state, reason, provider=None):
            return RunResult(
                success=False,
                status="needs_state",
                skill=skill.name,
                action=action.name,
                needs_state=state,
                error={
                    "kind": "needs_state",
                    "message": "Required state unavailable",
                    "state": state,
                    "reason": reason,
                    "provider": provider,
                },
            )

        def execute(name, supplied):
            nonlocal device
            action = skill.action(name)
            # Validate the caller's target params before making any transition.
            try:
                _resolve_params(action.params, supplied, skill.name, name)
            except SkillError as exc:
                return RunResult(success=False, skill=skill.name, action=name, error=exc.as_dict())
            if action.requires_state and not options.get("dry_run"):
                if device is None:
                    try:
                        device = _get_device(device_serial)
                    except Exception:
                        return needs(action, action.requires_state[0], "probe_unavailable")
                for state in action.requires_state:
                    observed = probe_state(skill, state, device)
                    if observed is True:
                        continue
                    if state in attempted:
                        return needs(action, state, "transition_limit")
                    providers = [a for a in skill.actions if state in a.provides_state and a.name != name]
                    if len(providers) != 1:
                        return needs(action, state, "no_provider" if not providers else "ambiguous_provider")
                    provider = providers[0]
                    if observed is None and not provider.idempotent:
                        return needs(action, state, "unknown_requires_idempotent", provider.name)
                    values = state_params.get(provider.name, {})
                    if not isinstance(values, dict):
                        return needs(action, state, "invalid_provider_params", provider.name)
                    if any(
                        p.secret and (values.get(p.name) is None or values.get(p.name) == "") for p in provider.params
                    ):
                        return needs(action, state, "missing_secret", provider.name)
                    try:
                        _resolve_params(provider.params, values, skill.name, provider.name)
                    except SkillError:
                        return needs(action, state, "missing_or_invalid_provider_params", provider.name)
                    attempted.add(state)  # before recursion; cycles cannot re-enter this transition
                    result = execute(provider.name, values)
                    if not result.success:
                        stopped = needs(
                            action,
                            state,
                            (result.error or {}).get("reason", "provider_needs_state")
                            if result.status == "needs_state"
                            else "provider_failed"
                            if result.status == "completed"
                            else "provider_" + result.status,
                            provider.name,
                        )
                        # A caller can explicitly resume a provider's HITL, then retry the target.
                        stopped.resume_token = result.resume_token
                        stopped.prompt, stopped.schema, stopped.attachments = (
                            result.prompt,
                            result.schema,
                            result.attachments,
                        )
                        stopped.data = {
                            "provider_status": result.status,
                            "provider_reason": (result.error or {}).get("reason"),
                        }
                        return stopped
                    if probe_state(skill, state, device) is not True:
                        return needs(action, state, "provider_did_not_establish_state", provider.name)
                # A later provider may clear an earlier prerequisite. Never trust declarations as a cache.
                for state in action.requires_state:
                    if probe_state(skill, state, device) is not True:
                        return needs(action, state, "state_changed")
            nested_options = {**options, "_state_attempts": attempted, "_device": device}
            if name != action_name:
                nested_options.pop("_resume_state", None)
            return _run_action(skill, name, supplied, device_serial, trace, **nested_options)

        result = execute(action_name, params)
        result.data = privacy.redact(result.data)
        result.error = privacy.redact(result.error)
        result.prompt = privacy.redact(result.prompt)
        result.schema = privacy.redact(result.schema)
        result.attachments = privacy.redact(result.attachments)
        result.trace = [TraceEntry(**privacy.redact(t.as_dict())) for t in result.trace]
        return result


def _run_action(
    skill: SkillDef,
    action_name: str,
    params: dict | None = None,
    device_serial: str = "",
    trace: bool = True,
    *,
    dry_run: bool = False,
    run_id: int | None = None,
    checkpoint_channel=None,
    _resume_state=None,
    _state_attempts=None,
    _device=None,
    progress_callback=None,
) -> RunResult:
    """Execute one action of `skill` end-to-end.

    Args:
        skill: SkillDef from load_skill().
        action_name: One of skill.action_names().
        params: User-supplied params dict.
        device_serial: ADB serial or 'ios:<udid>' — resolved to a Device wrapper.
        trace: If True (default), record per-step trace in the result. Set False
               for hot paths where trace overhead matters.
        dry_run: No device. Params are resolved and steps interpolated, `checkpoint:`
               steps run (and resolve immediately), every other step and the
               end_state_validator are skipped and noted in the trace.
        run_id: SkillRun id; checkpoint steps then signal/poll that run (engine/hitl.py).
        checkpoint_channel: explicit checkpoint control channel (wins over run_id).
        progress_callback: Optional callback(TraceEntry) after each traced step completes.

    Returns:
        RunResult — always returns; never raises. success=False + error dict on failure.
    """
    started = time.monotonic()
    if action_name not in skill.action_names():
        return RunResult(
            success=False,
            skill=skill.name,
            action=action_name,
            error={
                "kind": "param_error",
                "message": f"Action {action_name!r} not defined on skill {skill.name!r}. "
                f"Available: [{', '.join(skill.action_names())}]",
            },
        )
    action = skill.action(action_name)

    class ProgressTrace(list):
        def append(self, entry):
            super().append(entry)
            if progress_callback is not None:
                try:
                    progress_callback(TraceEntry(**privacy.redact(entry.as_dict())))
                except Exception:
                    log.warning("Live trace callback failed", exc_info=True)

    trace_log: list[TraceEntry] = ProgressTrace()
    ctx = RunContext(action_name=action_name, device_serial=device_serial)
    ctx.extras["_state_attempts"] = _state_attempts or set()

    try:
        resolved_params = _resolve_params(action.params, params or {}, skill.name, action.name)
        ctx.params = resolved_params

        device = None if dry_run else (_device if _device is not None else _get_device(device_serial))
        if device is not None:
            ctx.device_serial = device_serial or getattr(device, "serial", "")
        if dry_run:
            ctx.extras["_dry_run"] = True
        if run_id is not None:
            ctx.extras["_run_id"] = run_id
        if checkpoint_channel is not None:
            ctx.extras["_checkpoint_channel"] = checkpoint_channel

        # Popup detectors → context for `dismiss_popups` step to read
        ctx.extras["_skill_popup_detectors"] = skill.popup_detectors
        # Layer 1: OS popup policy (per-skill overrides)
        ctx.extras["_os_popup_policy"] = skill.os_popup_policy
        # Skill-dir for subroutine lookup (subroutine step primitive resolves via this)
        ctx.extras["_current_skill_dir"] = str(skill.skill_dir)
        # Identity for skill-local python_action / custom_python imports (engine/pyimport.py)
        ctx.extras[CTX_SKILL_KEY] = ident_for_skill(skill)

        if _resume_state:
            ctx.extras.update(_resume_state["extras"])
            ctx.result = _resume_state["result"]
            trace_log.extend(TraceEntry(**t) for t in _resume_state["trace"])

        # 1. pre_hooks
        for hook in [] if _resume_state else action.pre_hooks:
            _run_step(hook, ctx, device, trace_log, trace, is_hook=True)

        # 2. steps
        ctx.step_count = len(action.steps)
        for i, step in enumerate(action.steps):
            if _resume_state and i < _resume_state["next_step"]:
                continue
            ctx.step_index = i
            _run_step(step, ctx, device, trace_log, trace)

        checkpoints = ctx.extras.get("_checkpoints")
        if checkpoints:
            ctx.result["checkpoints"] = checkpoints
        if dry_run:
            ctx.result["dry_run"] = True
            return RunResult(
                success=True,
                skill=skill.name,
                action=action.name,
                data=ctx.result,
                duration_ms=(time.monotonic() - started) * 1000,
                trace=trace_log,
            )

        # 3. end_state_validator (must interpolate placeholders like @{handle})
        if action.end_state_validator:
            resolved_validator = interpolate(action.end_state_validator, ctx)
            passed = evaluate_validator(resolved_validator, ctx, device)
            if not passed:
                raise ValidatorFailedError(
                    "end_state_validator returned False — action's terminal state not reached",
                    skill=skill.name,
                    action=action.name,
                    payload={"validator": action.end_state_validator, "result": ctx.result},
                    hint="Check the current screen — did steps complete but land somewhere unexpected? "
                    "Screenshot + inspect a11y tree to diagnose.",
                )

        duration_ms = (time.monotonic() - started) * 1000
        return RunResult(
            success=True,
            skill=skill.name,
            action=action.name,
            data=ctx.result,
            duration_ms=duration_ms,
            trace=trace_log,
        )

    except NeedsInput as e:
        from .ask_resume import persist

        token = persist(skill, action_name, ctx, trace_log, e)
        return RunResult(
            success=False,
            status="needs_input",
            resume_token=token,
            prompt=e.spec["prompt"],
            schema=e.spec["schema"],
            attachments=e.attachments,
            skill=skill.name,
            action=action_name,
            trace=trace_log,
            data={**ctx.result, "prompt": e.spec["prompt"], "schema": e.spec["schema"], "attachments": e.attachments},
        )
    except SkillError as e:
        # Enrich with skill/action if missing
        if not e.skill:
            e.skill = skill.name
        if not e.action:
            e.action = action_name
        duration_ms = (time.monotonic() - started) * 1000
        log.warning("run_action failed: %s", e)
        return RunResult(
            success=False,
            skill=skill.name,
            action=action_name,
            data=ctx.result,
            error=e.as_dict(),
            duration_ms=duration_ms,
            trace=trace_log,
        )

    except PackagePolicyError as e:
        return RunResult(success=False, skill=skill.name, action=action_name, status="refused",
                         error={"kind": "package_denied", "message": str(e)}, trace=trace_log)

    except Exception as e:
        # Unexpected — engine bug
        tb = traceback.format_exc()
        duration_ms = (time.monotonic() - started) * 1000
        log.error("run_action engine-bug wrap:\n%s", tb)
        bug = EngineBug(
            f"Unexpected {type(e).__name__}: {e}",
            skill=skill.name,
            action=action_name,
            payload={"traceback": tb},
            hint="This is likely an engine bug. File an issue with the traceback above.",
        )
        return RunResult(
            success=False,
            skill=skill.name,
            action=action_name,
            data=ctx.result,
            error=bug.as_dict(),
            duration_ms=duration_ms,
            trace=trace_log,
        )


# ── Internals ────────────────────────────────────────────────────────────────


def _resolve_params(defs: list[Param], provided: dict, skill_name: str, action_name: str) -> dict:
    """Validate + fill defaults + type-check provided params against action's params[]."""
    resolved = {}
    provided_names = set(provided.keys())
    def_names = {p.name for p in defs}

    unknown = provided_names - def_names
    if unknown:
        raise ParamError(
            f"Unknown params: {sorted(unknown)}",
            skill=skill_name,
            action=action_name,
            hint=f"Accepted params: {sorted(def_names) or '(none)'}",
        )

    for p in defs:
        if p.secret and (not isinstance(provided.get(p.name), str) or not provided[p.name]):
            raise ParamError(f"Missing secret param {p.name!r}; supply a nonempty runtime string")
        if p.name in provided:
            val = provided[p.name]
        elif p.default is not None:
            val = p.default
        elif p.required:
            raise ParamError(
                f"Missing required param {p.name!r}",
                skill=skill_name,
                action=action_name,
                hint=f"Type: {p.type}. {p.description}",
            )
        else:
            val = None

        # Enum validation
        if p.type == "enum" and val is not None:
            # CLI values remain text until the declaration is known. Prefer an
            # exact string choice; otherwise allow a declared JSON scalar/value.
            if p.values and val not in p.values and isinstance(val, str):
                try:
                    candidate = json.loads(val)
                except ValueError:
                    candidate = val
                if candidate is not None and candidate in p.values:
                    val = candidate
            if p.values and val not in p.values:
                raise ParamError(
                    f"Param {p.name!r}={val!r} not in {p.values}",
                    skill=skill_name,
                    action=action_name,
                )

        # Coerce according to the declaration, regardless of the caller's transport.
        if val is not None:
            try:
                if p.type == "int":
                    val = int(val)
                elif p.type == "float":
                    val = float(val)
                elif p.type == "bool":
                    val = _to_bool(val)
                elif p.type in {"str", "path"}:
                    val = str(val)
                elif p.type == "list[str]" and isinstance(val, str):
                    # CLI gives strings: accept JSON ("[\"a\",\"b\"]"), bracketed ("[a,b]") or bare ("a,b").
                    txt = val.strip()
                    try:
                        parsed = json.loads(txt)
                        val = [str(x) for x in parsed] if isinstance(parsed, list) else [str(parsed)]
                    except ValueError:
                        val = [t.strip() for t in txt.strip("[]").split(",") if t.strip()]
                # enum values retain their declared type for membership checking.
            except (ValueError, TypeError) as e:
                raise ParamError(
                    f"Param {p.name!r}={val!r} cannot coerce to {p.type}: {e}",
                    skill=skill_name,
                    action=action_name,
                ) from e

        resolved[p.name] = val

    return resolved


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.lower() in {"true", "yes", "1", "on"}
    return bool(v)


def _get_device(serial: str):
    """Resolve serial → Device wrapper (Android) or iOS device handle."""
    if not serial:
        import os

        serial = os.environ.get("GHOST_DEVICE", "")
    if serial.startswith("fake:"):
        from gitd.skills.engine.fake_device import FakeDevice

        return FakeDevice(serial)
    if not serial:
        raise ParamError(
            "device_serial required — no device connected",
            hint="Pass device_serial='<serial>' to run_action, or set DEFAULT_DEVICE env.",
        )
    if serial.startswith("ios:"):
        from gitd.bots.common.device import get_device

        return get_device(serial)
    from gitd.bots.common.adb import Device

    return Device(serial)


def _run_step(step: dict, ctx: RunContext, device, trace_log: list, do_trace: bool, is_hook: bool = False) -> None:
    """Interpolate + dispatch one step. Records trace entry on completion.

    Popup handling Layer 2: auto-dismiss known popups before each step (unless
    the step itself is dismiss_popups, to avoid recursion).
    """
    do_trace = do_trace or "ask" in step
    started = time.monotonic()
    step_i = ctx.step_index if not is_hook else -1
    entry = TraceEntry(step_index=step_i, step=step, started_at=started, duration_ms=0)

    privacy.guard_step(step)
    if ctx.extras.get("_dry_run") and "checkpoint" not in step and "ask" not in step:
        interpolate(step, ctx)  # still surfaces missing {params}
        entry.note = "dry run: skipped (needs a device)"
        if do_trace:
            trace_log.append(entry)
        return

    try:
        # Layer 2 auto-dismiss — only before steps that READ the a11y tree.
        # Portal dumps are ~14s on video apps, so blind ops (sleep, tap, press_key,
        # launch_app, launch_intent, type_text) skip the pre-sweep. Steps that
        # consume a11y run their own mid-poll popup sweep in their handler.
        _A11Y_READERS = {"tap_element", "wait_for_text", "wait_for_element", "dump_xml", "read_text", "tap_nth"}
        _step_action = step.get("action")
        _is_reader = _step_action in _A11Y_READERS or "if_visible" in step or "for_each" in step
        xml_before = None  # a11y snapshot for the Layer-4 diff; one dump, reused by the pre-sweep
        if not privacy.sensitive() and _is_reader and _step_action != "dismiss_popups" and device is not None:
            # Layer 1: OS permission/system dialogs (Portal cannot see them), per os_popup_policy.
            try:
                os_popup_sweep(device, ctx.extras.get("_os_popup_policy"))
            except Exception as oe:
                log.debug("os popup sweep raised %s: %s (continuing)", type(oe).__name__, oe)
            try:
                xml_before = _fast_dump(device)
            except Exception as de:
                log.debug("pre-step dump raised %s: %s (Layer 4 disabled for this step)", type(de).__name__, de)
            popups = ctx.extras.get("_skill_popup_detectors") or []
            if popups and xml_before is not None:
                try:
                    skill_dismiss_popups(device, ctx, xml_before)
                except Exception as pe:
                    # Popup-dismissal failure shouldn't kill the step — log + continue
                    log.debug("popup pre-sweep raised %s: %s (continuing)", type(pe).__name__, pe)

        # Interpolate step (resolves {param} + {context.attr} in string values)
        resolved_step = interpolate(step, ctx)
        try:
            dispatch(resolved_step, ctx, device)
        except (StepFailedError, TimeoutError_) as first_err:
            # Layer 4: unknown-popup safety net — retry ONCE after dismiss cascade
            xml_after = _fast_dump(device) if (device is not None and xml_before is not None) else None
            if xml_before is not None and xml_after is not None and looks_like_new_popup(xml_before, xml_after):
                log.warning("Layer 4: unknown popup detected after step failure — dismiss cascade + retry once")
                try_dismiss_cascade(device)
                time.sleep(1)
                try:
                    dispatch(resolved_step, ctx, device)
                    return  # retry succeeded — skip trace error path below
                except (StepFailedError, TimeoutError_):
                    # Retry still failed — capture screenshot for author to add to catalog
                    screenshot_path = capture_unknown_popup(device, ctx)
                    raise UnknownPopupError(
                        f"Unknown popup blocked step; dismiss cascade + retry failed. Screenshot: {screenshot_path}",
                        step=step,
                        payload={"screenshot": screenshot_path, "original_error": first_err.message},
                        hint=f"Inspect {screenshot_path}, add a `popup_detectors:` entry matching the modal, and re-run.",
                    ) from first_err
            raise
    except SkillError as e:
        entry.duration_ms = (time.monotonic() - started) * 1000
        entry.ask = ctx.extras.pop("_ask_trace", None)
        entry.error = None if isinstance(e, NeedsInput) else e.message
        entry.note = ctx.extras.pop("_trace_note", None)
        if do_trace:
            trace_log.append(entry)
        # Enrich with step index if missing
        if e.step_index < 0:
            e.step_index = step_i
        if not e.step:
            e.step = step
        raise
    entry.duration_ms = (time.monotonic() - started) * 1000
    entry.note = ctx.extras.pop("_trace_note", None)
    entry.ask = ctx.extras.pop("_ask_trace", None)
    if do_trace:
        trace_log.append(entry)
