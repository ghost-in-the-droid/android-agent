---
title: "⚙️ Execution Engine"
description: The Ghost Skill Engine — v2 runtime that reads skill.yaml, dispatches step primitives, validates terminal state, and handles popups at 4 layers. ~2500 LOC, pluggable step + validator registries.
---

The **Skill Engine** is Ghost's v2 runtime for executing skills. It lives at `gitd/skills/engine/` in the private mono and ships in the pip package.

If you're using skills, you don't need to know this. If you're authoring or extending skills, this is the internals reference.

---

## Module map

```
gitd/skills/engine/
├── __init__.py         (public API: load_skill, run_action, RunResult, RunContext)
├── loader.py           (parse skill.yaml → typed dataclasses; Schema v2 validation)
├── context.py          (RunContext — params + result + extras across steps)
├── interpolate.py      ({param} + {context.attr} placeholder resolution + filters)
├── errors.py           (10 typed error classes, agent-parseable via .as_dict())
├── dispatch.py         (step handler registry + built-in step primitives)
├── validators.py       (validator kind registry + built-in validator primitives)
├── os_popups.py        (Phase 3 Layer 1 — engine-global OS popup catalog)
├── unknown_popup.py    (Phase 3 Layer 4 — safety net + screenshot capture)
├── runner.py           (orchestrator — resolves + hooks + steps + validator)
├── hitl.py             (checkpoint control channels: SkillRun row or in-process)
├── evidence.py         (concrete device fingerprint + signed run artifacts)
├── migrate.py          (wrap v1 skills as Schema v2 in place)
├── importers.py        (Maestro YAML and Automate flow import)
├── analyze.py          (static analyzer for skill Python)
├── submission.py       (verification PRs, only on verify --push)
└── cli.py              (ghost skill subcommands: scaffold, validate, lint, analyze, test, run,
                         verify, import, migrate, submit, install and friends)
```

Total ~2500 LOC. Pluggable via `@register_step("name")` and `@register_validator("kind")` decorators — third parties can add custom step types + validator kinds without patching the engine.

---

## The step dispatch table

Every YAML step is dispatched by its first structural key OR its `action:` field. The dispatcher priority is:

1. `python_action`, `if_visible`, `retry`, `run_skill`, `subroutine`, `checkpoint`, `pre_hooks` (structural keys)
2. `action:` (name lookup in `_HANDLERS` registry)

Built-in step handlers (all `@register_step`ed):

**Device interaction**: `tap`, `tap_element`, `type_text`, `long_press`, `swipe`, `press_key`, `launch_app`, `launch_intent`, `open_url`, `screenshot`, `dump_xml`, `dismiss_popups`.

**Waits**: `wait_for_text`, `wait_for_element`, `sleep`.

**Control flow**: `if_visible`, `retry`, `run_skill`, `subroutine`.

**Escape hatch**: `python_action` — imports `<module>:<function>`, calls with `(device, params, context)`, accepts a payload dict or `ActionResult`. Merges returned data into `ctx.result`.

Return a plain payload dict, such as `{"count": 5}`, to merge its fields into `context.result`. `ActionResult(success=True, data=payload)` and `{"success": True, "data": payload}` are also supported. Dict keys `success`, `error` and `data` identify a result envelope: if your payload uses those names, put it under `data`. A result with `success=False` fails the step.

Get the current registered set:

```bash
ghost skill list-registered
```

Or programmatically:

```python
from gitd.skills.engine.dispatch import registered_steps
from gitd.skills.engine.validators import registered_kinds
```

---

## The validator dispatch

Same shape as steps — kind-dispatch with pluggable registry:

```yaml
end_state_validator:
  all_of:                          # composition: all_of / any_of / not
    - {kind: text_visible, text: "Sent"}
    - {kind: custom_python, function: validators:message_delivered}
```

Built-in kinds: `text_visible`, `element_present`, `url_contains`, `pixel_at`, `ocr_text_present`, `screen_hash`, `custom_python`.

Composition is recursive — nested all_of inside any_of inside not is fine.

---

## The runner flow

```python
result = run_action(skill, "get_active_account", params={}, device_serial="<serial>")
# result.success: True
# result.data: {"handle": "your_handle"}
# result.duration_ms: 18018
# result.trace: [TraceEntry(step_index=0, step={"subroutine": "nav_to_profile_tab"}, duration_ms=13500, error=None), ...]
```

Under the hood:

1. Resolve params (type-check, fill defaults, enum validation)
2. Populate `RunContext(action_name, params, device_serial, result={}, extras={})`
3. Store skill metadata into `ctx.extras`: `_skill_popup_detectors`, `_os_popup_policy`, `_current_skill_dir` (for `subroutine:` + `run_skill:` resolution)
4. Fire `pre_hooks[]`
5. For each step:
   - Snapshot a11y BEFORE (for Layer 4 diff)
   - Layer 1 OS popup sweep (only if step reads a11y)
   - Layer 2 skill popup sweep (only if step reads a11y)
   - Interpolate `{param}` + `{context.attr}` in every string field
   - Dispatch
   - On failure + new-popup detected: Layer 4 safety net (dismiss cascade + retry once, else `UnknownPopupError` w/ screenshot)
6. Interpolate + evaluate `end_state_validator`
7. Return structured `RunResult` — never raises

Failures are wrapped as `SkillError` subclasses with `.as_dict()` for agent-parseable payload. Unexpected exceptions become `EngineBug` — file an issue.

Two keyword options change how a run behaves:

- `run_id=<SkillRun id>` binds the run to a dashboard or MCP run row, so `checkpoint:` steps publish and resume through that row (below).
- `dry_run=True` runs without a device. Params are resolved and steps interpolated; checkpoints resolve at once (`resolution: dry_run`), every other step is recorded in the trace as skipped, and the end-state validator is not evaluated.

---

## Checkpoint steps

A `checkpoint:` step (`reason`, `prompt`, optional `success:` validator, `timeout_s`, `poll_s`) is where a human, or an outside signal, has to act: a captcha, an SMS or email code, a login.

1. The run's status becomes `awaiting_human`, and `reason` plus `prompt` go out on the run's control channel.
2. Every `poll_s` seconds (default 2) the step checks for a `resume` or `abort` signal, then evaluates its `success:` validator on the live device.
3. `resume` or a passing validator sets the run back to `running` and the next step starts. `abort` raises `CheckpointAbortedError`. After `timeout_s` (default 600; `0` waits forever) the run is marked `timed_out` and the step raises `CheckpointTimeoutError`.
4. With no channel and no `success:` validator nothing could clear the gate, so the step is skipped with a warning.

The channel is chosen per run: a `SkillRun` row when `run_id` is given (resume or abort with `POST /api/skills/runs/{id}/resume`), otherwise an in-process channel for embedding and tests. Each checkpoint is appended to `result.data["checkpoints"]` with its resolution: `human`, `auto`, `aborted`, `timed_out`, `skipped` or `dry_run`.

---

## Recorded runs

`ghost skill run <skill> <action> --device <serial> --record` writes a run artifact next to the skill, in `runs/`. It holds a concrete device fingerprint (on Android read over ADB: OS version, manufacturer and model, and the installed version of the target app), the per-step results, and an Ed25519 SSH signature made with a local key that Ghost creates on first use. iOS runs need `--fingerprint <file.json>` with those values filled in by hand; a supplied file may also add `screen_wxh`, `density`, `locale` and `theme`.

`ghost skill verify <author>/<slug> --device <serial>` does the same for someone else's skill and writes to `verifications/`. These artifacts are what the hub's quality score counts; see [Skill Hub](/features/skill-hub/#evidence-record-verify-submit).

---

## Popup handling — 4 layers

### Layer 1: engine-global OS popup catalog (always-on)

Built-in patterns for the 11 most common OS-level modals:

**Permission dialogs** (default: DENY): location, contacts, storage, camera, microphone, notifications.

**Other OS popups**: battery_optimization (cancel), google_play_update (not now), keyboard_default (cancel), screen_recording (allow — Ghost needs it), system_update (later).

Per-skill override via `os_popup_policy:` in skill.yaml:

```yaml
os_popup_policy:
  allow_permissions: [storage, location]   # tap Allow for these
  deny_permissions: [contacts]             # explicit deny
  ignore: [google_play_update]             # don't touch
```

### Layer 2: skill-scoped popup_detectors

Declared per skill, checked before every a11y-reading step:

```yaml
popup_detectors:
  - {detect: "Continue editing", button: "Save draft", label: "Draft resume overlay"}
  - {detect: "Learn more", method: back, label: "Invisible promo overlay"}
```

Optional filters: `only_in_actions: [...]`, `not_in_actions: [...]`.

### Layer 3: action-level `on_popup:` override

For popups that are PART of a flow (Ad Authorization, cookie consents that must be Accepted). Author declares custom response steps per popup label.

### Layer 4: unknown-popup safety net (implicit)

Engine tracks pre-step and post-step a11y snapshots. When a step fails:

- Diff-heuristic detects new modal (text-node count drop >30%, new "Allow/OK/Cancel/Continue/Not now" buttons appeared)
- Screenshot to `/tmp/ghost-skills-artifacts/<serial>-unknown-popup-<ts>.png`
- Try dismiss cascade: BACK
- Retry the failed step ONCE
- If retry succeeds → transparent to caller
- If retry fails → `UnknownPopupError` with screenshot path in payload + hint to add a `popup_detectors:` entry

Screenshots become empirical grow-your-catalog fodder. `ghost skill mine <skill> --update-popups` (planned) post-processes them into detector proposals.

---

## Fingerprint match + fallback

> **Status (v1.6.0):** fingerprint distance matching, warn-and-execute, refuse at 3+, `--strict-fingerprint` and `ghost skill doctor <ref> --device` are implemented (`gitd/skills/engine/fingerprint.py`); MCP `run_skill` returns the report under `fingerprint`. Adapt (LLM re-mines from SOFT.md) and Mine are planned for v1.7+, not implemented.

At `run_action` time, the engine evaluates the skill's `fingerprint:` block against the target device:

- Fields: `os`, `os_version`, `hardware`, `app_package`, `app_version`
- Wildcards: `hardware: "*"` always matches
- SemVer ranges: `app_version: ">=44.0.0"` per-field

**Match distance** = count of non-matching fields (0 = perfect, 5 = totally different app).

| Distance | Behavior (shipped) |
|---|---|
| 0 | Hit: execute as-is |
| 1-2 | Warn + execute; the mismatched fields are printed (CLI) or returned under `fingerprint` (MCP) |
| 3+ | Refuse with the mismatched fields; `--force-fingerprint` runs anyway. Adapt is planned (v1.7+) |
| No skill exists | `ghost skill find "<intent>"` returns nothing; author one (`ghost skill scaffold`) |

`--strict-fingerprint` requires distance 0; `--no-fingerprint-check` skips the probe; `ghost skill doctor <ref> --device <serial>` shows the fit before you run.

---

## Fast a11y dump (video-app gotcha)

TikTok, Instagram, YouTube — all video-autoplay apps — never let `uiautomator dump` reach idle. Even `--compressed` variant fails with "could not get idle state" on these screens. Ghost's `_fast_dump()` tries direct uiautomator first (~500ms when idle), falls back to Droidrun Portal (~14s but works during video playback).

Impact: popup pre-sweeps only fire before a11y-reading steps (blind ops like `sleep`, `tap`, `press_key`, `launch_app` skip the sweep), giving 3× speedup on TT-class skills.

---

## Extending the engine

**Custom step type:**

```python
from gitd.skills.engine.dispatch import register_step

@register_step("my_custom_op")
def _my_custom_op(step: dict, ctx: RunContext, device) -> None:
    device.tap(step["x"], step["y"])
    # Raise StepFailedError / TimeoutError_ on failure; return None on success
```

**Custom validator kind:**

```python
from gitd.skills.engine.validators import register_validator

@register_validator("my_kind")
def _my_kind(spec: dict, ctx: RunContext, device) -> bool:
    return spec["value"] in device.dump_xml()
```

Import the module during skill load (add to `helpers.py` or skill `__init__.py`).

---

## Errors

All engine errors subclass `SkillError` with a structured payload:

```python
{
  "kind": "TimeoutError_",
  "message": "wait_for_text('Post') exceeded 20.0s",
  "skill": "tiktok",
  "action": "upload_video",
  "step_index": 5,
  "step": {"action": "wait_for_text", "text": "Post", "timeout_s": 20},
  "payload": {},
  "hint": "Element may not have rendered. Try screenshot + inspect, or increase timeout_s.",
}
```

Every error carries a `hint` field with actionable next steps. Agents parse `.as_dict()` for structured feedback.

---

## Related

- [Skill System](/features/skill-system/) — architectural walkthrough
- [Skill Hub](/features/skill-hub/) — registry, trust tiers, community
- [Skill Creator](/features/skill-creator/) — auto-BFS Skill Miner
- [Creating Skills](/skills/creating-skills/) — author flow
- [API Reference](/api/skill-classes/) — full YAML spec
