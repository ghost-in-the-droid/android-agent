# Skill Schema v2

Full `skill.yaml` specification for the v1.6.0 Skills release. Companion to `docs/skill-taxonomy-soft-vs-hard.md` (concepts) and `docs/contributing-skills.md` (submission flow).

**Migration**: v1 (bundled 6 skills, no action-level fields, no versioning matrix, no validators) → v2 (action-first bundles, fingerprint matrix, per-action validators + ref_prompt + test_case, trust-tier metadata). All v1 skills auto-migrate via `ghost skill migrate <path>`.

---

### Toolkit shape

Author an app toolkit with **one entry action**, **3–6 focused primitives**, and
**one read-state action** that returns visible structured data. Add actions beyond
that range only when the app needs distinct operations; this is an authoring rule,
not a schema-enforced action limit. Entry opens or resets the demo app; primitives
perform one operation; read-state observes without opening unrelated apps or
changing user data. Reuse the toolkit across prompts instead of embedding one
benchmark task in a single long action.

Include a **Toolkit** table in README with each action's role, parameters, returned
data and side effects. Document honest limits and the tested app/device scope.
Record every action three times after the final definition-file edit; editing
README, SOFT.md, helpers.py or skill.yaml changes the content digest. Prior runs
remain historical evidence and do not verify the new files.

For Android Python helpers, share the engine APIs instead of copying parsers or
launching a separate ADB process:

```python
from gitd.skills.engine.nodes import parse, by, centre

nodes = parse(device.dump_xml())
rows = by(nodes, "id", "com.example:id/row")
# centre(rows[0]) returns coordinates; it does not tap.
png = device.screencap_png()  # PNG bytes, transport errors and package policy checked
```

The node helpers preserve document order and raw XML attribute entities, reject
invalid/off-screen bounds, and use exact selectors. Decode display text explicitly
when needed. The screenshot API is Android-specific. Adopting either API in an
existing recorded skill requires fresh content-bound runs after its final edits.


## 1. Top-level fields

```yaml
# Identity
name: whatsapp-messaging           # kebab-case slug
version: 1.0.0                     # SemVer
author: alice                      # github handle (community) or "ghost" (official)
description: "Send + receive DMs on WhatsApp"

# Lifecycle (optional; `ghost skill fork` and `ghost skill deprecate` write these)
status: active | blocked | deprecated | draft
forked_from: bob/calc@1.2.0        # <author>/<slug>@<version> this skill was copied from; evidence never carries over
superseded_by: alice/calc2         # ref users should install instead
deprecated_reason: "app removed from F-Droid"   # required with status: deprecated (lint warns)

# Classification
skill_class: hard | soft           # required (see taxonomy doc)
trust: official | verified | unverified   # registry field (`trust` in registry.json), never set by the author
data_access:                       # required — informational, drives Hub badge
  - contacts | sms | camera | mic | location | notifications | clipboard | files | ...

# Fingerprint (versioning matrix; used by tier-1 Hit vs tier-2 Adapt logic)
fingerprint:
  os: android | ios
  os_version: ">=14"               # SemVer range
  hardware: "samsung-s24" | "*"    # exact model or wildcard
  app_package: com.whatsapp        # Android package name or iOS bundle id (the PRIMARY app: distance, evidence and demos key on it)
  app_version: ">=2.24.15"         # SemVer range
  apps: [com.whatsapp.w4b]         # optional, multi-app skills: the other packages the steps drive (launch_app names them per step)

# Entry (for soft skills that start from a URL rather than a package)
entry_url: "https://account.proton.me/mail/signup"   # optional; soft-skill web flows

# Registry references (populated during PR submit)
repo_url: "https://github.com/ghost-in-the-droid/android-agent"
skill_path: "skillhub/alice/whatsapp-messaging"     # relative to repo root

# Global popup detectors (checked before every step; auto-dismissed)
popup_detectors:
  - {detect: "Allow WhatsApp to access", button: "Allow", label: "Permission dialog"}
  - {detect: "Rate the app", button: "Not now", label: "Rate prompt"}
```

---

## 1b. Popup handling (first-class)

Popups are the #1 cause of hard-skill flake. Ghost handles them at four layers so authors don't have to think about them for the common case.

### Layer 1 — Engine-level global OS popups (always-on)

Ghost's engine ships a built-in catalog of OS-level popups auto-dismissed on every step. Authors get this for free with no skill.yaml config:

- Runtime permission dialogs (Location, Camera, Contacts, Notifications, Storage) — auto-**denied** by default (safest); override with `os_popup_policy: allow_permissions: [contacts, ...]` in skill.yaml for skills that need them
- "Battery optimization" / "Optimise battery usage" prompts — dismissed
- "Update system?" / "Google Play services" nags — postponed
- Vendor keyboards asking to be set default — dismissed
- Screen-recording confirmation dialogs — allowed (Ghost needs them)

### Layer 2 — Skill-level `popup_detectors:` (app-specific)

Each skill declares a catalog of popups it knows can appear at any point in ANY of its actions. Engine runs `dismiss_popups()` before every step transparently.

```yaml
popup_detectors:
  - {detect: "Continue editing", button: "Save draft", label: "Draft resume overlay"}
  - {detect: "connect with people", button: "Don't allow", label: "Contacts access popup"}
  - {detect: "Turn on notifications", button: "Not now", label: "Notifications popup"}
  # method: back — press BACK instead of tapping a button, for overlays without visible dismiss buttons
  - {detect: "Learn more", method: back, label: "Invisible promo overlay"}
```

Fields per detector:
- `detect: <text-or-content-desc>` — substring match against a11y tree (case-insensitive)
- `button: <text>` — target button text within the popup (mutually exclusive with `method:`)
- `method: back | home | tap_outside` — for popups without a dismiss button (default: `button` if button set, else `back`)
- `label: <str>` — human-readable name (shown in logs)
- `only_in_actions: [<action_name>...]` — optional; restrict this detector to specific actions
- `not_in_actions: [<action_name>...]` — optional; exclude specific actions (e.g., don't dismiss "Save draft" during `save_draft` action)

Engine runs detectors in declaration order, first match dismisses. When a skill declares `popup_detectors` or `os_popup_policy`, the device's legacy generic fallback (tap any small Cancel/Skip/Later/Dismiss button, BACK on invisible overlays) is off: v2 runs rely on Layer 1, Layer 2 and the Layer 4 BACK cascade only. `dismiss_popups()` is called:
- Automatically before every step transition
- Explicitly via `{action: dismiss_popups}` step if author wants an extra sweep

### Layer 3 — Action-level `on_popup:` override (custom response)

For popups that are PART of the intended flow (e.g., Ad Authorization confirmation), an action can override the default dismiss behavior:

```yaml
actions:
  - name: upload_video
    on_popup:
      "Ad authorization":            # popup label from a detector
        method: accept               # accept | dismiss | prompt_user | custom_python
        steps:                       # optional: extra steps if method=custom
          - {action: tap_element, text: "Authorize"}
          - {action: tap_element, text: "Save"}
```

### Layer 4 — Fallback when unknown popup blocks a step (engine safety net)

If a step fails with the same locator repeatedly AND a a11y-tree diff shows a new modal/overlay appeared, engine:
1. Screenshots + labels as `unknown_popup`
2. Emits a WARN log with the a11y text snippet
3. Tries generic dismiss cascade: BACK → tap_outside → HOME (in order, only tap_outside cancels action)
4. If dismiss cascade succeeds, retries the failed step ONCE
5. If still failing, aborts with `UnknownPopupError` — user's `runs/<id>/report.html` shows the screenshot for adding to the skill's `popup_detectors:`

The unknown-popup screenshot is the primary way authors GROW their popup catalog empirically. `ghost skill mine <skill> --update-popups` (planned, not in v1.6.0) will post-process recent runs' unknown-popup screenshots into detector proposals; today you add detector entries by hand.

---

## 2. Actions (the first-class thing)

Every skill exposes one or more actions. An **action** is what an agent invokes.

```yaml
actions:
  - name: send_msg                 # kebab-case within the skill's namespace
    description: "Send a text message to a contact"
    ref_prompt: "Text John Smith saying I'll be late"   # canonical natural-language
    params:                        # named parameters, referenced as {name} in steps
      - {name: contact_name, type: str, required: true}
      - {name: message, type: str, required: true}

    # Optional pre-flow Python prep (runs BEFORE any device step)
    pre_hooks:
      - {python_action: "helpers:normalize_contact"}

    # The atomic + escape-hatch sequence
    steps:
      - {action: launch_app, package: com.whatsapp}
      - {action: tap_element, id: search_button}
      - {action: type_text, text: "{contact_name}"}
      - {action: wait_for_text, text: "{contact_name}", timeout_s: 5}
      - {action: tap_element, text: "{contact_name}"}
      - {action: type_text, text: "{message}"}
      - {action: tap_element, desc: Send button}
      # Optional HITL/external-code gate (makes the skill soft); see "Checkpoint step" in section 3
      - checkpoint:
          reason: captcha          # captcha | sms | email | login | llm_decision | generic
          prompt: "hCaptcha drag-puzzle: a human drags the piece"
          success: {kind: url_contains, substring: "/inbox"}
          timeout_s: 600           # default 600; 0 = wait indefinitely

    # Terminal state — required. All conditions AND'd unless any_of/not used.
    end_state_validator:
      all_of:
        - {kind: text_visible, text: "{message}"}
        - {kind: element_present, desc: message_sent_check}

    # Per-action bench spec (see docs/contributing-skills.md §Bench)
    test_case:
      ref_prompt_variants:
        - "text mom I'll be home late"
        - "message Jane about the meeting"
        - "whatsapp Alice: dinner tonight?"
      expected_success: true       # after action runs, end_state_validator should PASS

  - name: reply_last_msg
    # ...another action, same shape
```

---

## 3. Step primitives (full list)

### Atomic device interactions

| `action:` | Fields | Notes |
|---|---|---|
| `tap` | `x, y, delay_s?` | Coordinate tap |
| `tap_element` | `id? \| desc? \| text? \| xpath?` | Locator chain: id → desc → text → xpath |
| `type_text` | `text, clear_first?` | Types into currently focused field; supports `{param}` interpolation |
| `long_press` | `x, y \| id\|desc\|text (+ index?), duration_ms` | A locator long-presses the matched node's centre |
| `swipe` | `x1, y1, x2, y2, duration_ms?` | |
| `press_key` | `key: HOME\|BACK\|ENTER\|VOLUME_UP\|...` | Standard Android keyevents |
| `launch_app` | `package, activity?` | Uses `am start` for Android, bundle-id launch for iOS |
| `launch_intent` | `intent_action, package?, activity?, mime_type?, extras?, category?` | `am start -a <action>` with optional `-p pkg`, `-t mime`, `--es key val` extras. Required for share-intent flows (media upload to social apps), OS deep-links |
| `open_url` | `url, browser?` | Default Chrome (Android) / Safari (iOS) |
| `screenshot` | `save_as?` | Captures screencap; stored in run artifacts |
| `dump_xml` | `save_as?` | Dumps a11y tree |
| `dismiss_popups` | — | Runs the skill's `popup_detectors:` once |
| `read_text` | `id\|desc\|text, store_as, attr?: text\|desc\|id\|checked, index?, all?, parse?: number, required?` | Reads a node into `{context.<store_as>}` and `result[<store_as>]`; `all` collects every on-screen match |
| `tap_nth` | `id\|desc\|text, index, delay_s?` | Taps the nth on-screen match (negative index from the end) |
| `compare` | `left, right, mode?: equals\|contains\|number\|regex, tolerance?, message?` | Fails the step unless the values agree |

### Waits

| `action:` | Fields |
|---|---|
| `wait_for_text` | `text, timeout_s?` (default 10) |
| `wait_for_element` | `id? \| desc? \| xpath?, timeout_s?` |
| `sleep` | `duration_s` (last-resort; prefer explicit waits) |

### Control flow

| `action:` | Fields |
|---|---|
| `if_visible` | `selector: {id\|desc\|text}, then: [steps], else?: [steps]` |
| `retry` | `steps: [...], max: int, backoff_s: float, on_failure?: <action>` |
| `run_skill` | `name: <user>/<slug>, action: <name>, params: {...}` |
| `checkpoint` | `reason, prompt, success?: <validator>, timeout_s?, poll_s?` (structural key: `- checkpoint: {...}`) |
| `for_each` | `over: <string or list>, as: <name>, map?: {item: value}, skip?: [items], strict?, steps: [...]` (structural key: `- for_each: {...}`). Inner steps write `{{context.<as>}}` / `{{context.<as>_mapped}}`: the outer interpolation pass turns the double braces into single ones and the loop resolves them per item |

#### Checkpoint step

A `checkpoint:` step pauses the run at a gate the bot must not clear itself (captcha, SMS or email code, login/2FA).

1. The run's state becomes `awaiting_human`, and `reason` + `prompt` are published through the run's checkpoint control channel, so the UI and MCP can surface them.
2. Every `poll_s` seconds (default 2) the step checks, in order: a human `resume` or `abort` on the channel, then the `success:` validator (any validator from section 4, evaluated against the live device). The first one to fire wins.
3. `resume` or a passing `success:` sets the state back to `running`, and the next step runs.
4. `abort` raises `CheckpointAbortedError`. When `timeout_s` passes first (default 600), the state becomes `timed_out` and the step raises `CheckpointTimeoutError`. Its `as_dict()` payload is `{reason, prompt, timeout_s, resolution: "timed_out"}`. `timeout_s: 0` waits indefinitely.
5. If there is no control channel AND no `success:` validator, nothing could ever clear the gate, so the step logs a warning and is skipped (`resolution: skipped`), as in the v1.5 engine.
6. Dry mode (`run_action(..., dry_run=True)`, no device) runs only checkpoint steps. They resolve immediately (`resolution: dry_run`); every other step is noted in the trace as skipped, and the end_state_validator is not evaluated.

Each checkpoint appends `{reason, prompt, timeout_s, resolution}` to the run result's `data.checkpoints`. `resolution` is one of `human`, `auto`, `aborted`, `timed_out`, `skipped`, `dry_run`. Its trace entry carries a `note`. The poll loop is `gitd/skills/checkpoint.py:run_checkpoint` (shared with the v1.5 engine), and the channel lives in `gitd/skills/engine/hitl.py`. `run_action(run_id=...)` uses the SkillRun-backed channel: resume or abort with `POST /api/skills/runs/{id}/resume`. Reasons outside the v1.5 set (`llm_decision`) are reported as `generic`. The action-level `checkpoints:` list is still accepted and validated for compatibility, but the engine does not execute it: put gates in `steps:`.

CLI `--param` values are converted by the parameter declaration in both `ghost skill run` and `ghost skill test`: `--param value=005` stays `"005"` for `type: str` and becomes `5` for `type: int`. Boolean-looking text and JSON-looking text also stay literal strings when declared `str`; `bool` and `list[str]` declarations parse them accordingly. Typed API values and YAML defaults declared `str` are normalized to strings.

### Escape hatch

| `action:` | Fields | Notes |
|---|---|---|
| `python_action` | `<file>:<function>` | Resolved by file path relative to the skill dir (`helpers:fn` -> `helpers.py`). Function signature: `(device, params: dict, context: RunContext)`, returning a payload dict or `ActionResult`. Receives full device handle. **Raises trust tier below Official → requires review.** |

Return a plain payload dict, such as `{"count": 5}`, to merge its fields into `context.result`. `ActionResult(success=True, data=payload)` and `{"success": True, "data": payload}` are also supported. Dict keys `success`, `error` and `data` identify a result envelope: if your payload uses those names, put it under `data`. Envelope sibling keys outside `success`, `error` and `data` are ignored with a warning; put payload fields inside `data`. A result with `success=False` fails the step.

`python_action` is opaque to the popup sweep by design: Layers 1 and 2 run before steps that read the accessibility tree, never inside the function. A popup that can appear while helper code runs must be handled by the helper itself (call `device.dismiss_popups(popups=..., generic=False)` or check for it), or the work should be split so the risky screen change happens in a YAML step that the sweep covers.

---

## 4. Validator primitives (full list)

Every validator is a dict with `kind:` + kind-specific fields. Composable with `all_of:` / `any_of:` / `not:` blocks (nestable).

| `kind:` | Fields | Description |
|---|---|---|
| `text_visible` | `text, exact?` | Text appears in current a11y tree |
| `element_present` | `id? \| desc? \| xpath?` | Element in a11y tree |
| `url_contains` | `substring` | Current WebView/browser URL |
| `pixel_at` | `x, y, rgb: [r,g,b], tolerance?` (default 8) | Pixel color within tolerance |
| `ocr_text_present` | `text, region?: {x, y, w, h}` | RapidOCR on screencap finds text (optionally in a region) |
| `screen_hash` | `ref_hash, similarity_min?` (default 0.85) | Perceptual hash match |
| `custom_python` | `<module>:<function>` | Function signature: `(device, context) -> bool` |

### Composition

```yaml
end_state_validator:
  all_of:                          # AND
    - {kind: text_visible, text: "Sent"}
    - any_of:                      # nested OR
        - {kind: element_present, id: sent_check}
        - {kind: pixel_at, x: 990, y: 1200, rgb: [34, 187, 51]}
    - not:                         # NOT
        {kind: text_visible, text: "Failed to send"}
```

**Default composition** (bare list at `end_state_validator:` level): AND.

---

## 5. Skill directory layout

Every skill is a directory with this shape:

```
skillhub/<author>/<slug>/
├── skill.yaml                    # this document
├── SOFT.md                       # human/LLM-readable flow narrative (see taxonomy §6)
├── README.md                     # required: one-page overview, failure modes
├── SKILL.md                      # generated wrapper for skills.sh-style indexers (registry build)
├── LICENSE                       # required for community skills
├── helpers.py                    # optional: python_action targets (`helpers:fn`)
├── validators.py                 # optional: custom_python validators (`validators:fn`)
├── icon.webp                     # optional: 96 px app icon
├── demos/<action>.webm + .spec.yaml   # optional: one clip per action (`ghost skill demo`)
├── runs/<fp-hash>-<ts>.json      # signed self-runs (`run --record`)
├── verifications/<login>-<fp>-<ts>.json   # signed independent runs (`verify`)
├── bench.yaml                    # optional, hand-written: per-action bench entries (§6)
└── data/                         # optional: reference screenshots for screen_hash, etc.
```
`ghost skill scaffold` writes skill.yaml, SOFT.md, README.md and helpers.py; the rest accrues.

**Placement:**
- **Tier 0 (Official)**: `skillhub/ghost/<slug>/`
- **Tier 1 (Community Verified)**: `skillhub/<user>/<slug>/`
- **Tier 2 (Community Unverified)**: any GitHub URL pointing at a valid skill dir

---

## 6. Bench specification (`bench.yaml`)

Optional. When present, contains trace-submitted bench numbers per action.

```yaml
# Per-action bench results submitted by the author
benches:
  - action: send_msg
    submitted_by: alice
    submitted_at: 2026-08-29
    with_skill:
      brain: claude-sonnet-5
      trace_ref: traces/send_msg-with-skill.jsonl
      steps: 3                     # tool calls
      tokens: 412                  # LLM tokens consumed
      wall_s: 8.3
      success: true                # end_state_validator PASSED
    without_skill:
      brain: claude-sonnet-5       # same brain
      trace_ref: traces/send_msg-without-skill.jsonl
      steps: 47
      tokens: 12_840
      wall_s: 62.1
      success: true                # both PASSED; skill is faster+cheaper
  # Optional additional entries at other brains — no fixed matrix
```

Trust model: user-submitted, honesty-based. No cloud verification in v1.6.0. CI does not enforce bench presence.

The `ghost skill bench <skill>` CLI today runs only the AndroidWorld replay arm (`--androidworld <Task>`, deterministic replay judged by AndroidWorld's evaluator, summary in `bench/androidworld.json`); the agent arms described next are planned (v1.7 in progress) and will generate this file by running the action's `test_case.ref_prompt_variants` twice (with-skill installed vs without-skill installed) and diffing the traces. In v1.6.0 `bench.yaml` is hand-written.

---

## 7. Fingerprint match + fallback

> **Status (v1.6.0):** fingerprint distance matching, warn-and-execute, refuse at 3+, `--strict-fingerprint` and `ghost skill doctor <ref> --device` are implemented (`gitd/skills/engine/fingerprint.py`); MCP `run_skill` returns the report under `fingerprint`. Adapt (LLM re-mines from SOFT.md) and Mine are planned for v1.7+, not implemented.

At `ghost skill run <name>` time, the engine evaluates the skill's `fingerprint:` against the target device:

- Each field independently — `os`, `os_version`, `hardware`, `app_package`, `app_version`
- Wildcards (`"*"`) always match
- Version fields use SemVer range semantics
- **Match distance** = count of non-matching fields (0 = perfect, 5 = totally different app)

Engine behavior by distance:

| Distance | Action (shipped) |
|---|---|
| 0 | **Hit**: execute the hard-skill as-is |
| 1-2 | **Warn + execute**: "fingerprint distance 2 (os_version: skill '>=14' vs device '13', ...); proceeding, the skill may fail" |
| 3+ | **Refuse** with the mismatched fields; `--force-fingerprint` overrides. The Adapt tier (LLM re-mines from SOFT.md) is planned for v1.7+ |
| No skill exists | `ghost skill find` returns nothing; author one (`ghost skill scaffold`) |

`--strict-fingerprint` requires distance 0; `--no-fingerprint-check` skips the probe; `ghost skill doctor <ref> --device <serial>` shows the fit before you run.

---

## 8. Trust tier metadata (registry-side)

The author does NOT set `trust:` in `skill.yaml`. The registry (`skillhub/registry.json`, field `trust`) assigns it based on where the skill lives:

| Filesystem location | Registry entry | Assigned tier |
|---|---|---|
| `skillhub/ghost/<slug>/skill.yaml` | `skillhub/registry.json` | `official` |
| `skillhub/<user>/<slug>/skill.yaml` | `skillhub/registry.json` | `verified` |
| Arbitrary GitHub URL or local path | Not in registry | `unverified` |
| Registry entry flagged by maintainers | `skillhub/registry.json` | `quarantined` (install refuses without `--force`) |

Install UX (`ghost skill install <ref>`):
- **official**: silent
- **verified**: 1-line note — "Installing verified community skill by @alice"
- **unverified**: prompt — "⚠️ UNVERIFIED. Contains Python code that will run on your machine + phone. Review at `<url>`. Continue? (y/N)". `--yes-python` auto-accepts.
- **quarantined**: blocked. `--force` overrides with additional warning.

---

## 9. Full example — `alice/whatsapp-messaging`

```yaml
name: whatsapp-messaging
version: 1.0.0
author: alice
description: "Send + receive DMs on WhatsApp"
skill_class: hard
data_access: [contacts, notifications]

fingerprint:
  os: android
  os_version: ">=14"
  hardware: "samsung-s24"
  app_package: com.whatsapp
  app_version: ">=2.24.15"

repo_url: "https://github.com/ghost-in-the-droid/android-agent"
skill_path: "skillhub/alice/whatsapp-messaging"

popup_detectors:
  - {detect: "Allow WhatsApp", button: "Allow", label: "Permission"}
  - {detect: "Not now", button: "Not now", label: "Update nag"}

actions:
  - name: send_msg
    description: "Send text to a contact"
    ref_prompt: "Text John Smith saying I'll be late"
    params:
      - {name: contact_name, type: str, required: true}
      - {name: message, type: str, required: true}
    steps:
      - {action: launch_app, package: com.whatsapp}
      - {action: dismiss_popups}
      - {action: tap_element, id: search_button}
      - {action: type_text, text: "{contact_name}"}
      - {action: wait_for_text, text: "{contact_name}", timeout_s: 5}
      - {action: tap_element, text: "{contact_name}"}
      - {action: type_text, text: "{message}"}
      - {action: tap_element, desc: Send button}
    end_state_validator:
      all_of:
        - {kind: text_visible, text: "{message}"}
        - {kind: element_present, desc: message_sent_check}
    test_case:
      ref_prompt_variants:
        - "text mom I'll be home late"
        - "message Jane about the meeting"
      expected_success: true

  - name: reply_last_msg
    description: "Reply to the last message in the currently open chat"
    ref_prompt: "Reply saying yes"
    params:
      - {name: message, type: str, required: true}
    steps:
      - {action: type_text, text: "{message}"}
      - {action: tap_element, desc: Send button}
    end_state_validator:
      all_of:
        - {kind: text_visible, text: "{message}"}
```

---

## 10. Migration from v1

`ghost skill migrate <path>` runs a mechanical rewrite:
- Wraps `exports.actions[]` list into first-class `actions[]:` entries with default `ref_prompt: "(unspecified)"`, empty `test_case:`, empty `end_state_validator:` (author fills in)
- Copies `app_package` + `app_version_tested` into new `fingerprint:` block with `os_version: "*"`, `hardware: "*"` (widest match)
- Preserves `popup_detectors:` as-is
- Emits a `docs/MIGRATION.md` diff for each converted skill
- Adds a `SOFT.md` stub with the author's `description:` + step names (author fills in narrative)

Failing to fill in `end_state_validator:` + `ref_prompt:` after migration means:
- `ghost skill validate` warns
- `ghost skill test` fails on dry run (validator returns false-by-default)
- Registry entry gets `bench_available: false` flag

Migration is one-shot; no need to re-run after author completes the fill-in.

---

## 11. Reserved / disallowed keys

- `trust:` — set by the registry, ignored if in author's `skill.yaml`
- `submitted_by:`, `submitted_at:` in top-level — reserved for registry metadata
- Any `python_action:` pointing outside the skill's own directory (`../../evil`) — hard-block in CI
- Any `python_action:` importing `os`, `sys`, `subprocess` at module load time (before function call) — soft-warn in CI, reviewer attention

---

## 12. Version + evolution

This is Schema v2 (v1.6.0 release). Future changes:
- v2.1: add `platform_specific:` blocks for cross-OS skills (Android + iOS in one skill)
- v3: cloud-verified skills with signed traces


## Ask step (human or agent in the loop)

`ask:` collects one typed answer inside a deterministic run. Required fields are
`who` (`human`, `parent_agent`, or `sub_agent`), `prompt`, `schema`, and `store_as`.
The schema type is `str`, `int`, `enum` (with nonempty `values`), or `json`.
Answers are strictly validated and saved in context for `{context.<store_as>}`.

```yaml
- ask:
    who: parent_agent
    prompt: Which item should be selected?
    attach: [screenshot, a11y, {params: [query]}]
    schema: {type: enum, values: [first, second]}
    store_as: selection
    timeout_s: 0
    fallback: fail
```

Attachments are optional: PNG screenshot in base64, a11y text trimmed to 20 KB,
and selected input params. `timeout_s` is a nonnegative integer; zero waits
indefinitely. `fallback: {value: ...}` provides a schema-valid answer on timeout
or provider unavailability; `fail` returns a typed ask error. Any ask without a
value fallback makes the skill soft. Agent asks mark replay token usage in the
registry, including when a fallback keeps the skill hard.

Human asks use the checkpoint channel's typed answer method. Local embeddings
call `LocalChannel.answer(value)`; DB channels accept `answer:<JSON>` in the
resume signal. Existing checkpoint resume behavior is unchanged. Parent asks
return `status: needs_input`, `resume_token`, prompt, attachments and schema in
the run result. State is stored privately in `~/.ghost/runs/<token>.json`.
Use MCP `run_skill_resume(token, answer)` (answer is JSON text) or
`ghost skill resume <token> --answer '<json>'`. Invalid answers leave the token
available; accepted answers consume it and continue on the same device serial.

The pluggable `AskAgent.answer` hook uses the Ghost Claude Code provider when
available, with tools disabled and at most three turns. It falls back when the
provider is unavailable. Dry mode uses the fallback or a typed placeholder and
records a trace note. Ask metadata (`who`, `prompt`, `schema`, `answered_by`,
`duration_ms`) is included in traces and signed artifacts; screenshots are never
included in those records.

## State prerequisites and secrets

The v1.6 [state model](skill-state-model.md) defines `state_probes`, action
`requires_state` / `provides_state` / `clears_state`, `idempotent`, and parameter
`secret: true`. The **auto-login runner: beta** probes prerequisites and attempts
bounded same-skill transitions with caller-supplied credentials.
