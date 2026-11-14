# Ghost Skill System — Internal Reference

Single canonical doc covering the whole Skill System: concepts, schema, engine, CLI, publishing, current state. Internal reference — not for public site. Site pages at `/skills/*` + `/features/skill-*` are user-facing renders of this.

**Ratified**: 2026-09-07 by the maintainer. Reflects post-Phase 1-4 + subroutines state (branch `feat/skills-refactor`). Section 17 updated 2026-10-05 for `feat/skillhub`.

---

## 1. Core concept

**Skills cost $0. Thinking costs tokens.**

A Skill is a named, versioned bundle of Actions for a specific app fingerprint. Once authored, replays deterministically at zero LLM cost forever. That's the whole point.

Vocabulary:

| Term | What it is |
|---|---|
| **Skill** | Named package. `ghost/tiktok` (official) or `alice/whatsapp-messaging` (community). Lives at `skillhub/ghost/<slug>/` or `skillhub/<user>/<slug>/`. |
| **Action** | Agent-invocable capability. Has `ref_prompt`, typed `params`, `steps`, `end_state_validator`, `test_case`. |
| **Subroutine** | Reusable step-list internal to a skill. NOT agent-invocable. De-dups boilerplate. |
| **Step** | Atomic op: `tap`, `type_text`, `wait_for_element`, `launch_intent`, `python_action`, `if_visible`, `retry`, etc. |
| **Validator** | Predicate on terminal screen: `text_visible`, `element_present`, `pixel_at`, `ocr_text_present`, `custom_python`. Composable via `all_of`/`any_of`/`not`. |
| **Fingerprint** | (OS × OS-version × hardware × app-package × app-version). Determines Hit vs Adapt vs Mine (only Hit exists in v1.6.0, see section 11). |

---

## 2. Hard vs Soft

**Hard skill** — deterministic. Zero LLM at replay. Zero human. Every step resolves via stable locator or `python_action`. Examples: `tiktok/upload_video`, `google_maps/get_directions`. Guarantee: same input → same terminal screen.

**Soft skill** — cannot be fully deterministic. Has one or more gates:
- **HITL checkpoint** — captcha, drag-puzzle. Engine pauses, streams live screen, waits for human.
- **External-code checkpoint** — SMS / email verification code fetched from a channel the skill controls.
- **LLM decision point** — next step depends on interpreting novel screen. Costs tokens.

Examples: any account registration or verification flow (HITL captcha, email code).

Guarantee: best-effort with explicit checkpoints. Terminal success = validator pass, not step count.

---

## 3. Three acquisition tiers

When an agent needs action X in app Y on YOUR device:

| Tier | Path | Cost |
|---|---|---|
| **1 — Hit** | Install matching hard-skill, execute | $0 |
| **2 — Adapt** | LLM re-mines using soft-skill + top-3 nearest hard-skills as reference | Tokens once, then $0 |
| **3 — Mine** | Skill Miner (`auto_creator.py`) BFS-explores app + LLM writes skill from scratch | Tokens for exploration + one authoring pass |

**Meta-tier**: `skill-creation-guide` skill in the Hub is distributed as LLM-context for adapt + mine flows. Teaches any competent LLM how to author skills.

Fingerprint match distance (0-5, count of non-matching fields): 0 = Hit, 1-2 = warn + try, 3+ = Adapt automatic, no skill = Mine. Status: only Hit (run as authored) exists in v1.6.0; distance matching is v1.7 work, Adapt and Mine are planned.

---

## 4. Trust tiers

| Tier | Location | Install UX |
|---|---|---|
| 🟢 **Official** | `skillhub/ghost/*` (official namespace) | Silent |
| 🔵 **Verified** | `skillhub/<user>/<slug>/` after PR merge | "Community skill by @user" |
| 🟡 **Unverified** | `ghost skill install <arbitrary-github-url>` | ⚠ "Contains Python. Review at `<url>`. Continue? (y/N)" |
| 🔴 **Quarantined** | Registry-flagged | Blocked. `--force` overrides. |

Trust exists because skills contain executable Python (`python_action:`). Author never sets `trust:` — the registry assigns based on filesystem location.

---

## 5. Skill layout

```
skill.yaml              schema-v2 spec
SOFT.md                 LLM-adaptable narrative (Tier 2 Adapt reference)
README.md               human overview + demo GIF
helpers.py              python_action + custom_python targets (flat, no subpackage)
bench.yaml              optional: with-vs-without-skill trace results
data/                   optional: ref screenshots for screen_hash, etc.
```

Notes: v1 had `actions/` + `workflows/` subpackages. v2 collapsed to flat `helpers.py`. Old subpackage empty dirs = dead — removed.

---

## 6. Schema v2 top-level

```yaml
# Identity
name: whatsapp-messaging
version: 1.0.0                     # SemVer
author: alice                      # github handle (or "ghost" for official)
description: "..."

# Classification
skill_class: hard | soft
data_access: [contacts, sms, camera, mic, location, notifications, clipboard, files, storage]

# Fingerprint
fingerprint:
  os: android | ios
  os_version: ">=14"
  hardware: "samsung-s24" | "*"
  app_package: com.whatsapp
  app_version: ">=2.24.15"

# Entry (soft-skill web flows only)
entry_url: "https://..."           # optional

# Registry
repo_url: "..."
skill_path: "..."

# Popup handling — Layer 1 (per-skill overrides)
os_popup_policy:
  allow_permissions: [storage]
  deny_permissions: [contacts]
  ignore: [google_play_update]

# Popup handling — Layer 2 (app-specific)
popup_detectors:
  - {detect: "Continue editing", button: "Save draft"}
  - {detect: "Learn more", method: back}

# Subroutines (internal reusable step-lists)
subroutines:
  - name: nav_to_profile_tab
    description: "..."
    steps: [...]

# Actions (agent-invocable, first-class)
actions:
  - name: send_msg
    ref_prompt: "..."
    params: [...]
    pre_hooks: [...]
    steps: [...]
    checkpoints: [...]                   # optional, HITL gates
    on_popup: {...}                       # optional, Layer 3 overrides
    end_state_validator: {...}
    test_case: {...}
```

---

## 7. Action structure

```yaml
- name: send_msg
  description: "Send text to a contact"
  ref_prompt: "Text John saying I'm late"    # canonical NL — LLM matches on this
  params:
    - {name: contact_name, type: str, required: true, description: "..."}
    - {name: message, type: str, required: true}
    - {name: attach, type: bool, default: false}
    - {name: priority, type: enum, values: [normal, urgent], default: normal}
    - {name: tags, type: "list[str]", default: []}      # quote list[str] — yaml flow gotcha
  pre_hooks:
    - {python_action: "helpers:prep_stuff"}    # runs BEFORE steps
  steps:
    - subroutine: nav_to_chat_list
    - {action: type_text, text: "{contact_name}"}
    - python_action: "helpers:tap_contact_row"
  checkpoints:                                 # optional, makes skill soft
    - after_step: send
      reason: captcha | sms | email | login | llm_decision | generic
      prompt: "Solve the captcha"
      success: {kind: url_contains, substring: "/inbox"}
      timeout_s: 60
  on_popup:                                    # optional Layer 3 override
    "Ad authorization":
      method: accept
      steps: [...]
  end_state_validator:                         # required
    all_of:
      - {kind: text_visible, text: "{message}"}
      - {kind: element_present, desc: sent_check}
  test_case:
    ref_prompt_variants: ["text mom", "message Jane"]
    expected_success: true
```

Every action needs: `ref_prompt`, `params[]`, `steps[]`, `end_state_validator`, `test_case`.

---

## 8. Step primitives (16 built-in)

**Atomic device**:
- `tap` (x, y, delay_s?)
- `tap_element` (id? | desc? | text? | xpath?) — locator chain: id → desc → text → xpath
- `type_text` (text, clear_first?) — shell-safe via `input_text_arg`
- `long_press` (x, y, duration_ms)
- `swipe` (x1, y1, x2, y2, duration_ms?)
- `press_key` (key: HOME|BACK|ENTER|...)
- `launch_app` (package, activity?)
- `launch_intent` (intent_action, package?, activity?, mime_type?, data?, category?, extras?) — content:// URIs use --eu automatically
- `open_url` (url, browser?)
- `screenshot` (save_as?)
- `dump_xml` (save_as?)
- `dismiss_popups` — runs skill's popup_detectors once explicitly

**Waits**:
- `wait_for_text` (text, timeout_s?) — default 10s, has mid-poll popup sweep
- `wait_for_element` (id? | desc? | xpath?, timeout_s?)
- `sleep` (duration_s)

**Control flow** (structural keys, not `action:`):
- `if_visible: {selector, then: [...], else: [...]}` — conditional branching
- `retry: {max, backoff_s, steps: [...], on_failure?}` — retry wrapper
- `run_skill: {name, action, params?}` — cross-skill composition
- `subroutine: <name>` — in-skill composition (references skill.subroutines[])
- `checkpoint: {reason, prompt, success, timeout_s?}` — HITL gate

**Escape hatch**:
- `python_action: <module>:<function>` — signature `(device, params, context) -> ActionResult`. Merges `.data` into `ctx.result`.

Pluggable: `@register_step("name")` decorator lets skills/plugins add step types.

---

## 9. Validator primitives (7 built-in)

Compose via `all_of` / `any_of` / `not` (recursive).

- `text_visible` (text, exact?) — a11y tree substring match
- `element_present` (id? | desc? | xpath?) — element in a11y tree
- `url_contains` (substring) — WebView URL substring
- `pixel_at` (x, y, rgb, tolerance?) — screencap pixel color check
- `ocr_text_present` (text, region?) — RapidOCR on screencap
- `screen_hash` (ref_hash, similarity_min?) — perceptual hash match
- `custom_python` (function) — arbitrary predicate `(device, context) -> bool`

Pluggable: `@register_validator("kind")`.

---

## 10. Popup handling (4 layers)

**Layer 1 — engine-global OS popups** (always-on, `gitd/skills/engine/os_popups.py`):
- 6 permission dialogs (location, contacts, storage, camera, microphone, notifications) — default DENY, `os_popup_policy.allow_permissions[]` opt-in
- 5 other OS popups: battery_optimization (cancel), google_play_update (not now), keyboard_default (cancel), screen_recording (allow — Ghost needs it), system_update (later)

**Layer 2 — skill-scoped `popup_detectors:`** (app-specific, in skill.yaml):
```yaml
popup_detectors:
  - {detect: "Continue editing", button: "Save draft"}
  - {detect: "Learn more", method: back}    # method: back | tap_outside
  - {detect: "Foo", button: "Bar", only_in_actions: [action_a, action_b]}
  - {detect: "Baz", button: "Qux", not_in_actions: [action_c]}
```

**Layer 3 — action-level `on_popup:`** (custom response for popups PART of the flow):
```yaml
on_popup:
  "Ad authorization":
    method: accept | dismiss | prompt_user | custom_python
    steps: [...]
```

**Layer 4 — unknown-popup safety net** (implicit, `unknown_popup.py`):
- Diff-heuristic detects new modal (text-node count drop >30%, new "Allow/OK/Cancel/Not now" buttons)
- Screenshot to `/tmp/ghost-skills-artifacts/`
- Dismiss cascade: BACK
- Retry failed step ONCE
- Else raise `UnknownPopupError` with screenshot path

Layer 1+2 pre-sweep runs only before a11y-reading steps (`tap_element`, `wait_for_*`, `dump_xml`, `if_visible`). Blind ops (`sleep`, `tap`, `press_key`, `launch_app`, `launch_intent`, `type_text`) skip pre-sweep → 3× speedup on video-app skills.

---

## 11. Fingerprint match

> **Status (v1.6.0):** fingerprint distance matching, warn-and-execute, refuse at 3+, `--strict-fingerprint` and `ghost skill doctor <ref> --device` are implemented (`gitd/skills/engine/fingerprint.py`); MCP `run_skill` returns the report under `fingerprint`. Adapt (LLM re-mines from SOFT.md) and Mine are planned for v1.7+, not implemented.

Fields: `os`, `os_version`, `hardware`, `app_package`, `app_version`. Wildcards (`"*"`) always match. SemVer ranges per version field.

Distance = count of non-matching fields:

| Distance | Behavior (shipped in `gitd/skills/engine/fingerprint.py`) |
|---|---|
| 0 | Hit: execute |
| 1-2 | Warn + execute (`ghost skill run` prints the mismatched fields; MCP `run_skill` returns them under `fingerprint`) |
| 3+ | Refuse with the mismatched fields; `--force-fingerprint` runs anyway. The LLM Adapt tier is planned (v1.7+), not implemented |
| No skill | `ghost skill find "<intent>"` finds nothing; drive the app directly or author a skill |

`--strict-fingerprint` requires distance 0 (MCP: `GHOST_STRICT_FINGERPRINT=1`); `--no-fingerprint-check` skips the probe. A device that cannot be probed (iOS without `--fingerprint`, adb unreachable) runs unchecked unless strict. `ghost skill doctor <ref> --device <serial>` prints the authored fingerprint, every fingerprint in `runs/`, the distance and the nearest tested fingerprint.

---

## 12. Engine module map

`gitd/skills/engine/` (~2500 LOC total, pluggable via `@register_step` + `@register_validator`):

| File | LOC | Purpose |
|---|---|---|
| `__init__.py` | 30 | Public API: `load_skill`, `run_action`, `RunResult`, `RunContext` |
| `loader.py` | 320 | Parses skill.yaml → typed dataclasses + Schema v2 validation |
| `context.py` | 50 | `RunContext` (params, result, extras, device_serial, step_index) |
| `interpolate.py` | 115 | `{param}` + `{context.attr}` resolution + pipe filters (capitalize/lower/upper/strip/int/str/len/join) |
| `errors.py` | 100 | 10 typed error classes (agent-parseable via `.as_dict()`) |
| `dispatch.py` | 450 | Step handler registry + 16 built-in handlers |
| `validators.py` | 210 | Validator kind registry + 7 built-in kinds + composition |
| `os_popups.py` | 165 | Phase 3 Layer 1 |
| `unknown_popup.py` | 120 | Phase 3 Layer 4 |
| `runner.py` | 315 | Orchestrator |
| `cli.py` | 340 | `ghost skill` subcommands |

**Error hierarchy**: all subclass `SkillError`. `.as_dict()` returns `{kind, message, skill, action, step_index, step, payload, hint}`.

**Run lifecycle**:
1. Resolve params (type check, defaults, enum validate)
2. Build `RunContext` w/ params + device_serial + skill metadata (popup detectors, os_popup_policy, current_skill_dir)
3. Run `pre_hooks[]`
4. For each step: interpolate → Layer 1+2 popup sweep (if a11y-reader) → snapshot a11y before → dispatch → Layer 4 safety net if failed + new-popup detected
5. Interpolate + evaluate `end_state_validator`
6. Return `RunResult(success, data, error, duration_ms, trace[])`. Never raises.

---

## 13. CLI

```bash
ghost skill scaffold <user>/<slug> [--app PKG] [--actions a,b,c] [--skill-class hard|soft] [--official]
ghost skill validate <path>                                # schema + import checks (dry, ~1s)
ghost skill test <path> [--live] [--action NAME] [--param k=v] [--device SERIAL]
ghost skill run <path> <action> [--param k=v] [--device SERIAL]
ghost skill submit <path> --push                             # gh fork + isolated-index commit + PR (plan only without --push)
ghost skill migrate <v1-path>                                # v1→v2 rewrite in place
ghost skill list                                             # installed skills
ghost skill list-registered                                  # engine's step + validator primitives

ghost skill bench <ref> --androidworld <Task> --bridge-cmd "<aw_bridge cmd>"   # AndroidWorld replay arm, scored by task.is_successful
# Planned (v1.7): ghost skill mine (Skill Miner), ghost skill bench agent arms (with-vs-without-skill runs)
ghost skill install <slug>                                   # v1-legacy, delegates to gitd.cli
ghost skill install alice/foo --yes            # non-official installs print an install card (has_python, data_access, side_effects, tos_risk, tested-on); a community skill with Python needs --yes or a y/N the first time
ghost skill search <query>                                   # v1-legacy
ghost skill find "<intent>" [--top N] [--json] [--no-hub]     # BM25 over names, descriptions, ref prompts, app package; MCP: find_skill(intent)
ghost skill fork <src> --as <author>/<slug> [--out DIR]     # copy without runs/verifications/demos, version 0.1.0, forked_from lineage
ghost skill deprecate <path> --reason "..." [--superseded-by <ref>] [--undo]   # status: deprecated + reason + replacement ref
ghost skill update <slug>                                    # v1-legacy
ghost skill remove <slug>                                    # v1-legacy
```

CLI wired via `ghost_cli.py` local subcommand routing → `gitd/skills/engine/cli.py:main`.

---

## 14. Publishing flow (PR-based)

All community submissions are GitHub PRs to `ghost-in-the-droid/android-agent`. No separate service — GitHub identity is the auth.

`ghost skill submit <path>` prints the plan (title, branch, files, PR body) after the static analysis; a high-severity finding stops it. `--push` wraps `gh` and `git` without touching your checkout or index:
1. `gh repo fork <hub repo> --clone=false` (idempotent; skipped when you own the target)
2. Fetch the target's default branch and build one commit of `skillhub/<author>/<slug>/` on an isolated index, parented on that branch
3. Force-update `skill/<author>-<slug>` on your fork (a resubmission is a fresh commit, not a child of the last attempt)
4. `gh pr create --title "[skill] <author>/<slug> v<version>"`, or reuse the open PR for that branch
The registry is never edited by the submitter; CI regenerates it after merge.

CI on the PR (`.github/workflows/skill-submission.yml`, shipped; `docs/skillhub/security.md` lists what is enforced):
1. `ghost skill validate` — hard-block
2. Static analyzer on `python_action:` targets — flags `os.system`, `subprocess shell=True`, `exec/eval`, `__import__`, network outside `gitd.http`, filesystem writes outside skill dir, obfuscated strings. Adds `needs-security-review` label. Not auto-reject.
3. Emulator smoke — run each action's `test_case.ref_prompt_variants[0]` in dry mode. Hard-block on parse/import.
4. Bench sanity — verify `bench.yaml` structure (no re-run).
5. README + SOFT.md non-empty — soft-warn.

Human review always required. Turnaround target: 3-7 days.

On merge: skill lives at `skillhub/<user>/<slug>/`, `skillhub/registry.json` is regenerated by the registry workflow and served through jsDelivr (CDN cache purged), `trust` → verified (community).

Registry endpoint (fetched by `ghost skill install`): one file, `skillhub/registry.json` at `main`, read through jsDelivr (`cdn.jsdelivr.net/gh/<repo>@main/skillhub/registry.json`), never raw.githubusercontent; skill files are fetched at the version's commit (see `gitd/skills/hub.py`).

---

## 15. Reference skill: TT (`skillhub/ghost/tiktok/`)

Reference hardest-hard-skill. 8 actions, 2 subroutines, 11 popup detectors, safety-scoped to user's-own-account only.

Actions:
- `open_my_profile` — nav (LOW)
- `open_inbox` — nav (LOW)
- `get_active_account` — scrape @handle from profile header (MED)
- `get_unread_count` — read Inbox badge count (MED)
- `get_my_stats` — scrape following/followers/likes/display_name/drafts (MED)
- `list_accounts` — enumerate all logged-in accounts from switcher (MED)
- `switch_account` — nav + drawer + tap + verify (MED)
- `upload_video` — the hard one: share intent + caption + hashtags + optional TTS + draft/post (HIGH, 9/10 steps green on ROG)

Subroutines: `nav_to_profile_tab`, `open_account_switcher`.

NOT included (stays premium): outreach, mass-crawl, engage, mass-scrape.

Live-verified on ROG <serial> / TT 44.3.3 / your_handle: 8/8 actions green (upload_video 10/10 steps, drafts counter validated).

---

## 16. Design decisions log

Decisions made during Phase 1-4 build, referenced here so future contributors know why the shape is what it is:

- **Action-first (kill v1 workflows/)** — v1's two-tier (actions/ + workflows/) was confusing. v2 collapses to one thing (Action) with clear ancillary primitives (`subroutine:` for internal reuse, `run_skill:` for cross-skill).
- **Subroutines for de-dup** — actions-only made every helper flow become a top-level agent-invocable Action with meaningless `ref_prompt`. Subroutines give clean internal reuse without polluting the agent-invocable surface.
- **`python_action:` unavoidable escape hatch** — TT upload proves it: 2000+ LOC of app-specific glue in premium. Trust tier system handles the security surface.
- **Trust tiers over auth service** — GitHub PR merge status IS the trust signal. No separate account, no separate auth server. Piggyback on `gh`.
- **4-layer popup handling** — v1's popup detectors were per-skill only; every author had to relearn Android permission patterns. Layer 1 (engine-global OS catalog) handles the 11 most common OS modals once. Layer 4 (unknown-popup safety net) makes the catalog-growth loop empirical (screenshot + `--update-popups`) rather than requiring authors to memorize every popup.
- **Popup pre-sweep selectivity** — Portal dumps are ~14s on video apps. Running pre-sweep before every step made TT skills take 90s+ per action. Restricted to a11y-reading steps → 3× speedup, same correctness.
- **Blind coord tap for video apps** — TT/IG/YT autoplay pages make `uiautomator dump` fail. Blind-tap known-stable bottom-nav coords, dump AFTER navigating to a static page. Documented per-skill in SOFT.md so adapt-mode preserves.
- **Fingerprint distance model** — old approach was "exact match or fail". New: distance-based fallback (0=Hit, 1-2=warn+try, 3+=Adapt automatic) means skills gracefully degrade rather than hard-fail on version drift.
- **Trust-on-honesty bench in v1.6.0** — cloud verification is v1.7+. Author-submitted bench numbers are trusted; discrepancies handled by human review at PR merge.
- **PR flow, not API** — no separate submission service. Every skill is a GitHub PR. Every review is a maintainer review. Every merge is a public commit. Auditable end-to-end.

---

## 17. Companion docs

- `docs/skill-taxonomy-soft-vs-hard.md` — concepts + empirical basis (hard vs soft, why registration is inherently soft)
- `docs/skill-schema-v2.md` — full YAML spec (400+ lines, most-detailed reference)
- `docs/contributing-skills.md` — PR submit flow + review process

Public site pages (all render slices of this doc):
- `/skills/overview` — concept intro
- `/skills/using-skills` — CLI usage
- `/skills/creating-skills` — author flow
- `/skills/publishing` — PR submit flow
- `/skills/elements` — locator chain reference
- `/features/skill-system` — architecture walkthrough
- `/features/skill-execution-engine` — engine internals
- `/features/skill-hub` — registry + community
- `/features/skill-creator` — Skill Miner
- `/contributing/skills` — quick-start + first-time checklist
- `/api/skill-classes` — full YAML spec (compact)
