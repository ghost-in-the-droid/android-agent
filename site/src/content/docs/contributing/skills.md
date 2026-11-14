---
title: "🧩 Contributing Skills"
description: How to contribute a skill to Ghost. TL;DR — scaffold, edit, validate, test, submit as PR. Full flow at /skills/publishing/.
---

**Adding skills for real apps is the highest-impact contribution to Ghost.**

Every new skill turns your one-time authoring effort into infinite $0-per-invocation replays for everyone else on your fingerprint. Skills compound the ecosystem's value.

---

## Quick start

```bash
pip install ghost-in-the-droid>=1.6.0

ghost skill scaffold alice/whatsapp-messaging \
    --app com.whatsapp \
    --actions send_msg,check_inbox

# ... edit skillhub/alice/whatsapp-messaging/skill.yaml + helpers.py ...

ghost skill validate skillhub/alice/whatsapp-messaging
ghost skill test skillhub/alice/whatsapp-messaging --live --device asus
ghost skill submit skillhub/alice/whatsapp-messaging
```

For the full walkthrough see:

- [Creating Skills](/skills/creating-skills/) — step-by-step author flow
- [Publishing Skills](/skills/publishing/) — PR submit flow + review process
- [Skill Hub](/features/skill-hub/) — trust tiers + registry model
- [Skill Schema v2 Reference](/api/skill-classes/) — every YAML field

---

## Contribution types (impact-ordered)

| Type | Difficulty | Impact | Notes |
|---|---|---|---|
| **New skill for a top mainstream app** | Med-Hard | Very High | WhatsApp, Google Maps, Spotify, Instagram, Uber... |
| **New action on an existing skill** | Easy | High | e.g. `reply_last` on `alice/whatsapp-messaging` |
| **Alternate skill for a different fingerprint** | Medium | High | Pixel 10 variant of a Samsung S24 skill |
| **Bench trace on a shipped skill** | Easy | Medium | Real with-vs-without-skill numbers on your brain |
| **Docs improvement** | Easy | Medium | Correct/expand these very pages |
| **Static analyzer signature** | Medium | High | Catch new Python patterns worth flagging in CI |

---

## What you can and cannot ship

**Yes, allowed**:
- Skills for any app you can install
- Actions on your own account (nav, read your own data, upload your own content)
- Custom `python_action:` targets — the escape hatch is unavoidable for real complexity, trust tier handles it
- Gated skills with a human captcha checkpoint
- Skills that require paid API credentials (declare in `data_access:`)

**No, will be rejected**:
- Skills that violate the target app's ToS at scale (mass outreach, mass scraping, spam)
- Skills that automate engagement to game platform metrics (mass-like, mass-follow, view farms)
- Skills that scrape other users' private data
- Skills that impersonate specific users
- Skills that bypass anti-abuse mechanisms (captcha solvers, phone-number spoofers)
- Malicious code — obfuscated python, credential exfiltration, network calls to unknown hosts

The line: **can a user reasonably run this themselves without violating the app's Acceptable Use?** If yes → probably fine. If no → premium-only or don't ship.

---

## First-time contributor checklist

Before submitting:

- [ ] `ghost skill validate <path>` returns 0
- [ ] `ghost skill test <path> --live` passes for at least one action
- [ ] `README.md` explains what the skill does + shows the WebM recorded with `ghost skill demo`
- [ ] `SOFT.md` has semantic-level narrative for each action (LLM will read this for adapt-mode)
- [ ] `ref_prompt` on every action is a real natural-language phrase (not "TODO")
- [ ] `test_case.ref_prompt_variants` are actual variants, not duplicates
- [ ] `data_access:` honestly declared
- [ ] `popup_detectors:` include the popups you encountered during testing
- [ ] `python_action:` targets scoped — no `os.system`, no writes outside skill dir, no network outside `gitd.http`
- [ ] Fingerprint matches what you actually tested against (don't wildcard `hardware:` if you only tested one device)

---

## Getting help

- **Discord**: [join our server](https://discord.gg/gmvDX4Juk) to share what you build and get help
- **GitHub Issues**: use the `skill-question` label
- **`ghost doctor`**: diagnoses local skill-authoring environment
- **[Publishing Skills](/skills/publishing/)** — canonical reference for the flow

## Record the hub demo

Use `ghost skill demo` to make the hub video with the original Ghost showcase
recorder: asciinema terminal on the left, live phone in its device frame on the right.

```bash
ghost skill demo <author>/<skill> <action> --mode hard --device <device> --render-host <render-host>
# Reference notes followed by a real Claude Code session:
ghost skill demo <author>/<skill> <action> --mode soft --device <device> --render-host <render-host> --max-tokens 12000
```

The recorder clears only the installed non-system demo app, seeds its sample data,
returns HOME, starts capture and launches the app. Use a disposable demo app state.
System apps are refused. Configure app-scoped seed broadcasts and all card text in
`--spec spec.yaml`; card flags override the spec. `--dry` prints the plan without
recording; `--trim-idle` removes static time from both panes together after composition.
Soft mode uses the Haiku model alias and stops at its transcript token budget;
a response already in flight may cross the threshold. Its output tokens are also bounded.

Output is `demos/<action>.webm` plus its `.spec.yaml` (first action also updates
`demo.webm`). The VP9 WebM is silent, at most 30 seconds and 3 MB, and goes through
terminal and OCR privacy scans before publication to the local output path.
Open this WebM in [Validate](/skills/validate/) to check it locally, then include
it in the hub submission. See the repository's `docs/DEMO_RECORDING.md` for the
full spec and the original `scripts/record_showcase_reel.py` grid reel workflow.

HARD means deterministic `run_skill` replay. SOFT means `SOFT.md` reference notes
read with `get_skill_notes`. A human captcha is a GATE, not a soft skill.
