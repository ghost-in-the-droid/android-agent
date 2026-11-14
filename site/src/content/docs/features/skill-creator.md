---
title: "🛠️ Skill Creator (Miner)"
description: The BFS state-graph explorer that turns an LLM's trace of driving your phone into a v2 skill.yaml, or bootstraps a brand-new skill from an unknown app.
---

The **Skill Creator** — internally `gitd/skills/auto_creator.py`, sometimes called the **Skill Miner** — is Ghost's mechanism for producing skills automatically from an LLM's exploration of an app.

> **Planned feature.** `ghost skill mine` is not implemented in v1.6.0; `gitd/skills/auto_creator.py` is a BFS state explorer with no LLM calls and no v2 output. This page describes the design. Until it ships, author skills by hand or import them (see [Creating Skills](/skills/creating-skills/)).

It is designed to solve the Tier 2 (Adapt) + Tier 3 (Mine) cases of the [Skills acquisition model](/skills/overview/#three-acquisition-tiers): when a skill doesn't exactly match your device, or when no skill exists at all, an agent runs the miner and emits a fresh v2 skill.

---

## The pattern

```
Agent drives phone
    │
    ▼
Every tool call → recorded in a trace
    │
    ▼
Trace → Skill Miner
    │  BFS: discovers screen states, deduplicates, extracts stable locators
    ▼
Emits: skill.yaml (v2) + helpers.py + SOFT.md skeleton
    │
    ▼
Agent lightly polishes (or you tweak)
    │
    ▼
ghost skill validate + test + submit
```

**Key insight**: Schema v2 was designed to be near-1:1 with an LLM's tool-call output. Every step primitive matches an MCP tool name (`tap_element`, `type_text`, `wait_for_text`, `launch_intent`). Selectors mirror tool-call args. Validators can be inferred from the observed terminal screen ("agent saw text X → emit `text_visible: {text: X}`").

---

## Two invocation modes

### Mine a specific action

```bash
ghost skill mine skillhub/alice/whatsapp-messaging \
    --action send_msg \
    --ref-prompt "Text John Smith saying I'll be late"
```

Runs the agent with the given ref_prompt, records the trace, appends the action to the skill's `actions[]` list. Existing actions untouched.

### Mine from scratch

```bash
ghost skill mine skillhub/alice/whatsapp-full \
    --app com.whatsapp \
    --explore
```

BFS-explore the app from launch, discover ~20-40 screens, propose actions the LLM can articulate (from screen affordances). Emits a starter skill.yaml with candidate actions the author refines.

---

## Under the hood

The miner does three things:

**1. Trace capture**
- Runs the agent against the target app
- Records every tool call (name, args, result)
- Records every screen dump (a11y XML) + screenshot
- Records validator observations at each step

**2. State-graph analysis**
- Deduplicates screens by content-hash (skip similar states)
- Extracts stable locators per element (prefers content-desc > resource-id > text > coord)
- Detects popups (transient modals) vs. screens (persistent state)
- Maps ref_prompt → step sequence

**3. YAML emission**
- Steps become `- {action: <tool_name>, ...args}` entries
- Parameters extracted from repeated string values ({contact_name} substitution)
- Popup detectors emitted from transient-modal patterns
- `end_state_validator` drafted from 2-3 terminal-screen affordances
- `ref_prompt` = the original user request or a paraphrase

---

## Trace→YAML mapping (rules)

For any LLM agent that just drove your phone, the Skill Miner (or the LLM directly) can follow these rules to emit valid v2 yaml:

1. **Every tool call becomes a step** — copy the tool name as `action:`, args as sibling keys
2. **Parameterize repeated values** — same string typed as search + same string tapped in results is likely `{contact_name}` → extract to `params:`
3. **Emit an `end_state_validator`** by observing the terminal screen — 2-3 things you can assert (text visible, checkmark shown, URL contains)
4. **Emit a `ref_prompt`** — the natural-language phrase the user gave (or a paraphrase)
5. **Decision mid-trace on novel content** → wrap as `checkpoint: {reason: llm_decision, ...}` — declares the flow soft, warns future replay
6. **Custom helper invoked** (not in atomic set) → emit `python_action: <module>:<func>` + ship helper alongside → raises trust badge to `has_python: true`

Ghost ships a `skill-creation-guide` skill (meta-tier) that packages these rules + worked examples so any competent LLM can be handed a trace + this guide and produce a submission-ready skill dir.

---

## Popup catalog growth (--update-popups)

```bash
ghost skill mine ghost/tiktok --update-popups
```

Post-processes recent `runs/<id>/unknown-popup-*.png` artifacts (from Layer 4 safety-net captures) into detector proposals. OCR each screenshot, propose a `{detect, button, label}` entry, ask the author to confirm.

Empirical grow-your-catalog workflow — replaces manual popup discovery.

---

## Adapt (Tier 2)

When a skill's fingerprint doesn't exactly match your device (e.g. your Pixel 10 vs. author's Samsung S24), the engine calls the miner in **adapt mode**:

1. Loads the existing hard-skill(s) with nearest fingerprint(s) as concrete reference
2. Loads the skill's `SOFT.md` as semantic narrative
3. LLM re-mines the flow on YOUR device
4. Emits a new hard-skill for YOUR fingerprint (stored locally, optionally submitted back to community)

Adapt-mode uses fewer tokens than mine-mode because it has the reference structure — LLM only re-verifies + re-emits the drift.

Distance-based cutoff (designed, not yet in the engine): 0 → Hit, 1-2 → warn + try, 3+ → Adapt automatically.

---

## Other starting points: import and migrate

Mining is not the only way to get a first draft. Two commands turn existing automation into a v2 skill without any LLM tokens:

```bash
ghost skill import --maestro login_flow.yaml --out skillhub/<you>/my-app
ghost skill import --automate my_flow.flo   --out skillhub/<you>/my-app
ghost skill migrate skillhub/<you>/old-v1-skill [--dry-run]
```

- **`import`** reads a Maestro YAML flow or an Automate flow export and writes a skill folder: `skill.yaml` with one action per flow, a `helpers.py` stub, `README.md`, `SOFT.md`, and the original source kept next to them. Steps that map one to one become v2 steps; anything else stays as a TODO step for you to finish. If the flow does not end on a wait the importer can turn into a validator, the action gets a TODO end-state validator. `generated_with:` records the importer, and a multi-app source must be split into one skill per app. Native binary Automate `.flo` files are kept verbatim with a TODO placeholder; nothing in them is executed or decoded.
- **`migrate`** wraps an older v1 skill (Python `actions/` and `workflows/` classes, a recorded flow, or a FLOW.md-only soft skill) as Schema v2 in place. v1 files stay, so the old runtime keeps working.

Either way, review the result before replaying it: fill the TODOs, check the fingerprint and `data_access`, then run `ghost skill lint` and `ghost skill test --live`.

---

## Related

- [Skill System](/features/skill-system/) — how the emitted skills execute
- [Creating Skills](/skills/creating-skills/) — author flow (mine as one option)
- [What Are Skills?](/skills/overview/) — the 3-tier acquisition model
- [Execution Engine](/features/skill-execution-engine/) — runtime that consumes the emitted skills

## Skill Creator agent guide

The companion agent skill is `skillhub/_guides/skill-creation-guide/SKILL.md`
(`ghost-skill-creation-guide`). Use it to turn explored actions or a trace into a
versioned hub skill: scaffold, author steps and validators, write SOFT.md notes,
validate, lint, analyze, run with signed evidence, record with `ghost skill demo`,
then prepare `ghost skill submit`. Push and publish only when the user requests it.
HARD is deterministic replay; SOFT is reference notes read through get_skill_notes;
a captcha is a GATE. The general `ghost` guide handles everyday phone tasks.
