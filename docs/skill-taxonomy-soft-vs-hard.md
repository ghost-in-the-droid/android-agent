# Skill Taxonomy

Ratified 2026-08-28.

Empirical basis: live runs of a maps skill and of account-registration flows (2026-07-19). Extended here with the action-first framing, acquisition-tier model, primitive list, and LLM-emission mapping needed to ship v1.6.0.

---

## 1. What a skill IS

A **Skill** is a named, versioned bundle of **Actions** for a specific app fingerprint. Each Action is the first-class thing an agent invokes.

- **Skill** ≈ npm package (`alice/whatsapp-messaging`)
- **Action** ≈ exported function (`send_msg`, `reply_last_msg`)
- **Agent** invokes actions via the same MCP tool surface it uses for raw device control — `run_skill(name, action, params)` is just another tool.

Multiple skills can target the same app fingerprint but expose different action sets — `alice/whatsapp-messaging` (send/reply/mark_read) vs. `bob/whatsapp-media` (upload_img, download_video). Disambiguation is `<user>/<skill>`.

Every action ships with:

- **Steps**: atomic (tap/swipe/type/...) OR dynamic (`python_action:` escape hatch)
- **`ref_prompt`**: the natural-language prompt this action is a canonical response to (e.g. `"Text John saying I'll be late"`)
- **`end_state_validator`**: predicate that must hold after the action succeeds
- **`test_case`**: prompt-variants for benching / CI validation

Skills exist because **skills cost $0, thinking costs tokens**. A shipped skill replays deterministically forever after one authoring pass.

---

## 2. Hard vs soft skills

### Hard skill — deterministic replay

Runs start-to-finish with:
- **Zero LLM calls** at replay time
- **Zero human intervention**
- Every step resolves via a known locator chain (content-desc → text → rid → class → coords) or a `python_action:` callable
- Pre/post-conditions gate each step; failure retries then aborts. No branching on unknown/novel screen content.

**Guarantee:** deterministic replay. Same input → same steps → same terminal state (validated by `end_state_validator`).

**Examples:** `google_maps/get_directions`, `tiktok/upload_video`, `send_gmail_email`.

### Soft skill — SOFT.md reference notes

The skill's `SOFT.md`: layout notes for the app (tab and element ids, first-launch dialogs, failure modes). It is what an agent uses when the hard replay does not match the phone or app version, or the task is off-script. The agent drives by hand (tap, swipe, type) following the notes, and should be faster than with no skill at all, because it skips exploring the app blind. Over MCP: `get_skill_notes(name)`.

**Guarantee:** none beyond the notes being accurate for the verified app version; the agent decides each step and success is judged by the task, not by a replay.

**Examples:** `markor` (notebook tabs, new-file FAB, save quirks), `clock` (tab ids, intent extras).

### Gates — suspend/resume points (not a skill class)

A **gate** is a point inside any skill (usually a hard skill's backbone) where the run suspends until something non-deterministic resolves it, then resumes. A human captcha is a gate, not a soft skill. Gate types:

1. **Human-in-the-loop (HITL) checkpoint** — CAPTCHA / bot-challenge, or a code that only a human channel can produce. Engine pauses, surfaces the live screen on the dashboard, waits for a human to clear the gate, resumes from that screen.
2. **External-code checkpoint** — SMS or email verification code fetched from a channel the skill controls (e.g. read the code out of an inbox the skill owns). Semi-automatable, still a suspend/resume boundary.
3. **LLM decision point** — a step where the next action depends on interpreting a novel screen or choosing among options; costs tokens, not deterministic.

Over MCP a gate returns `needs_input` with a token; answer with `run_skill_resume`.

**Guarantee:** best-effort with explicit checkpoints. Terminal success detected by the `end_state_validator`, NOT by step count.

**Examples:** any account-registration or KYC/verification flow (HITL captcha, email-code checkpoint). The registry field `skill_class: soft` marks a skill that contains a gate (legacy name for "gated"; it does not mean SOFT.md-only).

### Why the split matters

| Dimension | Hard skill | Soft skill | Gate |
|---|---|---|---|
| What it is | deterministic replay (`run_skill`) | SOFT.md notes the agent follows by hand | suspend/resume point inside a skill |
| Cost | $0 | LLM tokens, fewer than blind exploration | human-seconds / LLM tokens at the gate |
| Scheduling | headless, batch, offline | needs an agent | needs a human or brain *available* |
| Reliability | deterministic | best-effort | gate can reject |
| Failure mode | step precond fails → abort | agent adapts or fails the task | gate unresolved → **suspend**, not fail |

### Why registration flows carry gates

Registration/verification flows are **structurally gated**: providers deliberately place an anti-bot gate exactly where an autonomous agent must stop. The correct skill design does not try to defeat the gate — it declares a checkpoint and hands off.

---

## 3. Acquisition tiers — how you get action X working on your phone

When an agent needs to perform action X in app Y on YOUR device, three paths in order of preference:

### Tier 1 — Hit

Install a hard-skill whose declared fingerprint matches your device: `(os, os_version, hardware, app_package, app_version)` all satisfy the skill's `fingerprint:` block.

Cost: **$0** per invocation, deterministic replay.

Requirement: the skill exists in the registry AND matches.

### Tier 2 — Adapt

Use a skill's SOFT.md notes (or install a hard-skill whose fingerprint doesn't match — engine falls back to the SOFT.md notes + top-3 nearest hard-skills as reference).

The agent:
1. Reads the `SOFT.md` describing the workflow at a semantic level
2. Reads the top-3 nearest hard-skills as concrete-example references (with **distance info** showing what's different)
3. Re-mines the flow against your device
4. Emits a new hard-skill for YOUR fingerprint, which is then registered locally and (optionally) submitted back to the community registry

Cost: **tokens for the adapt pass; then $0 forever** for your fingerprint.

Requirement: SOFT.md notes exist + agent available + your phone.

### Tier 3 — Mine

No skill exists. Agent calls the **Skill Miner** (`gitd.skills.auto_creator`, BFS state-graph explorer) on the target app. Miner produces a SOFT.md (recorded flow notes) + your first hard-skill.

Cost: tokens for the exploration + one authoring pass.

Requirement: just agent + your phone.

### Meta tier — `skill-creation-guide` skill

A skill in the registry whose SOFT.md teaches any loaded LLM how to be a competent skill author. Loaded as context by tier-2 and tier-3 flows to bootstrap agents that have never authored a skill before. Distributed via the Hub like any other skill.

---

## 4. Primitive catalog

### Step primitives

Atomic device interactions (map 1:1 to MCP tools):

- `tap(x, y)`, `tap_element(id|desc|text|xpath)`
- `type_text(text)`, `long_press(x, y, duration_ms)`, `swipe(x1, y1, x2, y2, duration_ms)`
- `press_key(HOME | BACK | ENTER | ...)`
- `launch_app(package)`, `open_url(url)`

Waits + observations:

- `wait_for_text(text, timeout_s)`, `wait_for_element(id|desc, timeout_s)`
- `screenshot()`, `dump_xml()`, `dismiss_popups()`

Composition + control flow:

- `if_visible: {selector, then: [steps], else: [steps]}` — conditional branching
- `retry: {max, backoff_s, on_failure: <action>}` — flake resilience wrapper
- `run_skill: {name, action, params}` — skill composition (call another skill's action)
- `checkpoint: {reason, prompt, success: <validator>, timeout_s}` — HITL/external-code/LLM-decision gate

Escape hatches:

- `python_action: <module>:<function>` — arbitrary Python callable; receives `(device, params, context)`, returns a plain payload dict or `ActionResult`. Dicts containing `success`, `error` or `data` are result envelopes; payload belongs inside `data`, and ignored sibling keys produce a warning. Required for real-world complexity (media prep, custom intents, OCR helpers). See §5 for security model.
- `pre_hooks: [<python_action>]` — pre-flow prep (e.g. transcode video before upload)

### Validator primitives (composable via `all_of` / `any_of` / `not`)

- `text_visible: {text}` — a11y tree contains text
- `element_present: {id | desc | xpath}` — a11y element exists
- `url_contains: {substring}` — for browser/webview
- `pixel_at: {x, y, rgb, tolerance}` — pixel color check on screencap
- `ocr_text_present: {text}` — screencap OCR (RapidOCR) finds text
- `screen_hash: {ref_hash, similarity_min}` — perceptual hash match against reference
- `custom_python: <module>:<function>` — arbitrary Python predicate

Default composition: `end_state_validator:` at action level runs with AND semantics — all listed conditions must pass. Explicit `any_of:` / `not:` blocks override.

---

## 5. Security model for `python_action:`

`python_action:` is unavoidable — the hardest hard-skills (see the reference TT upload) need 2000+ LOC of app-specific glue. But it's a remote-code-execution vector when a user installs someone else's skill.

Four trust tiers:

| Tier | Location | Review | Install UX | Badge |
|---|---|---|---|---|
| **0 — Official** | `skillhub/ghost/*` (official namespace) | Ghost maintainers | Silent | 🟢 OFFICIAL |
| **1 — Community Verified** | `skillhub/<user>/<slug>/` merged via PR | Human review + CI static-analyzer | Short "Community skill by @user" note | 🔵 VERIFIED |
| **2 — Community Unverified** | `ghost skill install <arbitrary-github-url>` | None | Loud prompt: "Contains Python. Review at `<url>` first. Continue? (y/N)". Requires `--yes-python` to auto-skip | 🟡 UNVERIFIED |
| **3 — Quarantined** | Registry flag `quarantined: true` | Was reviewed + rejected as malicious/abusive | Install blocked. `--force` overrides | 🔴 QUARANTINED |

CI static-analyzer flags on ALL community submissions:
- `os.system`, `subprocess.*shell=True*`, `exec/eval`, `__import__`
- Network calls not routed through `gitd.http` helpers
- Filesystem writes outside the skill's own directory
- Suspicious binary blobs or obfuscated strings

Flag = extra reviewer attention required, does not auto-reject.

**"Use at your own risk"** applies to Tier 2 — the loud install prompt is the informed-consent gate.

---

## 6. LLM emission guide — writing skills from a trace

The schema is designed so an agent that just drove the phone can dump its own tool-call trace and get a valid skill YAML back with minimal transformation.

### Trace → YAML mapping

Given the LLM's execution trace:

```
tap_element(id="search")
type_text(text="alice")
tap_element(id="search_button")
wait_for_text(text="Results")
tap_element(text="Alice Smith")
type_text(text="hey are you free")
tap_element(desc="Send button")
```

The equivalent skill action:

```yaml
actions:
  - name: send_msg
    ref_prompt: "Send hey to Alice on WhatsApp"
    params: [contact_name, message]
    steps:
      - {action: tap_element, id: search}
      - {action: type_text, text: "{contact_name}"}
      - {action: tap_element, id: search_button}
      - {action: wait_for_text, text: Results}
      - {action: tap_element, text: "{contact_name}"}
      - {action: type_text, text: "{message}"}
      - {action: tap_element, desc: Send button}
    end_state_validator:
      all_of:
        - {kind: text_visible, text: "{message}"}
        - {kind: element_present, desc: message_sent_check}
```

Rules for the emitting agent:
1. **Every tool call becomes a step** — copy the tool name as `action:`, args as sibling keys
2. **Parameterize repeated values** — the same string typed as a search + the same string tapped in results is likely `{contact_name}`; extract to `params:`
3. **Emit an `end_state_validator`** by observing the terminal screen: 2-3 things you can assert (text visible, checkmark shown, URL contains)
4. **Emit a `ref_prompt`** — the natural-language phrase you were given (or a paraphrase) that triggered this trace
5. **If you were forced to make a decision mid-trace based on novel screen content**, wrap that step as a `checkpoint: {reason: llm_decision, ...}` — declares a gate, warns future replay
6. **If you invoked a helper that isn't in the atomic set** (custom video prep, OCR read), emit `python_action: <module>:<func>` and ship the helper alongside — declares this skill contains custom Python (raises trust badge to VERIFIED-or-lower)

The **`skill-creation-guide` skill** (meta tier, distributed via the Hub) packages this doc + worked examples so any competent LLM can be handed a trace + this guide and produce a valid submission-ready skill dir.

---

## 7. What's next

See:

- `docs/skill-schema-v2.md` — full yaml spec with every field, defaults, examples
- `docs/contributing-skills.md` — PR-submit flow, folder structure, `ghost skill scaffold/validate/test/submit` CLI walkthrough
