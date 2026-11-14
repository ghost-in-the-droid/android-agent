"""Step dispatch table — every yaml step type → a handler function.

Pluggable: `@register_step("my_custom")` decorator lets skills or plugins add
step types at runtime. Built-in handlers below cover the Schema v2 primitive set.

Handler signature:
    def handler(step: dict, ctx: RunContext, device) -> None
        # Raise on failure (StepFailedError, TimeoutError_, DispatchError)
        # Write to ctx.result / ctx.<extras> for downstream steps
        # Return None (implicit success)

Post-interpolation guarantee: by the time a handler runs, every string field in
`step` has {param} placeholders resolved. Handlers work with plain values.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from gitd.skills.engine.context import RunContext
from gitd.skills.engine.errors import (
    DispatchError,
    ParamError,
    SkillError,
    StepFailedError,
    TimeoutError_,
    UnknownStepError,
)
from gitd.skills.engine.pyimport import CTX_SKILL_KEY
from gitd.skills.engine.pyimport import ident_for_skill as skill_ident

from . import privacy

# ── Fast a11y dump for polling ────────────────────────────────────────────
# Device.dump_xml() uses Droidrun Portal which returns a deep tree — 666KB and
# 13s on TT. For skill polling we only need the CLI uiautomator dump (~57KB,
# ~500ms). This helper bypasses Portal.


def _fast_dump(device) -> str:
    """Direct uiautomator dump → xml string. ~500ms vs Device.dump_xml's ~13s on TT.

    Reads Ghost Portal first when the device has it. Otherwise uses
    `uiautomator dump --compressed`; on some builds (API 34 emulators) that
    still waits for idle and fails on animating screens, and then this falls
    back to device.dump_xml(). Returns
    a smaller/filtered tree than the default dump but retains all visible elements
    with their bounds + content-desc + text + resource-id — everything skills need.

    Falls back to device.dump_xml() if the direct path errors (Portal-only device
    profiles, iOS, etc.).
    """
    if privacy.sensitive():
        return privacy.dump_xml(device)
    if getattr(device, "is_fake", False):
        return device.dump_xml()
    serial = getattr(device, "serial", None)
    if not serial:
        return device.dump_xml()
    # Portal first: ~0.4 s and immune to idle waits. A running uiautomator dump
    # also suspends accessibility services, so it must not go first.
    portal = getattr(device, "dump_portal_xml", None)
    if callable(portal):
        xml = portal()
        if xml:
            return xml
    xml = _uiautomator_dump(serial)
    if xml:
        return xml
    return device.dump_xml()


def _uiautomator_dump(serial: str) -> str | None:
    """`uiautomator dump --compressed`, or None if it failed. The file is removed first:
    a failed dump ("could not get idle state", which --compressed does not avoid on
    API 34) must not hand back the previous screen's file."""
    import subprocess

    try:
        d = subprocess.run(
            [
                "adb",
                "-s",
                serial,
                "shell",
                "rm -f /sdcard/_ghost_ui.xml; uiautomator dump --compressed /sdcard/_ghost_ui.xml",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=6,
        )
        if "dumped to" not in (d.stdout or ""):
            return None
        r = subprocess.run(
            ["adb", "-s", serial, "exec-out", "cat", "/sdcard/_ghost_ui.xml"],
            capture_output=True,
            text=True,
            timeout=4,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
    except Exception:
        pass
    return None


def skill_dismiss_popups(device, ctx, xml: str | None = None) -> bool:
    """Layer 2 sweep with the skill's popup_detectors. When the skill declares
    popup_detectors or an os_popup_policy, the device's generic Cancel/Skip/Later
    fallback is off: v2 relies on Layer 1 + Layer 2 + the Layer 4 BACK cascade."""
    if privacy.sensitive():
        return False
    popups = ctx.extras.get("_skill_popup_detectors") or []
    generic = not (popups or ctx.extras.get("_os_popup_policy"))
    import inspect

    try:
        takes_flag = "generic" in inspect.signature(device.dismiss_popups).parameters
    except (TypeError, ValueError):
        takes_flag = False
    if takes_flag:
        return device.dismiss_popups(xml=xml, popups=popups, generic=generic)
    # Backends without the flag (fake, iOS) have no generic fallback to disable.
    return device.dismiss_popups(xml=xml, popups=popups)


log = logging.getLogger("skills.engine.dispatch")

# Handler registry — step type name → callable
_HANDLERS: dict[str, Callable[[dict, RunContext, Any], None]] = {}


def register_step(name: str) -> Callable[[Callable], Callable]:
    """Decorator: register a step handler.

    Example:
        @register_step("my_custom_op")
        def _my_custom_op(step, ctx, device):
            ...
    """

    def wrap(fn):
        if name in _HANDLERS:
            log.warning("Overriding registered step handler %r", name)
        _HANDLERS[name] = fn
        return fn

    return wrap


def dispatch(step: dict, ctx: RunContext, device) -> None:
    from gitd.bots.common.package_policy import check_tool_target, package_session

    with package_session(ctx.device_serial):
        check_tool_target(step.get("action", ""), step)
        return _dispatch_inner(step, ctx, device)


def _dispatch_inner(step: dict, ctx: RunContext, device) -> None:
    """Dispatch one step (post-interpolation) to its handler.

    A step is EITHER:
      - {action: <name>, ...args}        — atomic op keyed by `action:`
      - {python_action: <mod:fn>, ...}   — escape hatch keyed by `python_action:`
      - {if_visible: {...}}              — control flow keyed by structural key
      - {retry: {...}}                   — control flow
      - {run_skill: {...}}               — composition (Phase 2)
      - {checkpoint: {...}}              — HITL gate (Phase 2)

    Handler is looked up by the first recognized key.
    """
    privacy.guard_step(step)
    # Structural keys (dict-typed control flow) take priority over `action:`
    for key in (
        "python_action",
        "if_visible",
        "retry",
        "run_skill",
        "subroutine",
        "checkpoint",
        "ask",
        "pre_hooks",
        "for_each",
    ):
        if key in step:
            handler = _HANDLERS.get(key)
            if handler is None:
                raise UnknownStepError(
                    f"Step key {key!r} has no registered handler",
                    step=step,
                    hint=f"Registered step types: {sorted(_HANDLERS.keys())}",
                )
            return handler(step, ctx, device)

    action = step.get("action")
    if not action:
        raise UnknownStepError(
            "Step must declare `action:`, `python_action:`, or one of {if_visible, retry, run_skill, subroutine, checkpoint}",
            step=step,
        )
    handler = _HANDLERS.get(action)
    if handler is None:
        raise UnknownStepError(
            f"Unknown step action {action!r}",
            step=step,
            hint=f"Registered step types: {sorted(_HANDLERS.keys())}",
        )
    return handler(step, ctx, device)


# ═══════════════════════════════════════════════════════════════════════════
# Atomic device interactions
# ═══════════════════════════════════════════════════════════════════════════


@register_step("tap")
def _tap(step, ctx, device):
    x, y = step.get("x"), step.get("y")
    if x is None or y is None:
        raise ParamError("tap requires x, y", step=step)
    delay_s = float(step.get("delay_s", 0.6))
    device.tap(int(x), int(y), delay_s)


@register_step("tap_element")
def _tap_element(step, ctx, device):
    """Locator chain: id → desc → text → xpath. First match wins.

    Parses bounds from a11y XML directly (Device.tap_text/tap_desc signatures
    vary — this path is portable).
    """
    xml = _fast_dump(device)
    for locator in ("id", "desc", "text"):
        target = step.get(locator)
        if not target:
            continue
        b = _find_bounds(xml, locator, target)
        if b is not None and not (b[2] > b[0] and b[3] > b[1] and b[0] >= 0 and b[1] >= 0):
            raise StepFailedError(
                f"tap_element: {locator}={target!r} exists but is off screen (bounds {b})",
                step=step,
                hint="Scroll it into view first, or wait for the screen to settle.",
            )
        if b is None:
            raise StepFailedError(
                f"tap_element: no element matches {locator}={target!r}",
                step=step,
                payload={"xml_size": len(xml)},
                hint="Check the a11y tree — dump_xml shows current state. Element may not have rendered yet; consider wait_for_element before this step.",
            )
        cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
        device.tap(cx, cy)
        return

    if step.get("xpath"):
        raise DispatchError("tap_element: xpath support not yet implemented; use id/desc/text", step=step)

    raise ParamError(
        "tap_element requires one of: id, desc, text, xpath",
        step=step,
        hint="Use `desc:` for content-desc (most stable), `id:` for resource-id, `text:` for visible text.",
    )


@register_step("type_text")
def _type_text(step, ctx, device):
    text = step.get("text", "")
    if step.get("clear_first"):
        # Select-all + delete (Android)
        device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(200):
            device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    if not text:
        return
    try:
        from gitd.bots.common.adb import input_text_arg

        device.adb("shell", "input", "text", input_text_arg(text))
    except ImportError:
        # Fallback: raw input text (unsafe for shell metachars)
        device.adb("shell", "input", "text", text.replace(" ", "%s"))


@register_step("long_press")
def _long_press(step, ctx, device):
    """`x, y` or a locator (`id|desc|text`, optional `index`): centre of the matched node."""
    x, y = step.get("x"), step.get("y")
    if x is None or y is None:
        node = _nth_node(_fast_dump(device), step, step)
        left, top, right, bottom = node["bounds"]
        x, y = (left + right) // 2, (top + bottom) // 2
    duration_ms = int(step.get("duration_ms", 800))
    # Use swipe with same start/end for long-press
    device.adb("shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms))


@register_step("swipe")
def _swipe(step, ctx, device):
    x1, y1, x2, y2 = step["x1"], step["y1"], step["x2"], step["y2"]
    duration_ms = int(step.get("duration_ms", 300))
    device.adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))


@register_step("press_key")
def _press_key(step, ctx, device):
    """Press an Android keycode. Use Device shortcut methods where available
    (back / home), else fall back to `adb shell input keyevent`."""
    key = step.get("key", "").upper()
    if not key:
        raise ParamError("press_key requires `key:` (e.g. BACK, HOME, ENTER)", step=step)
    key_short = key.replace("KEYCODE_", "")

    # Prefer Device shortcut methods (Device.back / Device.home have delays baked in)
    method = getattr(device, key_short.lower(), None)
    if callable(method):
        try:
            method()
            return
        except TypeError:
            # Method exists but takes args we don't have — fall through
            pass

    # Direct adb keyevent
    keycode = key if key.startswith("KEYCODE_") else f"KEYCODE_{key}"
    device.adb("shell", "input", "keyevent", keycode)


@register_step("launch_app")
def _launch_app(step, ctx, device):
    pkg = step.get("package", "")
    if not pkg:
        raise ParamError("launch_app requires `package:`", step=step)
    activity = step.get("activity")
    if activity:
        device.adb("shell", "am", "start", "-n", f"{pkg}/{activity}")
    else:
        device.adb("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")


@register_step("launch_intent")
def _launch_intent(step, ctx, device):
    """Full android.content.Intent — supports SEND (share), VIEW (deep link), etc.

    Builds `am start` directly (rather than routing through
    gitd.services.device_context.launch_intent) because that service doesn't
    accept `mime_type:` — which is REQUIRED for SEND intents to route through
    an app's share filter (e.g. TikTok video upload).
    """
    intent_action = step.get("intent_action", "")
    if not intent_action:
        raise ParamError("launch_intent requires `intent_action:` (e.g. android.intent.action.SEND)", step=step)

    cmd = ["shell", "am", "start"]
    cmd.extend(["-a", intent_action])
    if data := step.get("data"):
        cmd.extend(["-d", data])
    if mime_type := step.get("mime_type"):
        cmd.extend(["-t", mime_type])
    if category := step.get("category"):
        cmd.extend(["-c", category])
    pkg = step.get("package", "")
    act = step.get("activity", "")
    if pkg and act:
        cmd.extend(["-n", f"{pkg}/{act}"])
    elif pkg:
        cmd.extend(["-p", pkg])
    extras = step.get("extras") or {}
    for k, v in extras.items():
        if isinstance(v, bool):
            cmd.extend(["--ez", k, str(v).lower()])
        elif isinstance(v, int):
            cmd.extend(["--ei", k, str(v)])
        elif isinstance(v, str) and (v.startswith("content://") or v.startswith("file://")):
            # URI extras need --eu (Android intents expect Uri objects for STREAM etc.)
            cmd.extend(["--eu", k, v])
        else:
            cmd.extend(["--es", k, str(v)])
    # `adb shell` joins its arguments with spaces and the device shell re-splits
    # them, so quote every word: values with spaces ("+1 555 0100") stay whole.
    import shlex

    device.adb(cmd[0], *(shlex.quote(str(c)) for c in cmd[1:]))


@register_step("open_url")
def _open_url(step, ctx, device):
    from gitd.services.device_context import launch_intent as _fn

    url = step.get("url", "")
    if not url:
        raise ParamError("open_url requires `url:`", step=step)
    _fn(
        device=device.serial if hasattr(device, "serial") else str(device),
        action="android.intent.action.VIEW",
        data=url,
        package=step.get("browser", ""),
    )


@register_step("screenshot")
def _screenshot(step, ctx, device):
    save_as = step.get("save_as")
    remote = "/sdcard/_ghost_skill_screenshot.png"
    device.adb("shell", "screencap", "-p", remote)
    if save_as:
        Path(save_as).parent.mkdir(parents=True, exist_ok=True)
        device.adb("pull", remote, save_as)


@register_step("dump_xml")
def _dump_xml(step, ctx, device):
    xml = _fast_dump(device)
    save_as = step.get("save_as")
    if save_as:
        Path(save_as).parent.mkdir(parents=True, exist_ok=True)
        Path(save_as).write_text(xml)
    ctx.last_xml = xml


@register_step("dismiss_popups")
def _dismiss_popups(step, ctx, device):
    """Run the skill's popup_detectors once."""
    skill_dismiss_popups(device, ctx)


# ═══════════════════════════════════════════════════════════════════════════
# Waits
# ═══════════════════════════════════════════════════════════════════════════


@register_step("wait_for_text")
def _wait_for_text(step, ctx, device):
    text = step.get("text", "")
    timeout_s = float(step.get("timeout_s", 10))
    popups = ctx.extras.get("_skill_popup_detectors") or []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        xml = _fast_dump(device)
        if text in xml:
            return
        # Mid-poll popup sweep (Layer 2)
        if popups:
            try:
                skill_dismiss_popups(device, ctx, xml)
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError_(
        f"wait_for_text({text!r}) exceeded {timeout_s}s",
        step=step,
        hint="Element may not have rendered. Try screenshot + inspect, or increase timeout_s. "
        "Also verify no unhandled popup is blocking — add a popup_detectors entry if you see one.",
    )


@register_step("wait_for_element")
def _wait_for_element(step, ctx, device):
    timeout_s = float(step.get("timeout_s", 10))
    popups = ctx.extras.get("_skill_popup_detectors") or []
    deadline = time.monotonic() + timeout_s
    for locator in ("id", "desc", "text", "xpath"):
        target = step.get(locator)
        if not target:
            continue
        while time.monotonic() < deadline:
            xml = _fast_dump(device)
            if _find_bounds(xml, locator, target) is not None:
                return
            # Mid-poll popup sweep (Layer 2)
            if popups:
                try:
                    skill_dismiss_popups(device, ctx, xml)
                except Exception:
                    pass
            time.sleep(0.5)
        raise TimeoutError_(
            f"wait_for_element({locator}={target!r}) exceeded {timeout_s}s",
            step=step,
            hint="Element may not have rendered. Check current dump_xml + screenshot. "
            "Also verify no unhandled popup is blocking.",
        )
    raise ParamError("wait_for_element requires one of: id, desc, text, xpath", step=step)


@register_step("sleep")
def _sleep(step, ctx, device):
    duration_s = float(step.get("duration_s", 1))
    time.sleep(duration_s)


# ═══════════════════════════════════════════════════════════════════════════
# Escape hatch — python_action
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# Control flow — Phase 2 primitives
# ═══════════════════════════════════════════════════════════════════════════


@register_step("if_visible")
def _if_visible(step, ctx, device):
    """Conditional branching: if selector present → run `then` steps; else `else`.

    step = {if_visible: {selector: {id|desc|text}, then: [...], else?: [...]}}
    """
    spec = step["if_visible"]
    selector = spec.get("selector") or {}
    if not selector:
        raise ParamError("if_visible: `selector:` required (id/desc/text)", step=step)
    xml = _fast_dump(device)
    matched = False
    for locator in ("id", "desc", "text"):
        target = selector.get(locator)
        if target and _find_bounds(xml, locator, target) is not None:
            matched = True
            break
    branch = spec.get("then" if matched else "else") or []
    for sub in branch:
        # Recursively dispatch each sub-step (no popup pre-sweep — caller already did)
        dispatch(sub, ctx, device)


@register_step("retry")
def _retry(step, ctx, device):
    """Wrap a step-list in a retry loop.

    step = {retry: {max: 3, backoff_s: 1, steps: [...], on_failure?: <step>}}
    """
    spec = step["retry"]
    max_attempts = int(spec.get("max", 2))
    backoff_s = float(spec.get("backoff_s", 1))
    steps = spec.get("steps") or []
    on_failure = spec.get("on_failure")
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            for sub in steps:
                dispatch(sub, ctx, device)
            return  # all inner steps succeeded
        except (StepFailedError, TimeoutError_) as e:
            last_err = e
            log.info(
                "retry: attempt %d/%d failed (%s); backoff %.1fs",
                attempt,
                max_attempts,
                e.__class__.__name__,
                backoff_s,
            )
            time.sleep(backoff_s)
    # Exhausted
    if on_failure:
        dispatch(on_failure, ctx, device)
        return
    raise StepFailedError(
        f"retry exhausted after {max_attempts} attempts: {last_err.message if last_err else 'unknown'}",
        step=step,
    )


@register_step("subroutine")
def _subroutine(step, ctx, device):
    """Expand a named subroutine defined in the current skill.

    step = {subroutine: <name>}

    Subroutines are internal reusable step-lists (see loader.SubroutineDef).
    They de-dup boilerplate within a skill (nav_to_profile_tab, open_switcher_drawer,
    etc.) without requiring the boilerplate to become a top-level agent-invocable
    action.

    Recursion + cycle guard: same as run_skill (max depth 5, no self-reference).
    Shares RunContext (params + result + extras).
    """
    name = step["subroutine"]
    if not isinstance(name, str) or not name:
        raise ParamError("subroutine: name must be a non-empty string", step=step)

    # Find current skill via ctx._current_skill_dir (set by runner + run_skill)
    from pathlib import Path

    from gitd.skills.engine.interpolate import interpolate as _interp
    from gitd.skills.engine.loader import load_skill

    skill_dir = ctx.extras.get("_current_skill_dir")
    if not skill_dir:
        raise ParamError(
            "subroutine: no current skill in RunContext",
            step=step,
            hint="Subroutine steps only work inside a skill's action/pre_hooks. "
            "Runner should have set ctx.extras['_current_skill_dir'].",
        )

    skill = load_skill(Path(skill_dir))
    sub = skill.subroutine(name)  # raises KeyError w/ helpful msg if missing

    # Recursion + cycle guard (shared with run_skill via same stack key)
    call_stack = ctx.extras.setdefault("_subroutine_stack", [])
    if len(call_stack) >= 5:
        from gitd.skills.engine.errors import CompositionError

        raise CompositionError(
            "subroutine: max recursion depth (5) exceeded",
            step=step,
            payload={"stack": call_stack},
        )
    if name in call_stack:
        from gitd.skills.engine.errors import CompositionError

        raise CompositionError(
            f"subroutine: circular call — {name!r} already on stack",
            step=step,
            payload={"stack": call_stack},
        )

    call_stack.append(name)
    try:
        for sub_step in sub.steps:
            dispatch(_interp(sub_step, ctx), ctx, device)
    finally:
        call_stack.pop()


@register_step("run_skill")
def _run_skill(step, ctx, device):
    """Compose skills: run another skill's action from within this step chain.

    step = {run_skill: {name: <user>/<slug>, action: <action_name>, params?: {...}}}

    Shares the RunContext — invoked action can read/write ctx.result + ctx.extras.
    Max recursion depth: 5. Circular-call detection via call stack.
    """
    spec = step["run_skill"]
    skill_ref = spec.get("name", "")
    action_name = spec.get("action", "")
    inner_params = spec.get("params") or {}
    if not skill_ref or not action_name:
        raise ParamError(
            "run_skill: both `name:` and `action:` required",
            step=step,
        )

    # Recursion + cycle guard
    call_stack = ctx.extras.setdefault("_run_skill_stack", [])
    if len(call_stack) >= 5:
        from gitd.skills.engine.errors import CompositionError

        raise CompositionError(
            "run_skill: max recursion depth (5) exceeded",
            step=step,
            payload={"stack": call_stack},
        )
    call_key = f"{skill_ref}:{action_name}"
    if call_key in call_stack:
        from gitd.skills.engine.errors import CompositionError

        raise CompositionError(
            f"run_skill: circular call — {call_key} already on the stack",
            step=step,
            payload={"stack": call_stack},
        )

    # Load target skill: path, installed hub skill, or repo skillhub/ (loader resolution order)
    from gitd.skills.engine.errors import SkillNotFoundError
    from gitd.skills.engine.loader import load_skill

    try:
        target = load_skill(skill_ref)
    except SkillNotFoundError as e:
        raise ParamError(
            f"run_skill: skill {skill_ref!r} not found",
            step=step,
            payload=e.payload,
            hint=e.hint,
        ) from e

    # Execute target action inline with shared context
    call_stack.append(call_key)
    try:
        target_action = target.action(action_name)
        # Push/pop skill_dir so nested run_skill resolves relative to the RIGHT skill
        prev_skill_dir = ctx.extras.get("_current_skill_dir")
        prev_skill_ident = ctx.extras.get(CTX_SKILL_KEY)
        ctx.extras["_current_skill_dir"] = str(target.skill_dir)
        ctx.extras[CTX_SKILL_KEY] = skill_ident(target)
        # Merge inner_params for the sub-action's params — but don't clobber caller
        prev_params = ctx.params
        ctx.params = _resolve_sub_params(target_action.params, inner_params)
        try:
            for sub_step in target_action.steps:
                # Interpolate + dispatch each step of the target action
                from gitd.skills.engine.interpolate import interpolate as _interp

                dispatch(_interp(sub_step, ctx), ctx, device)
        finally:
            ctx.params = prev_params
            if prev_skill_dir is not None:
                ctx.extras["_current_skill_dir"] = prev_skill_dir
            else:
                ctx.extras.pop("_current_skill_dir", None)
            if prev_skill_ident is not None:
                ctx.extras[CTX_SKILL_KEY] = prev_skill_ident
            else:
                ctx.extras.pop(CTX_SKILL_KEY, None)
    finally:
        call_stack.pop()


def _resolve_sub_params(defs, provided):
    """Simple version of runner's _resolve_params for the composition path."""
    resolved = {}
    for p in defs:
        if p.name in provided:
            resolved[p.name] = provided[p.name]
        elif p.default is not None:
            resolved[p.name] = p.default
        else:
            resolved[p.name] = None
    return resolved


@register_step("checkpoint")
def _checkpoint(step, ctx, device):
    """Human-in-the-loop gate: `{checkpoint: {reason, prompt, success?, timeout_s?, poll_s?}}`.

    Pauses the run and publishes reason + prompt through the run's control channel
    (engine/hitl.py; SkillRun-backed when run_action got a run_id, as on origin/main),
    then polls until whichever fires first: a human `resume` / `abort` on the channel,
    or the `success:` validator passing. timeout_s defaults to 600; 0 waits
    indefinitely. Timeout raises CheckpointTimeoutError, abort CheckpointAbortedError.
    Dry mode (no device) resolves immediately. With no channel and no success
    validator nothing could ever clear the gate, so it is skipped (as v1.5 does).
    """
    from gitd.skills import checkpoint as ckpt
    from gitd.skills.engine import hitl
    from gitd.skills.engine.errors import CheckpointAbortedError, CheckpointTimeoutError
    from gitd.skills.engine.validators import evaluate

    spec = step.get("checkpoint")
    if not isinstance(spec, dict):
        raise ParamError("checkpoint: expects a mapping {reason, prompt, success?, timeout_s?}", step=step)
    reason = str(spec.get("reason") or "generic")
    prompt = privacy.redact(str(spec.get("prompt") or ""))
    success = spec.get("success") or None
    timeout_s = spec.get("timeout_s", ckpt.DEFAULT_TIMEOUT_S)
    poll_s = float(spec.get("poll_s", 2.0))
    record = {"reason": reason, "prompt": prompt, "timeout_s": timeout_s}
    records = ctx.extras.setdefault(hitl.RECORD_KEY, [])

    def done(resolution: str, note: str) -> None:
        record["resolution"] = resolution
        records.append(record)
        ctx.extras["_trace_note"] = f"checkpoint {reason}: {note}"

    if device is None or ctx.extras.get("_dry_run"):
        return done("dry_run", "dry run, resolved immediately")
    channel = hitl.channel_for(ctx)
    if channel is None and not success:
        if privacy.sensitive():
            raise ParamError("Secret-bearing checkpoint requires a human channel or success selector")
        logging.getLogger(__name__).warning(
            "[checkpoint] no run channel and no success validator: skipping gate (%s)", reason
        )
        return done("skipped", "skipped, no channel and no success validator")

    def check(cond) -> bool:
        try:
            if isinstance(cond, list) or (isinstance(cond, dict) and ({"kind", "all_of", "any_of", "not"} & set(cond))):
                return bool(evaluate(cond, ctx, device))
            if privacy.sensitive():
                if set(cond) == {"screen_has"}:
                    return evaluate({"kind": "text_visible", "text": cond["screen_has"]}, ctx, device)
                if set(cond) == {"url_contains"}:
                    return evaluate({"kind": "url_contains", "substring": cond["url_contains"]}, ctx, device)
                return False
            return ckpt.screen_condition_met(device, cond)  # v1 shorthand {url_contains | screen_has}
        except Exception as e:  # a failed probe is "not yet", not a crash
            logging.getLogger(__name__).debug("checkpoint success probe raised %s: %s", type(e).__name__, e)
            return False

    outcome = ckpt.run_checkpoint(
        reason=reason,
        prompt=prompt,
        success=success,
        timeout_s=timeout_s,
        read_signal=channel.read_signal if channel else (lambda: None),
        check_success=check,
        set_state=(lambda status, detail: channel.set_state(status, privacy.redact(detail)))
        if channel
        else (lambda *_: None),
        notify=channel.notify if channel else hitl.LocalChannel(echo=True).notify,
        now=time.monotonic,
        sleep=time.sleep,
        poll=poll_s,
    )
    if outcome.resolved:
        return done(outcome.resolution, f"resolved ({outcome.resolution})")
    done(outcome.resolution, outcome.error or outcome.resolution)
    if outcome.resolution == "aborted":
        raise CheckpointAbortedError(outcome.error or "checkpoint aborted", step=step, payload=dict(record))
    raise CheckpointTimeoutError(
        outcome.error or f"checkpoint timed out after {timeout_s}s",
        step=step,
        payload=dict(record),
        hint="Raise timeout_s (0 waits indefinitely), or resume the run: POST /api/skills/runs/{id}/resume.",
    )


@register_step("python_action")
def _python_action(step, ctx, device):
    """Call skill-local Python: `python_action: helpers:scrape_active_handle`.

    The file part resolves relative to the current skill dir (see engine/pyimport.py).

    Function signature: `fn(device, params, context) -> dict | ActionResult`.
    Plain dicts are data; dicts with success/error/data keys are result envelopes.
    Returns success=False → StepFailedError with the returned error message.
    Raises exception → DispatchError wrapping the traceback.
    """
    from gitd.skills.engine.pyimport import identity_from_ctx, resolve_callable

    ref = step.get("python_action", "")
    try:
        fn = resolve_callable(ref, identity_from_ctx(ctx), what="python_action")
    except SkillError as e:
        e.step = e.step or step
        raise

    try:
        res = fn(device, ctx.params, ctx)
    except Exception as e:
        raise DispatchError(
            f"python_action {ref} raised {type(e).__name__}: {e}",
            step=step,
        ) from e

    if isinstance(res, dict) and {"success", "error", "data"}.intersection(res):
        extra_keys = res.keys() - {"success", "error", "data"}
        if extra_keys:
            log.warning(
                "python_action %s result envelope has ignored sibling keys %s; "
                "put payload fields inside data",
                ref, sorted(str(key) for key in extra_keys),
            )

    # Accept ActionResult, dict, bool, or None
    success = getattr(res, "success", None)
    if success is None:
        if isinstance(res, bool):
            success = res
        elif isinstance(res, dict):
            success = res.get("success", True)
        else:
            success = True  # None or other → assume success

    if not success:
        err = getattr(res, "error", None) or (res.get("error") if isinstance(res, dict) else "")
        raise StepFailedError(
            f"python_action {ref} returned success=False: {err}",
            step=step,
        )

    # Merge returned data into ctx.result
    if isinstance(res, dict):
        # Preserve result envelopes while accepting the documented plain-payload
        # shorthand. Wrap business fields named success/error/data in `data`.
        data = res.get("data") if {"success", "error", "data"}.intersection(res) else res
    else:
        data = getattr(res, "data", None)
    if isinstance(data, dict):
        ctx.result.update(data)


# ═══════════════════════════════════════════════════════════════════════════
# Read steps — YAML-only skills: read a node, tap the nth match, compare, loop
# ═══════════════════════════════════════════════════════════════════════════

_LOCATORS = ("id", "desc", "text")
_ATTR_FOR = {"id": "resource-id", "desc": "content-desc", "text": "text"}


def _all_nodes(xml: str, locator: str, value: str) -> list[dict]:
    """Every on-screen node whose `locator` attribute equals `value`, in document order."""
    from gitd.skills.engine.nodes import by, parse

    if locator not in _ATTR_FOR:
        return []
    # Preserve the read-step's public record shape while sharing parsing and
    # matching with Python helpers. Additional attributes are available via nodes.
    return [
        {key: node[key] for key in ("text", "desc", "id", "bounds", "checked")}
        for node in by(parse(xml), locator, value)
    ]


def _locator(step, spec) -> tuple[str, str]:
    for locator in _LOCATORS:
        if spec.get(locator):
            return locator, str(spec[locator])
    raise ParamError(f"{step.get('action', 'step')} needs one of id, desc, text", step=step)


def _nth_node(xml: str, step, spec) -> dict:
    locator, value = _locator(step, spec)
    nodes = _all_nodes(xml, locator, value)
    index = int(spec.get("index", 0))
    if not nodes or index >= len(nodes) or index < -len(nodes):
        raise StepFailedError(
            f"{step.get('action', 'step')}: {locator}={value!r} has {len(nodes)} on-screen match(es), index {index} asked",
            step=step,
            hint="Check the locator with dump_xml, wait for the screen, or scroll the element into view.",
        )
    return nodes[index]


def _parse_number(text: str):
    t = str(text or "").replace(",", "").replace("\u2212", "-").strip()
    try:
        return float(t)
    except ValueError:
        return None


@register_step("read_text")
def _read_text(step, ctx, device):
    """Read one node (or all matches) into the context and the result.

    {action: read_text, id|desc|text: ..., store_as: name, attr?: text|desc|id|checked,
     index?: 0, all?: false, parse?: number, required?: true}
    Later steps use `{context.<store_as>}`; validators read `context.result[<store_as>]`.
    """
    store_as = step.get("store_as")
    if not store_as or not isinstance(store_as, str):
        raise ParamError("read_text requires store_as", step=step)
    attr = str(step.get("attr", "text"))
    if attr not in {"text", "desc", "id", "checked"}:
        raise ParamError("read_text attr must be text, desc, id or checked", step=step)
    xml = _fast_dump(device)
    required = step.get("required", True)
    if step.get("all"):
        locator, value = _locator(step, step)
        values = [n[attr] for n in _all_nodes(xml, locator, value)]
        if step.get("parse") == "number":
            values = [_parse_number(v) for v in values]
        if required and not values:
            raise StepFailedError(f"read_text: no on-screen {locator}={value!r}", step=step)
        stored = values
    else:
        try:
            stored = _nth_node(xml, step, step)[attr]
        except StepFailedError:
            if required:
                raise
            stored = None
        if stored is not None and step.get("parse") == "number":
            stored = _parse_number(stored)
            if stored is None and required:
                raise StepFailedError(f"read_text: {store_as} is not a number", step=step)
    ctx.extras[store_as] = stored
    ctx.result[store_as] = stored


@register_step("tap_nth")
def _tap_nth(step, ctx, device):
    """Tap the nth on-screen match of a locator (negative index counts from the end)."""
    node = _nth_node(_fast_dump(device), step, step)
    left, top, right, bottom = node["bounds"]
    device.tap((left + right) // 2, (top + bottom) // 2, float(step.get("delay_s", 0.3)))


@register_step("compare")
def _compare(step, ctx, device):
    """Fail the step unless left and right agree.

    {action: compare, left: "{context.display}", right: "{expected}", mode?: equals|contains|number|regex, tolerance?: 1e-6}
    `number` compares floats with a relative tolerance; `contains` checks right in left; `regex` matches right against left.
    """
    import re

    mode = str(step.get("mode", "equals"))
    left, right = step.get("left"), step.get("right")
    if mode == "equals":
        ok = str(left).strip() == str(right).strip()
    elif mode == "contains":
        ok = str(right) in str(left)
    elif mode == "regex":
        ok = re.search(str(right), str(left)) is not None
    elif mode == "number":
        a, b = _parse_number(left), _parse_number(right)
        tolerance = float(step.get("tolerance", 1e-6))
        ok = a is not None and b is not None and abs(a - b) <= max(tolerance, abs(b) * tolerance)
    else:
        raise ParamError("compare mode must be equals, contains, number or regex", step=step)
    if not ok:
        raise StepFailedError(step.get("message") or f"compare ({mode}): {left!r} vs {right!r}", step=step)


@register_step("for_each")
def _for_each(step, ctx, device):
    """Run steps once per item of a string (characters) or list.

    {for_each: {over: "{expression}", as: ch, map?: {"+": plus}, skip?: [" "], strict?: false, steps: [...]}}
    Inner steps see `{{context.<as>}}` (double braces: the outer interpolation pass must
    leave them for the per-item pass) and `{{context.<as>_mapped}}` when `map:` is given.
    """
    from gitd.skills.engine.interpolate import interpolate as _interp

    spec = step["for_each"]
    over = spec.get("over")
    name = spec.get("as")
    steps = spec.get("steps") or []
    if not isinstance(name, str) or not name or not steps:
        raise ParamError("for_each needs `as:` and `steps:`", step=step)
    items = list(over) if isinstance(over, (list, tuple)) else list(str(over if over is not None else ""))
    mapping = spec.get("map") or {}
    skip = set(str(x) for x in (spec.get("skip") or []))
    for item in items:
        if str(item) in skip:
            continue
        ctx.extras[name] = item
        if mapping or spec.get("strict"):
            if str(item) not in mapping and spec.get("strict"):
                raise StepFailedError(f"for_each: {item!r} has no entry in map", step=step)
            ctx.extras[name + "_mapped"] = mapping.get(str(item), item)
        for sub in steps:
            dispatch(_interp(sub, ctx), ctx, device)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers — a11y-tree bounds lookup
# ═══════════════════════════════════════════════════════════════════════════


def _find_bounds(xml: str, locator: str, value: str) -> tuple[int, int, int, int] | None:
    """First element bounds by (locator, value) that has a positive on-screen area.

    Returns (x1,y1,x2,y2) or None. Nodes with inverted or off-screen bounds (pager
    neighbours, hidden toolbars, WebView content outside the viewport) are skipped:
    tapping their "centre" lands on empty space or on a different element.
    """
    import html
    import re

    attr = {"id": "resource-id", "desc": "content-desc", "text": "text"}.get(locator)
    if not attr:
        return None
    # Attribute values are XML-escaped in the dump ("&" is "&amp;"), so capture the
    # value and compare it unescaped instead of regex-matching the raw needle.
    bounds_re = r'bounds="\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]"'
    patterns = (
        (rf'<node[^>]*\s{attr}="([^"]*)"[^>]*{bounds_re}', 0),
        (rf'<node[^>]*{bounds_re}[^>]*\s{attr}="([^"]*)"', 4),
    )
    fallback = None
    for pattern, value_group in patterns:
        for m in re.finditer(pattern, xml):
            groups = m.groups()
            if html.unescape(groups[value_group]) != value:
                continue
            b = tuple(int(g) for i, g in enumerate(groups) if i != value_group)
            if b[2] > b[0] and b[3] > b[1] and b[0] >= 0 and b[1] >= 0:
                return b
            fallback = fallback or b
    # Keep the old contract for callers that only test presence (if_visible, waits):
    # an element that exists but is off screen still counts as found when nothing
    # on screen matches. tap_element rejects such bounds itself.
    return fallback


# ═══════════════════════════════════════════════════════════════════════════
# Introspection
# ═══════════════════════════════════════════════════════════════════════════


def registered_steps() -> list[str]:
    """Return sorted list of all registered step names (for docs / debug UI)."""
    return sorted(_HANDLERS.keys())


@register_step("ask")
def _ask(step, ctx, device):
    from .ask import ask

    return ask(step, ctx, device)
