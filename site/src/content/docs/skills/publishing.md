---
title: "📦 Publishing Skills"
description: The community submission flow. Skills are pull requests to ghost-in-the-droid/android-agent under skillhub/<you>/<slug>/, gated by CI, human-reviewed, and proven by independent signed runs.
---

Ghost skills are submitted as **GitHub pull requests** that add or change `skillhub/<your-github-login>/<slug>/`. Your GitHub identity is your author namespace; there is no separate account.

Merging lists the skill on the hub with a **Verified** trust badge. Its **quality tier** (Draft, Runs, Proven, Hardened, Reference) comes from evidence: signed runs by you and by other people.

---

## Prerequisites

- `pip install "ghost-in-the-droid>=1.6.0"` (1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`)
- `gh` CLI installed and authenticated (`gh auth status`)
- A skill you have scaffolded, validated, linted and tested (see [Creating Skills](/skills/creating-skills/))
- `ghost skill doctor` green

---

## Before you open the PR

```bash
ghost skill validate skillhub/alice/whatsapp-messaging     # must pass
ghost skill lint skillhub/alice/whatsapp-messaging         # no errors
ghost skill analyze skillhub/alice/whatsapp-messaging      # no high findings
ghost skill run skillhub/alice/whatsapp-messaging send_msg --record --device <serial>   # commit runs/*.json
```

Then prepare the PR:

```bash
ghost skill submit skillhub/alice/whatsapp-messaging            # prints the plan; changes nothing
ghost skill submit skillhub/alice/whatsapp-messaging --push     # forks, pushes the branch, opens (or updates) the PR
```

The plan is the default (`--dry-run` is accepted and means the same). It prints the title `[skill] alice/whatsapp-messaging v<version>`, the branch `skill/alice-whatsapp-messaging`, the files, and a PR body with actions, fingerprint, data access, whether the skill has Python, bench and demo, plus the contribution checklist. `--push` needs `gh auth login`; it forks the hub repository if you do not own it, commits only that one skill directory on an isolated index on top of the hub's default branch, force-updates `skill/<author>-<slug>` on your fork, and opens the PR (or updates the open one). `--push` and `--dry-run` together are an error.

**Which repository.** The default is `ghost-in-the-droid/android-agent` (`DEFAULT_VERIFY_REPO` in `gitd/skills/engine/submission.py`). Point `submit` and `verify --push` at another hub, for example a private mirror, with `--repo <owner>/<repo>` or the `GHOST_HUB_REPO` environment variable. It must be `<owner>/<repo>`: a URL or a remote name is refused.

**What `submit` refuses, and why.**

| Refused | Why |
|---|---|
| Leftover `TODO` placeholders from the scaffold (exit 1, unless `status: draft`) | A reviewer should not read scaffold text |
| An analyzer finding of severity high (exit 2) | Same gate CI applies; fix it before a human sees it |
| A `python_action` or `custom_python` target that does not resolve | Checked by reading the files, never by running your Python |
| A directory that is not `skillhub/<author>/<slug>` inside a source checkout | The PR may only touch your own folder |
| Symlinks and special files | A link could point outside the folder |
| A plan that no longer matches the files on disk | Rerun `submit`; what you reviewed is what gets pushed |
| `tos_risk:` missing or not `low`, `medium`, `high` | The registry build fails closed; the hub never lists a skill with an undeclared risk |

Do not edit `skillhub/registry.json` or anything under `skillhub/registry/`. CI generates them after merge.

---

## What CI runs on your PR

`.github/workflows/skill-submission.yml`, on `pull_request` (never `pull_request_target`):

1. **Ownership**: your GitHub login must match the `<author>` folder. One author folder per PR; generated registry files untouched.
2. **`ghost skill validate`**: hard block.
3. **`ghost skill analyze`**: a high finding blocks; a medium one adds the `needs-security-review` label for a human.
4. **`ghost skill lint`**, bandit, semgrep: warnings.
5. **Version bump**: an existing skill's `version:` must increase (SemVer).
6. **Dry run** in a container with no network and a read-only filesystem: blocks on import or parse errors.
7. **Verification artifacts**: any added `verifications/*.json` must be signed by the PR author (details below). Run artifacts under `runs/` are checked the same way when the registry is built: a signed run counts as the author's or the maintainer's own evidence, an unsigned or mismatched one is rejected, never counted.
8. **Security tier**, enforced except APK sources and automatic rejection (the [security policy](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/skillhub/security.md) marks what is enforced today): a YAML-only hard skill for an app on the [trusted-vendors allowlist](https://github.com/ghost-in-the-droid/android-agent/blob/main/skillhub/trusted-vendors.yml) runs on the emulator automatically; a skill with its own Python, or for an app not on the allowlist, waits until a maintainer reviews it and adds `approved:<full sha>`; network calls from skill code, secrets, arbitrary APK URLs or obfuscated code fail the PR.
9. One **sticky comment** with the results and the quality signals the registry will compute, plus labels (`skill-submission`, `has-python`, `soft-skill`, `size/*`).

A maintainer can add the `skill-emulator` label to run an optional emulator job, which records a smoke action and uploads the signed run as an Actions artifact for review; it is never a required check and commits nothing (see the [verify runbook](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/skills/verify-runbook.md#ci-emulator-run)). CI never runs a skill against a logged-in account, and nothing auto-merges.

---

## Review

From your second merged PR, CODEOWNERS makes you the reviewer of your own folder. Maintainers review first-time authors and anything touching CI or the registry, along these lines:

**Correctness**: fingerprint matches what you tested; validators actually gate success; `python_action` targets do only what the skill needs.

**Safety**: `data_access`, `side_effects`, `destructive` and `tos_risk` honest (`tos_risk: high` when the vendor's terms ban automated access or bot-created accounts: the skill page then shows a warning and the skill is published for research only); analyzer findings explained; no private data (real handles, tokens, contacts, device serials) in `SOFT.md`, `runs/` or `data/`.

**Quality**: README explains the skill and links a demo; real `ref_prompt`s; prompt variants that vary.

Target for a first response: 7 days.

---

## After merge

- CI tags `<author>/<slug>-v<version>`, signs the release tarball with Sigstore, records build provenance, regenerates `skillhub/registry.json` and the per-skill index file, and purges the jsDelivr cache.
- `ghost skill install alice/whatsapp-messaging` works from then on.
- The skill shows trust **Verified** and quality **Draft** or **Runs** (Runs if you committed a self-run and a README). How points and tiers are computed, with a worked example from a real entry: [How skills are scored](/skills/scoring/).

---

## Getting to Proven, then Hardened

A skill reaches **Proven** on your own evidence: 35 points, your own signed passing run on every action, a demo clip (30 s max) and 3+ step-level validators on every action. Docs and packaging (up to 20 points) plus your own runs, validators, benches and a second device of your own (up to 30) take a skill to 50 points without anyone else.

**Hardened** (60) starts with independent verification: someone else runs the skill on a device you have not recorded on and it passes. It also needs 2+ phone makers or Android versions, benches on 2+ models and 10+ community runs. Reference (90) adds 60 days at Hardened and a curator review, so the top tiers still take other people's runs, community use and maintenance.

### Independent verification

Ask for a run with the **Verify request** issue form, or in the community channel. The verifier runs:

```bash
ghost skill verify alice/whatsapp-messaging@1.0.0 --device <serial>          # preview
ghost skill verify alice/whatsapp-messaging@1.0.0 --device <serial> --push   # open the PR
```

`--push` commits only `skillhub/alice/whatsapp-messaging/verifications/<verifier>-<fingerprint-hash>-<ts>.json` on a fresh branch and opens a PR. Verification-only PRs do not need a version bump and do not need to come from the skill's owner.

**How CI trusts the artifact.** It fetches the PR author's public SSH keys from GitHub and checks the artifact's signature with `ssh-keygen -Y verify` in the `ghost-skill-run` namespace. The filename login and the signed `verifier` field must both equal the PR author. Self-verification, tampering, missing signatures and mismatched keys are rejected. So a verifier adds `~/.ghost/run-signing-key.pub` to their GitHub SSH keys once.

Fair-play rules the scoring applies: self-runs never count as independent; one device counts once however many accounts use it; accounts younger than 14 days have their runs held; two accounts that keep verifying only each other stop counting after the third pair in 30 days.

---

## Status: blocked and deprecated

Set `status: blocked` when a skill cannot complete on its own today (for example the app now demands a phone check a bot must not clear). Blocked skills get a grey badge, are hidden from default browsing and the leaderboard, and still install with a warning. Set `status: deprecated` when you are retiring a skill; installs warn and point users to look for a replacement. Both are a normal version bump.

---

## Folder convention

```
skillhub/
└── <github-login>/
    └── <slug>/                  # matches skill.yaml name
        ├── skill.yaml
        ├── README.md
        ├── SOFT.md
        ├── helpers.py           # optional: python_action targets
        ├── validators.py        # optional
        ├── bench.yaml           # optional
        ├── demos/<action>.webm  # record with ghost skill demo; not downloaded on install
        ├── data/                # optional: reference screens
        ├── runs/                # your signed self-runs
        ├── verifications/       # other people's signed runs, added by their PRs
        └── SKILL.md             # generated wrapper; do not edit
```

**Collisions** are fine: `skillhub/alice/whatsapp-check-inbox/` and `skillhub/bob/whatsapp-check-inbox/` coexist; users install by full ref.

**Abandoned skills** are never handed over. Fork under your own namespace and credit the original in your README.

**Promotion to Official**: maintainers may copy a mature skill to `skillhub/ghost/<slug>/` with author credit. No auto-promotion.

---

## FAQ

**Q: My skill needs custom Python to prep media before upload. Allowed?**
A: Yes. Put it in `helpers.py`. The hub card shows that the skill has Python, CI scans it, and a maintainer reads it before the emulator runs your skill (manual review, Tier 2). No network calls, secrets or obfuscation.

**Q: Can my skill call other skills?**
A: Yes: a `run_skill` step with `name: <user>/<slug>`, `action` and `params`.

**Q: The app's UI changes often.**
A: Pin `fingerprint.app_version` tightly and publish new versions. A weekly drift job opens a `skill-drift` issue when the Play Store ships a version outside your range, and a failing run on a newer app version freezes the quality tier until a pass arrives.

**Q: Can I submit an iOS skill?**
A: Yes: `fingerprint.os: ios` and the bundle id as `app_package`. Device setup is in `docs/SETUP_IOS.md` in the repo; iOS support is experimental (`GITD_ENABLE_IOS=1`). Recording iOS runs needs `--fingerprint <file.json>`.

**Q: I found a bug in someone's skill.**
A: Open a skill bug issue with a run artifact that shows it, or a PR to their folder; the owner approves. An accepted bug report with a reproducing run earns Reviewer credit.

**Q: Did AI write my skill?**
A: Fine. Say so in `generated_with:`. Undisclosed AI generation is a 30-day points freeze.

---

## Etiquette

- One skill per PR.
- No near-identical skills across many accounts.
- When an app update breaks your skill, bump `version:` on the same slug.
- Run artifacts and bench numbers come from real runs. Forged artifacts unlist the skill.

---

## Next

- [How skills are scored](/skills/scoring/): how your submission climbs the tiers, with a worked example
- [Creating Skills](/skills/creating-skills/): full author flow
- [Using Skills](/skills/using-skills/): install, run, verify
- [Contribute](/skills/contribute/): the contributor ladder
- [Skill Hub](/features/skill-hub/): registry and community

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
