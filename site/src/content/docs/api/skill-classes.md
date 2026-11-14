---
title: "🧬 Skill Schema v2 Reference"
description: The complete YAML spec for a Ghost skill — every field, every primitive, every default. Reference companion to /skills/creating-skills/.
---

Full specification for `skill.yaml` in Ghost's Schema v2 (v1.6.0+).

For the concept walkthrough, see [Skill System](/features/skill-system/). For the author how-to, see [Creating Skills](/skills/creating-skills/). This page is the field-by-field reference.

---

## Top-level structure

```yaml
# Identity
name: whatsapp-messaging           # kebab-case slug
version: 1.0.0                     # SemVer
author: alice                      # github handle (or "ghost" for official)
description: "Send + receive DMs on WhatsApp"

# Classification
skill_class: hard | soft           # required
data_access:                       # required — informational, drives Hub badge
  - contacts | sms | camera | mic | location | notifications | clipboard | files | storage

# Fingerprint (versioning matrix)
fingerprint:
  os: android | ios
  os_version: ">=14"               # SemVer range
  hardware: "samsung-s24" | "*"    # exact model or wildcard
  app_package: com.whatsapp        # Android pkg or iOS bundle id
  app_version: ">=2.24.15"

# Entry (soft-skill web flows only)
entry_url: "https://account.proton.me/mail/signup"    # optional

# Registry
repo_url: "https://github.com/ghost-in-the-droid/android-agent"
skill_path: "skillhub/alice/whatsapp-messaging"

# Popup handling (Layer 2)
popup_detectors:
  - {detect: "Allow WhatsApp", button: "Allow"}
os_popup_policy:                   # Layer 1 per-skill overrides
  allow_permissions: [storage]
  deny_permissions: [contacts]
  ignore: [google_play_update]

# Subroutines (internal reusable step-lists — de-dup within skill)
subroutines:
  - name: open_chat_list
    description: "..."
    steps: [...]

# Actions (first-class, agent-invocable)
actions:
  - name: send_msg
    ref_prompt: "..."
    params: [...]
    pre_hooks: [...]
    steps: [...]
    checkpoints: [...]
    end_state_validator: {...}
    on_popup: {...}
    test_case: {...}
```

---

## Actions

```yaml
actions:
  - name: send_msg                       # kebab-case within skill's namespace
    description: "Send a text to a contact"
    ref_prompt: "Text John saying I'm running late"    # canonical NL phrase
    params:
      - name: contact_name
        type: str
        required: true
        description: "Contact display name to search for"
      - name: message
        type: str
        required: true
      - name: attach_image
        type: bool
        default: false
      - name: priority
        type: enum
        values: [normal, urgent]
        default: normal
      - name: tags
        type: "list[str]"                # quoted — YAML flow syntax
        default: []

    # Optional pre-flow Python prep (runs BEFORE device steps)
    pre_hooks:
      - {python_action: "community.alice.whatsapp_messaging.helpers:normalize_contact"}

    # The step sequence
    steps:
      - subroutine: open_chat_list
      - {action: tap_element, id: search_button}
      - {action: type_text, text: "{contact_name}"}
      - {action: tap_element, text: "{contact_name}"}
      - {action: type_text, text: "{message}"}
      - {action: tap_element, desc: Send button}

    # HITL/external-code/LLM-decision gates (makes skill soft)
    checkpoints:
      - after_step: send
        reason: captcha                   # captcha | sms | email | login | llm_decision | generic
        prompt: "Solve the captcha"
        success: {kind: url_contains, substring: "/inbox"}
        timeout_s: 60                     # default 60; 0 = wait indefinitely

    # Popup override — for popups that are part of the flow (not to dismiss)
    on_popup:
      "Ad authorization":
        method: accept
        steps:
          - {action: tap_element, text: "Authorize"}
          - {action: tap_element, text: "Save"}

    # Terminal state — REQUIRED
    end_state_validator:
      all_of:
        - {kind: text_visible, text: "{message}"}
        - {kind: element_present, desc: message_sent_check}

    # Per-action bench + test spec
    test_case:
      ref_prompt_variants:
        - "text mom I'll be home late"
        - "message Jane about the meeting"
      expected_success: true
```

---

## Step primitives (all 16 built-in)

Every step is either `{action: <name>, ...args}` (name lookup) OR a structural key (`python_action`, `if_visible`, `retry`, `run_skill`, `subroutine`, `checkpoint`).

### Atomic device interactions

| `action:` | Fields | Notes |
|---|---|---|
| `tap` | `x, y, delay_s?` | Coord tap |
| `tap_element` | `id? \| desc? \| text? \| xpath?` | Locator chain: id → desc → text → xpath |
| `type_text` | `text, clear_first?` | Types via `adb shell input text` w/ shell-safe quoting; supports `{param}` |
| `long_press` | `x, y, duration_ms` | |
| `swipe` | `x1, y1, x2, y2, duration_ms?` | |
| `press_key` | `key: HOME \| BACK \| ENTER \| VOLUME_UP \| ...` | Uses Device shortcut methods where available, else adb keyevent |
| `launch_app` | `package, activity?` | `am start -n pkg/act` or monkey launcher |
| `launch_intent` | `intent_action, package?, activity?, mime_type?, data?, category?, extras?` | Full Android Intent. `content://` values in extras use `--eu` (URI). Needed for share flows. |
| `open_url` | `url, browser?` | Chrome default, else launches specified pkg |
| `screenshot` | `save_as?` | `screencap -p` |
| `dump_xml` | `save_as?` | Fast uiautomator + Portal fallback |
| `dismiss_popups` | — | Runs skill's `popup_detectors:` once explicitly |

### Waits

| `action:` | Fields |
|---|---|
| `wait_for_text` | `text, timeout_s?` (default 10). Mid-poll popup sweep enabled. |
| `wait_for_element` | `id? \| desc? \| xpath?, timeout_s?` |
| `sleep` | `duration_s` |

### Control flow

| Key | Fields |
|---|---|
| `if_visible:` | `{selector: {id\|desc\|text}, then: [steps], else?: [steps]}` |
| `retry:` | `{max, backoff_s, steps: [...], on_failure?: <step>}` |
| `run_skill:` | `{name: <user>/<slug>, action: <name>, params?: {...}}` — cross-skill composition |
| `subroutine:` | `<name>` — in-skill composition (looks up `subroutines[]`) |
| `checkpoint:` | `{reason, prompt, success: <validator>, timeout_s?}` — HITL/external-code gate |

### Escape hatch

| Key | Fields |
|---|---|
| `python_action:` | `<module>:<function>` — signature `(device, params, context) -> ActionResult`. Merges returned `.data` into `ctx.result`. |

---

## Validator primitives (all 7 built-in)

Compose via `all_of` / `any_of` / `not` (recursive):

```yaml
end_state_validator:
  all_of:
    - {kind: text_visible, text: "Sent"}
    - any_of:
        - {kind: element_present, id: sent_check}
        - {kind: pixel_at, x: 990, y: 1200, rgb: [34, 187, 51]}
    - not:
        {kind: text_visible, text: "Failed to send"}
```

| `kind:` | Fields | Description |
|---|---|---|
| `text_visible` | `text, exact?` | Text appears in a11y tree |
| `element_present` | `id? \| desc? \| xpath?` | Element in a11y tree |
| `url_contains` | `substring` | Current WebView URL |
| `pixel_at` | `x, y, rgb: [r,g,b], tolerance?` (default 8) | Pixel color within tolerance |
| `ocr_text_present` | `text, region?: {x, y, w, h}` | RapidOCR on screencap (optionally in region) |
| `screen_hash` | `ref_hash, similarity_min?` (default 0.85) | Perceptual hash match |
| `custom_python` | `function: <module>:<function>` | Predicate `(device, context) -> bool` |

Bare list at `end_state_validator:` level = AND semantics.

---

## Interpolation

Placeholder syntax in yaml string values:

- `{name}` — from `params[name]`
- `{context.attr}` — from `ctx.extras[attr]` or `ctx.result[attr]` (set by python_action targets)
- `{{literal}}` — escape (produces `{literal}`)

Pipe filters:

- `{name | capitalize}`, `| lower`, `| upper`, `| strip`, `| int`, `| str`, `| len`
- `{tags | join:,}` — join list with separator arg

---

## Subroutines

```yaml
subroutines:
  - name: nav_to_profile_tab
    description: "Launch TT + navigate to Profile tab. Idempotent."
    steps:
      - {action: launch_app, package: com.zhiliaoapp.musically}
      - {action: sleep, duration_s: 3}
      - {action: tap, x: 972, y: 2214}
      - {action: wait_for_element, desc: "Profile menu"}
```

Rules:
- Kebab-case name, unique within skill
- Cannot collide with an action name
- Non-empty `steps:` required
- No `ref_prompt` / `end_state_validator` / `test_case` fields (not agent-invocable)
- Called from step context: `- subroutine: nav_to_profile_tab`
- Max recursion depth: 5 (shared stack with `run_skill:`)
- Cycle detection built-in

---

## Fingerprint match rules

> **Status (v1.6.0):** fingerprint distance matching, warn-and-execute, refuse at 3+, `--strict-fingerprint` and `ghost skill doctor <ref> --device` are implemented (`gitd/skills/engine/fingerprint.py`); MCP `run_skill` returns the report under `fingerprint`. Adapt (LLM re-mines from SOFT.md) and Mine are planned for v1.7+, not implemented.

At `run_action` time, engine compares skill's `fingerprint:` against the target device:

| Distance | Behavior (shipped) |
|---|---|
| 0 | Hit: execute as-is |
| 1-2 | Warn + execute; the mismatched fields are printed (CLI) or returned under `fingerprint` (MCP) |
| 3+ | Refuse with the mismatched fields; `--force-fingerprint` runs anyway. Adapt is planned (v1.7+) |
| No skill exists | `ghost skill find "<intent>"` returns nothing; author one (`ghost skill scaffold`) |

`--strict-fingerprint` requires distance 0; `--no-fingerprint-check` skips the probe; `ghost skill doctor <ref> --device <serial>` shows the fit before you run.

---

## Reserved keys

- `trust:` — set by the registry, ignored if in author's skill.yaml
- `submitted_by:`, `submitted_at:` in top-level — reserved for registry metadata
- Any `python_action:` targeting outside the skill's own directory (`../../evil`) — hard-block in CI
- Any `python_action:` doing `import os; os.system(...)` at module-load — soft-warn in CI, reviewer attention

---

## Related

- [Skill System](/features/skill-system/) — architectural walkthrough
- [Execution Engine](/features/skill-execution-engine/) — runtime internals
- [Creating Skills](/skills/creating-skills/) — author flow
- Local `docs/skill-schema-v2.md` — most-detailed reference (source-of-truth for this page)
