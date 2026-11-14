---
title: "🧠 Skill System"
description: The action-first architecture for phone automation — Skills bundle Actions built from atomic Steps with typed Params, Validators, and community-contributable Subroutines.
---

Ghost's Skill System is what turns a probabilistic LLM-driven phone-driving loop into a **deterministic, replayable, community-contributable library of $0 automations**.

If you're here to understand the *architecture*, you're in the right place. If you're here to *use* skills, start with [Using Skills](/skills/using-skills/). If you're here to *author* skills, start with [Creating Skills](/skills/creating-skills/).

---

## The hierarchy

```
Skill (a package)
├── fingerprint       (os × hw × app-version this is verified against)
├── status            (active | blocked | deprecated, default active)
├── license, generated_with, side_effects, destructive, tos_risk, locale
├── data_access       (permissions the skill uses — informational)
├── popup_detectors   (skill-scoped popups auto-dismissed mid-flow)
├── os_popup_policy   (permission grant/deny overrides)
├── subroutines[]     (internal reusable step-lists — de-dup helpers)
└── actions[]         (agent-invocable, first-class)
    ├── ref_prompt        (natural-language phrase LLM matches against)
    ├── params[]          (typed inputs, {name} interpolation)
    ├── pre_hooks[]       (python_action prep before device flow)
    ├── steps[]           (the flow — atomic primitives + control flow + composition)
    ├── end_state_validator (composable predicate on terminal screen)
    └── test_case         (canonical prompt variants + expected success)
```

Everything lives in `skill.yaml` next to a flat `helpers.py` (Python for `python_action:` escape hatches).

New skills must declare `license:` (an SPDX id such as `MIT`) and `generated_with:` (how the skill was written, for example `hand` or the tool that produced it). `side_effects:` (`sends_message`, `posts_content`, `makes_payment`, `modifies_account`, `deletes_data`, `none`), `destructive:`, `tos_risk:` (`low`, `medium`, `high`) and `locale:` describe what the skill does to the world; a `destructive: true` skill needs a `confirm_before:` gate or a `dry_run` param. You can check a file in the browser at [Validate a skill](/skills/validate/).

---

## Why action-first

v1 split skill code into `actions/` (atomic Python classes) + `workflows/` (compositions calling actions) — two tiers, two Python conventions, one confusing distinction because both were called "actions" in the wild.

v2 collapses to **one first-class thing** — the Action — with clear ancillary primitives for the different needs it was solving:

| v1 concept | v2 replacement | Why |
|---|---|---|
| `actions/` (atomic Python classes) | Not needed — atomic ops are yaml primitives (`tap`, `wait_for_element`, etc.) or `python_action:` escape hatches | LLMs can emit YAML from a trace; Python classes are opaque to them |
| `workflows/` (multi-step compositions) | `actions:` with inline `steps:` | The composition IS the action — one thing, one name |
| Shared prelude Python between workflows | `subroutines:` (named reusable step-lists in the same yaml) | De-dup without inventing a "helper action" that isn't agent-invocable |

Now: **every named thing an agent can invoke is an Action**. Every Action has `ref_prompt` + `end_state_validator` + `test_case`. Every Action can be tested, benched, and validated in isolation.

---

## The action lifecycle

When you call `ghost skill run ghost/tiktok get_active_account --device asus`:

1. **Loader** parses `skillhub/ghost/tiktok/skill.yaml` → typed `SkillDef` w/ validated Schema v2 conformance
2. **Runner** builds a `RunContext` (params, result, device_serial, popup detectors, os_popup_policy, skill_dir)
3. **Runner** resolves params against the action's `params[]` — type-checks, fills defaults, validates enums
4. **Pre-hooks** — any `pre_hooks: [{python_action: ...}]` fire before device steps (media prep, TTS injection, etc.)
5. For each step in `steps[]`:
   - **Interpolate** `{param}` and `{context.attr}` placeholders in every string field
   - **Layer 1** OS popup sweep (permission dialogs, battery-opt, etc.) — only before a11y-reading steps
   - **Layer 2** skill popup sweep (from `popup_detectors:`) — same selectivity
   - **Dispatch** to step handler (16 built-in step types, pluggable registry)
   - **Layer 4 safety net**: if step failed AND a11y-diff shows a new modal appeared → screenshot + BACK cascade + retry ONCE → else `UnknownPopupError` with screenshot
6. **Validator** on end_state_validator — kind-dispatch (7 built-in, composable via all_of/any_of/not)
7. **Result** — structured `RunResult(success, data, error, duration_ms, trace[])` — never raises

Full engine internals: [Execution Engine](/features/skill-execution-engine/).

---

## Step primitives

All available via yaml step syntax (see the ["step" grammar](/api/skill-classes/)):

**Atomic device interactions**:
`tap`, `tap_element` (id/desc/text locator chain), `type_text`, `long_press`, `swipe`, `press_key`, `launch_app`, `launch_intent` (full Android Intent w/ mime_type + URI extras), `open_url`, `screenshot`, `dump_xml`, `dismiss_popups`.

**Waits**:
`wait_for_text`, `wait_for_element`, `sleep`.

**Control flow**:
`if_visible: {selector, then: [...], else: [...]}`, `retry: {max, backoff_s, steps: [...], on_failure}`, `run_skill: {name, action, params}` (cross-skill composition), `subroutine: <name>` (in-skill composition), `checkpoint: {reason, prompt, success, timeout_s}` (HITL gate for soft skills).

A `checkpoint:` step pauses at a gate the bot must not clear itself, such as a captcha or an emailed code. The run is marked `awaiting_human` and shows the `prompt`; it continues when a person resumes it (`POST /api/skills/runs/{id}/resume` for dashboard and MCP runs) or when the step's `success:` validator passes, and ends `timed_out` after `timeout_s` (default 600). A dry run, `run_action(..., dry_run=True)`, needs no device: it resolves params, passes checkpoints straight through and lists every other step as skipped, which makes it a cheap smoke test for a skill's structure.

**Escape hatch**:
`python_action: <module>:<function>` — arbitrary Python callable receiving `(device, params, context)`, returns `ActionResult`. Required for real-world complexity (custom validators, media prep, OCR helpers). Raises trust tier — Community submissions with `python_action:` get extra reviewer attention.

---

## Validator primitives

Compose via `all_of` / `any_of` / `not`. Leaf kinds:

- `text_visible: {text}` — a11y tree substring match
- `element_present: {id | desc | xpath}` — element in tree
- `url_contains: {substring}` — WebView URL
- `pixel_at: {x, y, rgb, tolerance}` — screencap pixel color check
- `ocr_text_present: {text, region?}` — RapidOCR on screencap (optionally in a region)
- `screen_hash: {ref_hash, similarity_min}` — perceptual hash match against reference
- `custom_python: {function}` — arbitrary Python predicate `(device, context) -> bool`

Example:

```yaml
end_state_validator:
  all_of:
    - {kind: text_visible, text: "Sent"}
    - any_of:
        - {kind: element_present, id: sent_check_icon}
        - {kind: pixel_at, x: 990, y: 1200, rgb: [34, 187, 51]}
    - not:
        {kind: text_visible, text: "Failed to send"}
```

---

## Popup handling (4 layers)

TT-style flake was the #1 pain of v1 skills. v2 handles it at four layers so authors barely think about it for the common case:

- **Layer 1** — engine-global OS popups: permission dialogs, battery-opt, Google Play nag, screen-recording confirm. Always-on, deny-by-default (with per-skill `os_popup_policy.allow_permissions[]` opt-in).
- **Layer 2** — skill-scoped `popup_detectors:` in skill.yaml. Auto-dismissed before every a11y-reading step.
- **Layer 3** — action-level `on_popup:` override for popups that are PART of the flow (Ad Authorization, cookie consents that must be accepted specifically).
- **Layer 4** — safety net: unknown modal detected after step failure → dismiss cascade → retry once → screenshot + `UnknownPopupError` if still failing. Screenshot becomes the seed for extending the skill's detector catalog.

---

## Trust, quality and status

Every skill on the [Skill Hub](/features/skill-hub/) carries two separate badges, and the author sets neither of them:

- **Trust** comes from where the skill lives: **Official** (`skillhub/ghost/*`), **Verified** (a community folder merged through a reviewed PR), **Unverified** (installed from a URL outside the hub; the installer asks first), **Quarantined** (blocked).
- **Quality** comes from evidence: **Draft, Runs, Proven, Hardened, Reference**, earned with signed run artifacts, independent runs on other devices, validators and docs. See [Scoring](/skills/scoring/).

The author does set `status:`. A `blocked` skill cannot finish on its own right now (for example a mandatory phone check); the hub hides it by default and the installer warns, but it still installs.

---

## Upgrading v1 skills

Older skills were Python packages (`actions/` and `workflows/` classes) or FLOW.md notes. `ghost skill migrate <path>` wraps one as a Schema v2 skill in place without deleting any v1 file: each v1 action or workflow becomes a v2 action whose single step is a generated `python_action` adapter, and a FLOW.md-only soft skill becomes an `open_url` plus a `checkpoint:`. It also generates `SOFT.md`. Re-running it refreshes the generated block, and `--dry-run` reports what would change.

---

## Where this fits

Skills sit between agents and the [MCP Server](/features/mcp-server/):

```
Agent (Claude / Codex / GPT / etc)
    │  MCP tool: run_skill(name, action, params)
    ▼
Ghost Skill Engine
    │  loads skill.yaml → dispatches steps
    ▼
Device (Android via ADB / iOS via WebDriverAgent)
```

Agents can use skills, and agents can *author* skills — the "LLM emission" mode of the schema is intentional: an LLM that just drove the phone can dump its own tool-call trace and get a near-1:1 YAML back. See [Creating Skills](/skills/creating-skills/) for the trace→yaml recipe.

---

## Reference

- [`docs/skill-taxonomy-soft-vs-hard.md`](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/skill-taxonomy-soft-vs-hard.md) — hard vs soft, 3-tier acquisition, empirical basis
- [`docs/skill-schema-v2.md`](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/skill-schema-v2.md) — full YAML spec, every primitive, composition rules
- [Execution Engine](/features/skill-execution-engine/) — runtime internals
- [Skill Hub](/features/skill-hub/) — registry + community + trust
- [Skill Creator](/features/skill-creator/) — the auto-BFS Skill Miner
- [Publishing Skills](/skills/publishing/) — PR submit flow
