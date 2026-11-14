# The Ghost Skill Hub contributor ladder

You do not have to write a skill to matter here. Phone automation breaks on devices nobody tested, and the person who owns an odd Xiaomi or a three-year-old Samsung is as valuable as the person who wrote the skill. So there are four ways to climb, and you can climb any of them.

## Two ladders, not one

- **Skills** have a quality tier: Draft, Runs, Proven, Hardened, Reference. It answers "does this work, and has anyone besides the author proved it?"
- **People** have a contributor tier: Novice, Contributor, Expert, Master, Grandmaster. It answers "what has this person done for the hub?"

Your skills climbing earns you medals on the Author track. Everything else earns medals on the other three tracks.

A skill's quality tier is separate from its trust badge (Official, Verified, Unverified, Quarantined), which is about who published it and whether it passed review and scanning. "Proven" is the quality tier; "Verified" on a trust badge means the publisher passed review.

## The four tracks

| Track | You earn a medal when | Bronze | Silver | Gold |
|---|---|---|---|---|
| **Author** | a skill you own reaches a tier | it reaches Runs | it reaches Proven | it reaches Hardened (Reference adds a ribbon) |
| **Verifier** | your independent run on someone else's skill is accepted | a run on any skill (once per skill per device class) | the first run of that skill on a new device class or model | you re-verified a Stale skill, or your run caught a regression that was confirmed |
| **Reviewer** | a curator accepts your review work | a bug report with a run artifact that reproduces it | a docs or validator PR to someone else's skill | a confirmed safety finding, or a completed Reference review |
| **Helper** | someone marks your answer helpful | 2 helpful answers | 5 | 10, with the asker at Contributor or above |

Helpful votes from Novice accounts do not count toward Helper medals. That keeps the track about real help.

## The tiers

You hold the highest tier you have reached on any track. If you reach the same tier on more than one track, your profile shows it, for example "Master x2".

| Tier | How you get there |
|---|---|
| **Novice** | Sign in. Welcome. |
| **Contributor** | Confirmed email, one device enrolled, and any one of: a skill at Runs, 3 Verifier bronzes, 2 Reviewer bronzes, or 5 Helper bronzes. Most people get here in one evening. |
| **Expert** | Author: 2 silvers. Verifier: 10 bronzes across 5+ different skills. Reviewer: 5 bronzes. Helper: 50 bronzes. |
| **Master** | Author: 1 gold and 2 silvers. Verifier: 3 golds and 20 silvers across 3+ phone makers. Reviewer: 2 golds and 10 silvers. Helper: 50 silvers. |
| **Grandmaster** | Author: 3 golds including one Reference skill. Verifier: 10 golds. Reviewer: 10 golds. Helper: 50 golds. |

Thresholds are tuned each season so Master stays around 1% of active members and Grandmaster around 0.1%. Changes are announced 30 days before a season starts and never apply backwards.

**Your tier never decays.** Once you are Expert, you are Expert. What does fade is the **Active** ring on your avatar, which shows activity in the last 90 days, and the default leaderboard, which is 90-day rolling. The all-time board is one click away. There are no daily streaks. Take weekends off.

## How a skill climbs

| Tier | What it takes |
|---|---|
| **Draft** | `skill.yaml` validates and the security scan is clean. |
| **Runs** | A README and one signed self-run (`ghost skill run ... --record`). |
| **Proven** | Someone else ran it on a different device and it passed, plus a demo clip (30 s max) and at least 3 step-level validators. |
| **Hardened** | Passes on 2+ phone makers or Android versions, benchmarked on 2+ models, 10+ community runs with a high confidence success rate, a "Known failure modes" section, and re-verified in the last 90 days. |
| **Reference** | Hardened for 60+ days, reviewed by the curator board, no open serious bug older than 14 days, and the author is at Contributor or above. Only about 5% of Hardened skills per category. |

Scores run from 0 to 100. Each tier needs both the evidence above and a points floor: Runs 10, Proven 35, Hardened 65, Reference 90. Points come from five categories, each capped so no single source can carry a skill:

| Category | Up to |
|---|---|
| Docs and packaging | 15 |
| Your own runs, validators and benchmarks | 15 |
| Other people's runs on other devices | 40 |
| Community runs over the last 90 days (once there are 10 or more) | 20 |
| Maintenance: re-verified in the last 30 days (6), bug reports answered within 7 days (2 each, up to 4) | 10 |

The full formula is public on the scoring page; the numbers come from `skillhub/scoring/v1.json`.

Skills go **Stale** when nobody has re-verified them in 90 days. If a run fails on a newer app version than the last pass, the skill's tier freezes within 24 hours until a pass arrives. That is where Verifiers shine: re-verifying a Stale skill is a gold.

## Your first evening

1. Join Discord and read #start-here.
2. Pick one skill from #verify-requests that targets an app you already have.
3. Run `ghost skill verify <author>/<slug>`. It records your signed run and prints the PR it would open; add `--push` to open the PR for you.
4. That accepted run is your first Verifier bronze. Two more and, with a confirmed email and enrolled device, you are a Contributor.

Prefer writing? Pick a `first-timers-only` issue. Each one has a mentor who has promised to answer within 48 hours.

## Founding Contributors

The first 100 people to reach Contributor after launch get a numbered Founding Contributor badge, #1 to #100. It is never issued again. Details: `docs/community/badges.md`.

## What does not count

- Downloads, likes and stars. They are shown, and they are worth zero points. They are the easiest numbers to fake anywhere.
- Running your own skill as "independent". Self-runs never count.
- Several accounts on one phone. One device fingerprint counts once.
- Trading verifications. Two accounts that keep verifying only each other stop counting for each other after the third pair in 30 days.
- Buying a tier. Points come only from signed run evidence.
- Undisclosed AI generation. Using AI is fine and common. Say so in `generated_with:`. Hiding it means a 30-day points freeze.

## Seasons, awards and the curator board

- A season is about 90 days. At the end we publish how many medals of each kind were earned and how many gaming cases were removed.
- Every month maintainers pick a Skill of the Month, a Verifier of the Month and a First-Timer of the Month. Each gets a permanent page.
- Each season, Masters and above on the Reviewer or Verifier tracks can stand for the 10-seat curator board. Curators are the only people who can grant Reference tier.
