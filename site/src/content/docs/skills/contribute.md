---
title: "🏅 Contribute to the Skill Hub"
description: Four ways to climb, from your first verified run to Grandmaster. Write skills, verify them on your phones, review, or help others. Downloads are worth zero; evidence is everything.
---

**You do not have to write a skill to matter here.**

Phone automation breaks on devices nobody tested. The person who owns an unusual phone and runs other people's skills on it is as valuable as the person who wrote them. So the Skill Hub has four tracks, and you can climb any of them.

---

## Your first 10 minutes

```bash
pip install ghost-in-the-droid   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill doctor                      # adb, phone, gh: all green?
ghost skill verify <author>/<slug>          # run someone else's skill; preview the PR
ghost skill verify <author>/<slug> --push   # same, and open the PR
```

`verify` runs the skill and records a signed result; `--push` opens the pull request for you. Pass or fail, it counts. Before your first `--push`, add `~/.ghost/run-signing-key.pub` (created on your first run) to your GitHub SSH keys, because CI checks the signature against them. Pick a skill from the open [verify requests](https://github.com/ghost-in-the-droid/android-agent/issues?q=is%3Aopen+label%3Averify-request) that targets an app you already have.

That accepted run is your first Verifier medal.

Or ask in #verify-requests on [Discord](https://discord.gg/gmvDX4Juk).

---

## Two ladders

| | Ladder | Question it answers |
|---|---|---|
| **Skills** | Draft, Runs, Proven, Hardened, Reference | Does it work, and has anyone besides the author proved it? |
| **People** | Novice, Contributor, Expert, Master, Grandmaster | What has this person done for the hub? |

A skill's quality tier is separate from its trust badge (Official, Verified, Unverified, Quarantined), which says who published it and whether it passed review. Proven is about the skill working; the Verified trust badge is about the publisher.

---

## How a skill climbs

| Tier | What it takes |
|---|---|
| **Draft** | `skill.yaml` validates and the security scan is clean |
| **Runs** | A README and one signed self-run (`ghost skill run ... --record`) |
| **Proven** | Your own signed passing run on every action, a demo clip (30 s max), 3+ step-level validators on every action and 35 points: reachable on your own evidence |
| **Hardened** | Someone else ran it on a different device and it passed, passes on 2+ phone makers or Android versions, benchmarked on 2+ models, 10+ community runs with a high-confidence success rate, a "Known failure modes" section, re-verified in the last 90 days |
| **Reference** | Hardened for 60+ days, curator reviewed, no serious bug open longer than 14 days. About 5% of Hardened skills per category |

Scores run from 0 to 100. Each tier needs both the evidence and a points floor: Runs 10, Proven 35, Hardened 60, Reference 90. Points come from five categories, each capped so no single source can carry a skill:

| Category | Up to |
|---|---|
| Docs and packaging | 20 |
| Your own runs, validators and benchmarks | 30 |
| Other people's runs on other devices | 30 |
| Community runs over the last 90 days (once there are 10 or more) | 10 |
| Maintenance: re-verified in the last 30 days (6), bug reports answered within 7 days (2 each, up to 4) | 10 |

The numbers come from `skillhub/scoring/v1.json`, and the full formula is on the [scoring page](/skills/scoring/).

**Downloads and likes are shown and worth zero points.** They are the easiest numbers to fake on every hub we studied.

A skill nobody has re-verified for 90 days goes **Stale**. If a run fails on a newer app version than the last pass, the tier freezes within a day until someone proves it works again.

---

## Four tracks for people

| Track | You earn a medal when | Bronze | Silver | Gold |
|---|---|---|---|---|
| **Author** | A skill you own reaches a tier | Runs | Proven | Hardened (Reference adds a ribbon) |
| **Verifier** | Your run on someone else's skill is accepted | Any skill, once per skill per device class | First run on a new device class or model | Re-verified a Stale skill, or caught a confirmed regression |
| **Reviewer** | A curator accepts your review work | Bug report with a reproducing run | Docs or validator PR to someone else's skill | Confirmed safety finding, or a Reference review |
| **Helper** | Your answer is marked helpful | 2 answers | 5 | 10, asker at Contributor or above |

### Tiers

| Tier | How you get there |
|---|---|
| **Novice** | Sign in |
| **Contributor** | Confirmed email + one enrolled device + any one of: a skill at Runs, 3 Verifier bronzes, 2 Reviewer bronzes, 5 Helper bronzes. One evening for most people |
| **Expert** | Author: 2 silvers. Verifier: 10 bronzes across 5+ skills. Reviewer: 5 bronzes. Helper: 50 bronzes |
| **Master** | Author: 1 gold + 2 silvers. Verifier: 3 golds + 20 silvers across 3+ phone makers. Reviewer: 2 golds + 10 silvers. Helper: 50 silvers |
| **Grandmaster** | Author: 3 golds incl. 1 Reference. Verifier: 10 golds. Reviewer: 10 golds. Helper: 50 golds |

**Tiers never decay.** The leaderboard defaults to the last 90 days, with all-time one click away, and an Active ring on your avatar shows recent activity. There are no daily streaks.

The first 100 people to reach Contributor after launch get a numbered **Founding Contributor** badge. It is never issued again.

---

## Write a skill

```bash
ghost skill scaffold <your-github-login>/<slug> --app <package> --actions <action>
# author skill.yaml, README.md, SOFT.md; set license: and generated_with:
ghost skill validate <path>
ghost skill lint <path>
ghost skill run <path> <action> --record     # signed self-run: your skill reaches Runs on merge
ghost skill submit <path> --push             # forks, pushes, opens the PR (plan only without --push)
```

Then open a **Verify request** issue so someone with a different phone can verify it: independent runs are worth up to 30 points and the first gate of Hardened.

Full walkthroughs: [Creating Skills](/skills/creating-skills/) and [Publishing Skills](/skills/publishing/). Field reference: [Skill Schema v2](/api/skill-classes/).

**Not sure what to build?** The [wanted skills](https://github.com/ghost-in-the-droid/android-agent/issues?q=is%3Aopen+label%3Awanted-skill) list has one useful action for each of 20 of the most-installed apps. Issues labelled [`first-timers-only`](https://github.com/ghost-in-the-droid/android-agent/issues?q=is%3Aopen+label%3Afirst-timers-only) are reserved for people who have never had a skill merged, and each has a named mentor who answers within 48 hours.

AI-assisted skills are welcome. Say so in `generated_with:`.

---

## What you can and cannot ship

**Allowed:**
- Skills for any app you can install
- Actions on your own account: navigate, read your own data, post your own content
- Custom `python_action:` helpers: a maintainer reads them before CI runs the skill (see Security below)
- Soft skills with a human checkpoint (captcha, confirmation)
- Skills that need paid API credentials, declared in `data_access:`
- Destructive actions, if they have a `confirm_before:` step and `destructive: true`

**Rejected:**
- Engagement farming: mass-like, mass-follow, view farms
- Mass messaging, mass scraping, spam
- Scraping other people's private data or impersonating anyone
- Bypassing anti-abuse systems (captcha solvers, number spoofers)
- Obfuscated Python, credential exfiltration, network calls to unknown hosts

The line: **could a person reasonably do this by hand on their own account without breaking the app's terms?** If yes, it is probably fine.

---

## Security: what CI will run

The tiers decide what CI runs on its own, not what the hub accepts. Most of it is enforced; APK sources and automatic rejection are still planned, and the [security policy](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/skillhub/security.md) marks exactly what is enforced today. Every community skill PR lands in one of three:

| Tier | When | What happens |
|---|---|---|
| **1. Auto-run** | YAML-only hard skill, and the app is on F-Droid, on the trusted-vendor list, or from a vendor GitHub repo with 1000+ stars and releases | CI runs your skill on an emulator (today: apps on the stock emulator image) |
| **2. Manual review** | Your skill has its own Python (`helpers.py`, `python_action`), or the app is not covered by any of those | A maintainer reads the Python and checks the app; for an uncovered app, give an allowed APK source and its sha256. The emulator run waits for the `approved:<full sha>` label |
| **3. Rejected** | Network calls from skill code, anything touching secrets, an arbitrary APK URL, or obfuscated code | The PR is rejected (today by the reviewer; automatic rejection is planned) |

When CI starts installing APKs, they will only come from F-Droid, a vendor's own download page, or a maintainer-approved private cache, each pinned by sha256; APKMirror, APKPure and links in a PR are never used. PR checks run on throwaway GitHub-hosted runners with no secrets and a read-only token. To get an app's package prefix trusted, open a PR that only edits `skillhub/trusted-vendors.yml`. Full policy: [`docs/skillhub/security.md`](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/skillhub/security.md).

---

## Fair play

- Self-runs never count as independent verification.
- One device counts once, however many accounts use it.
- Two accounts that keep verifying only each other stop counting for each other after the third pair in 30 days.
- Accounts younger than 14 days have their verification runs held until they mature. Nothing is lost.
- Undisclosed AI generation means a 30-day points freeze.
- Scoring changes only between seasons, with 30 days notice, never backwards.

At the end of each season we publish how many medals of each kind were earned and how many gaming cases were removed.

---

## Getting help

- **GitHub Issues**: label `skill-question`
- **`ghost skill doctor`**: checks your local setup
- **[Creating Skills](/skills/creating-skills/)**: the canonical author guide
