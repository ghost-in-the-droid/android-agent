---
title: "🧩 What Are Skills?"
description: Skills are named, versioned bundles of Actions that let any AI agent operate a real phone at $0/call after a one-time authoring pass. Reusable, replayable, community-contributable.
---

**Skills cost $0. Thinking costs tokens.**

A **Skill** is a named, versioned bundle of **Actions** for a specific app on a specific device fingerprint. Each Action is what an agent invokes: `send_message`, `check_inbox`, `upload_video`, `switch_account`.

Once authored, a Skill replays deterministically at zero LLM cost. That's the whole point.

---

## The vocabulary

| Term | What it is |
|---|---|
| **Skill** | A named package, e.g. `ghost/tiktok` or `alice/whatsapp-messaging`. Lives at `skillhub/ghost/<slug>/` (official) or `skillhub/<user>/<slug>/` (contributed). |
| **Action** | A first-class agent-invocable capability of a skill, e.g. `send_message(contact, text)`. Has `ref_prompt`, typed `params`, `steps`, and an `end_state_validator`. |
| **Subroutine** | Internal reusable step-list within a skill (e.g. `nav_to_profile_tab`). Not agent-invocable; a de-dup primitive so 10 actions don't all repeat the same 5-step boilerplate. |
| **Step** | An atomic operation: `tap_element`, `type_text`, `wait_for_element`, `launch_intent`, `python_action`, `if_visible`, `retry`, `checkpoint`, and more (21 types). Steps compose actions. |
| **Validator** | A predicate on the terminal screen: `text_visible`, `element_present`, `pixel_at`, `ocr_text_present`, `custom_python`, composable via `all_of` / `any_of` / `not`. |
| **Fingerprint** | (OS × OS-version × hardware × app-package × app-version) that a skill is tested against, plus optional `screen_wxh`, `density`, `locale`, `theme`. Determines Hit vs Adapt vs Mine (v1.6.0 runs skills as authored and records the fingerprint; distance matching is v1.7, Adapt and Mine are planned). |
| **Status** | `active`, `blocked` or `deprecated`. A blocked skill cannot complete on its own today (for example a mandatory phone check). |

---

## Hard vs Soft skills

Every skill has two layers: an exact route to replay, and a plain-language guide for when that route does not fit your phone.

### Hard skill

Deterministic replay:
- **Zero LLM calls** at replay time
- **Zero human intervention**
- Every step resolves via a stable locator (id, desc, text) or a `python_action:` callable
- Failure retries then aborts. No branching on unknown content.

**Examples**: `ghost/google_maps`, `ghost/tiktok` `upload_video`, `ghost/send_gmail_email`.

**Guarantee**: same input, same steps, same terminal screen.

### Soft skill

Every skill also ships a `SOFT.md`: a plain-language guide to the task. What it does, which screens to expect, where the popups and traps are.

Use it when no hard skill matches your phone, Android version or app version:
1. Your agent reads `SOFT.md` and drives the app by hand. This costs tokens, like any agent run.
2. Once it has found the route, it writes it down as a new hard skill for your setup (see the [Skill Creation Guide](/skills/skill-creation-guide/)).
3. From then on, the action replays as a hard skill: no LLM calls.

A soft skill is the fallback and the starting point for a hard skill, not a token saver on its own.

**Guarantee**: best effort. The agent decides each step, so results depend on the model.

### Skills that pause for a human

Some steps should not be automated: a captcha, a login, an SMS or email code, a confirmation before a destructive action. A skill can pause there with a `checkpoint` and resume once a human is done, or when its `success:` validator passes. See [Human in the Loop](/guides/human-in-the-loop/).

Every skill, hard or soft, can run in **dry mode** with no device: checkpoints resolve immediately and other steps are listed as skipped. Useful for CI and for checking a skill's structure.

---

## Three acquisition tiers

When an agent needs to do action X in app Y on YOUR device:

### 1. Hit: install a matching hard-skill ($0)

Skill fingerprint matches your device. Engine replays deterministically. **This is the ideal.**

### 2. Adapt: soft-skill or nearest hard-skill (tokens once, then $0)

Nothing exactly matches your fingerprint, but a soft-skill (or a hard-skill for a similar fingerprint) exists. The engine hands the LLM the skill's `SOFT.md` narrative and the closest hard-skills as reference; the agent re-mines the flow for your device.

### 3. Mine: no skill exists (tokens)

The agent explores the app and authors a first skill from scratch. The `ghost skill mine` command that automates this is planned; today you drive the agent yourself, or import a flow from Maestro or Automate (see [Creating Skills](/skills/creating-skills/)).

---

## Two badges: trust and quality

Every skill on the hub carries two separate badges.

**Trust** says who published it and whether it went through review:

| Trust | Where | Install prompt |
|---|---|---|
| 🟢 **Official** | `skillhub/ghost/*` | Silent |
| 🔵 **Verified** | `skillhub/<user>/<slug>/`, merged through the PR flow | "Installing verified community skill by @user" |
| 🟡 **Unverified** | `ghost skill install <ref> --url <git-url>` outside the hub repo | Warning, then y/N (or `--yes`) |
| 🔴 **Quarantined** | Flagged by maintainers | Blocked; `--force` overrides with a warning |

Trust exists because skills can contain executable Python (`python_action:` targets), and every listed skill's Python is statically scanned in CI.

**Quality** says whether the skill works, proven by signed runs on real devices:

| Quality tier | What it takes |
|---|---|
| **Draft** | Validates, security scan clean |
| **Runs** | README + one signed self-run by the author |
| **Proven** | Someone else ran it on a different device and it passed, plus a demo clip and 3 validator units on every action |
| **Hardened** | Several phone makers and models, 10+ community runs with a high success rate, re-verified in the last 90 days |
| **Reference** | Curator reviewed, the best ~5% of Hardened skills |

Downloads and likes are shown and worth zero points. The formula is public on the [scoring page](/skills/scoring/). A freshly merged community skill is trust **Verified** and quality **Draft** or **Runs**; it becomes **Proven** only when someone else runs it.

---

## What you actually do

**As an agent using skills:**

```bash
ghost skill install ghost/tiktok
ghost skill run ghost/tiktok get_active_account --device <serial>
# → {"handle": "<your_handle>"}
```

**As a skill author:**

```bash
ghost skill scaffold alice/whatsapp-messaging --app com.whatsapp --actions send_msg,check_inbox
# ... edit skill.yaml + helpers.py ...
ghost skill validate skillhub/alice/whatsapp-messaging
ghost skill run skillhub/alice/whatsapp-messaging send_msg --param contact_name=Me --param message=hi --record --device <serial>
ghost skill submit skillhub/alice/whatsapp-messaging
```

**As a verifier:** run someone else's skill on your phone with `ghost skill verify <author>/<slug>`. That is how skills reach Proven, and it does not require writing a skill. See [Contribute](/skills/contribute/).

---

## Next

- [Using Skills](/skills/using-skills/): install, run, record, telemetry
- [Creating Skills](/skills/creating-skills/): scaffold, import, migrate, test
- [Publishing Skills](/skills/publishing/): PR flow, CI, verification
- [Contribute](/skills/contribute/): the contributor ladder
- [Skill System](/features/skill-system/): deeper architectural walkthrough
- [Execution Engine](/features/skill-execution-engine/): primitives, validators, popup handling
- [Skill Hub](/features/skill-hub/): registry and community
