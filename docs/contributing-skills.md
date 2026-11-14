# Contributing Skills

How to submit a skill to Ghost Skill Hub. Companion to `docs/skill-taxonomy-soft-vs-hard.md` (concepts), `docs/skill-schema-v2.md` (spec) and `docs/community/contributor-ladder.md` (how contributors and skills climb).

**TL;DR**: a skill is a folder at `skillhub/<your-github-login>/<slug>/` in `ghost-in-the-droid/android-agent`, submitted as a pull request. Merging gets it listed. Evidence from real runs, not merging, moves it up the quality ladder.

---

## 1. Why contribute a skill

**Skills cost $0, thinking costs tokens.** A skill you author once replays deterministically for every agent that calls it, with no model in the loop.

Highest-impact contributions, in order:
1. **A skill for a top mainstream app** we do not cover yet. See the [open skill requests](https://github.com/ghost-in-the-droid/android-agent/issues?q=is%3Aopen+label%3Awanted-skill).
2. **A new action on an existing skill** (`reply_last_msg` when only `send_msg` shipped).
3. **An independent run** of someone else's skill on a phone they do not have (see section 5). No authoring needed.
4. **A bench trace** on a shipped skill (with-skill vs without-skill numbers you observed).

---

## 2. Prerequisites

- `pip install ghost-in-the-droid`
- `gh` CLI installed and authenticated (`gh auth status`)
- One Android device with USB debugging (or iOS, see `docs/SETUP_IOS.md`)
- A GitHub account. Your login is your author namespace: `skillhub/<login>/`.

`ghost skill doctor` checks all of the above.

---

## 3. The flow

```bash
ghost skill scaffold <you>/<slug> --app <package> --actions <a,b>   # 1. create skillhub/<you>/<slug>/
# ... author skill.yaml, helpers.py, README.md, SOFT.md ...
ghost skill validate skillhub/<you>/<slug>                          # 2. schema check (hard gate)
ghost skill lint skillhub/<you>/<slug>                              #    stricter checks, warnings
ghost skill analyze skillhub/<you>/<slug>                           #    static security scan of Python
ghost skill test skillhub/<you>/<slug> --live --device <serial>    #    iterate on a device; writes no artifacts
ghost skill run skillhub/<you>/<slug> <action> --record             # 3. signed self-run into runs/ (passes and failures)
ghost skill submit skillhub/<you>/<slug> --push                     # 4. fork, push, open the PR
```

After merge, open a **Verify request** issue so someone with a different phone runs it (section 5).

### 3.1 Scaffold

```bash
ghost skill scaffold alice/whatsapp-messaging \
  --app com.whatsapp \
  --skill-class hard \
  --actions send_msg,reply_last_msg
```

Creates `skillhub/alice/whatsapp-messaging/` with:
- `skill.yaml`: Schema v2, pre-filled with name, version `0.1.0`, author, fingerprint and one stub per action
- `helpers.py`: stubs for `python_action:` targets, referenced as `helpers:<fn>`
- `SOFT.md`: narrative template the adapt mode reads
- `README.md`: template

### 3.2 Author

**Path A: Skill Miner (planned, not in v1.6.0).** `ghost skill mine` will drive the app with an agent, record the trace and write the `steps:` and a draft `end_state_validator:`. Until it ships, drive the phone with your agent of choice (Ghost MCP tools) and write the steps from the trace, or use Path B.

**Path B: by hand.** Edit `skill.yaml` directly; use `ghost dev record` in another terminal to capture element ids while you tap around.

Every action needs:
- `ref_prompt`: the canonical natural-language phrase
- `params`: named, typed inputs
- `steps`: atomic steps, plus `python_action: helpers:<fn>` where needed
- `end_state_validator`: conditions that must hold after success (3+ step-level validators are required for the Proven tier)
- `test_case.ref_prompt_variants`: 2 to 3 real paraphrases

Top-level fields new in v2 that validate checks:
- `license:` SPDX id, **required** (MIT matches the repo)
- `generated_with:` free text, **required**. Say which model or tool helped, or `none`. AI help is fine; hiding it is a 30-day points freeze.
- `side_effects:` any of `sends_message`, `posts_content`, `makes_payment`, `modifies_account`, `deletes_data`, `none`
- `destructive:` `true` requires a `confirm_before:` step or `dry_run` support; installs then ask for acknowledgement
- `tos_risk:` `low`, `medium` or `high`
- `locale:` BCP-47 list you tested in
- `data_access:` what the skill reads (contacts, files, notifications, ...)

`python_action:` targets import by file path relative to the skill dir. Dotted `gitd.skills.*` targets are rejected.

### 3.3 Validate, lint, analyze

`ghost skill validate <path>` (about a second, no device) checks schema conformance, required fields, that every `python_action:` resolves, and selector syntax. Exit 0 or fix and retry.

`ghost skill lint <path>` adds stricter checks: unused or undeclared params, empty or TODO prompts, duplicate prompt variants, coordinate taps without a note, steps after a terminal HOME press. Exit 1 on errors, 0 with warnings.

`ghost skill analyze <path>` AST-scans every `.py` file for `os.system`, `shell=True`, `eval`/`exec`, `__import__`, `ctypes`, raw sockets, network calls outside `gitd.http`, writes outside the skill dir or `/tmp`, and long encoded blobs. Exit 2 on a high finding.

### 3.4 Record a self-run

```bash
ghost skill run skillhub/alice/whatsapp-messaging send_msg \
  --param contact_name=Me --param message="test" --record
```

Runs the action on your device and writes a signed artifact to `runs/<fingerprint-hash>-<ts>.json`: fingerprint hash, app version, per-step result. Commit it with the skill. One self-run plus a README takes the skill to **Runs**.

`ghost skill test <path> --live` still exists for iterating on all actions at once; it does not write run artifacts.

### 3.5 Submit

```bash
ghost skill submit skillhub/alice/whatsapp-messaging           # print title, branch, files, body (plan only)
ghost skill submit skillhub/alice/whatsapp-messaging --push    # fork the hub repo, push skill/alice-whatsapp-messaging, open or update the PR
```

The PR title is `[skill] alice/whatsapp-messaging v0.1.0`, branch `skill/alice-whatsapp-messaging`. The body lists actions, fingerprint, `data_access`, whether the skill has Python, bench summary, demo, and the checklist in section 9.

You do not edit `skillhub/registry.json`. It is generated by CI after merge.

---

## 4. What CI runs on your PR

On `pull_request` for `skillhub/**` (never `pull_request_target`):

1. **Ownership**: your GitHub login must match the `<author>` folder. A PR may touch only one author dir and never `skillhub/registry.json` or `registry/**`.
2. **`ghost skill validate`**: hard block.
3. **`ghost skill analyze`**: high finding blocks; medium adds `needs-security-review`.
4. **`ghost skill lint`**, `bandit`, `semgrep`: warnings.
5. **Version bump**: if the skill already exists, `version:` must increase (SemVer).
6. **Dry test** in a container with no network and a read-only filesystem: hard block on import or parse errors.
7. **Security tier** (`docs/skillhub/security.md`; enforced except APK sources and automatic rejection): Tier 1 (YAML-only hard skill, allowlisted app) runs on the emulator automatically; Tier 2 (your own Python, or an app not on the allowlist) waits for a maintainer's review and the `approved:<full sha>` label; Tier 3 (network calls from skill code, secrets, arbitrary APK URLs, obfuscated code) fails the PR.
8. **Sticky comment** with results and the quality signals the registry builder will compute.
9. **Labels**: `skill-submission`, `has-python`, `soft-skill`, `needs-security-review`, `size/*`.

An emulator smoke job exists but runs only when a maintainer adds its label, and is never required.

CI does not run your skill against any logged-in account, and nothing auto-merges.

---

## 5. After merge: tag, registry, and climbing

On merge to `main`:
- CI tags `<author>/<slug>-v<version>` (only CI creates tags), signs the release tarball with Sigstore, and regenerates `skillhub/registry.json`.
- `ghost skill install alice/whatsapp-messaging` then fetches from jsDelivr at that pinned version and checks every file's sha256 against the registry.

Merging lists the skill. It does not make it **Proven**. Quality tiers come from evidence:

| Tier | What it takes |
|---|---|
| **Draft** | Validates, static scan clean |
| **Runs** | README + one signed self-run |
| **Proven** | One independent run by another account on a different device fingerprint, demo video (demo.webm, 30 s max), 3+ step-level validators |
| **Hardened** | 2+ OEM or Android-major combos, bench on 2+ models, 10+ community runs with Wilson lower bound >= 0.80, "Known failure modes" section, re-verified in last 90 days |
| **Reference** | Hardened 60+ days, curator review, no open P1 > 14 days, author at Contributor+; about 5% of Hardened per category |

The score runs from 0 to 100, and each tier also needs a points floor: Draft 0, Runs 10, Proven 35, Hardened 65, Reference 90. Points come from five capped categories:

| Category | Cap |
|---|---|
| Docs and packaging | 15 |
| Self-evidence (your own runs, validators, bench) | 15 |
| Independent verification (other people's runs on other devices) | 40 |
| Community usage (Wilson lower bound over the last 90 days, once 10+ runs exist) | 20 |
| Maintenance (re-verified within the last 30 days: 6; each bug report answered within 7 days: 2, up to 4) | 10 |

Downloads and likes are displayed and worth 0 points. The numbers come from `skillhub/scoring/v1.json` and change only between seasons with 30 days notice. See the scoring page for the full table.

**Getting to Proven:** file a Verify request (`.github/ISSUE_TEMPLATE/verify_request.yml`) or post in #verify-requests on [Discord](https://discord.gg/gmvDX4Juk). A verifier runs `ghost skill verify alice/whatsapp-messaging@0.1.0 --push`, which records a signed run and opens a PR adding `verifications/<their-login>-<fingerprint-hash>-<ts>.json` to your skill dir. You approve it as the folder's code owner.

Self-runs never count as independent. One device fingerprint counts once. Accounts younger than 14 days have their runs held. Two accounts that verify only each other stop counting after the third pair in 30 days.

---

## 6. Review

Maintainers review new authors' first PR and anything touching `.github/` or the registry. Once your first skill is merged, the generated `.github/CODEOWNERS` maps your folder to you and you become its reviewer; the catch-all line routes everything else to the maintainers.

**Correctness**: declared fingerprint matches what was tested; validators actually gate success; `python_action:` targets do only what the skill needs.

**Safety**: `data_access:`, `side_effects:`, `destructive:` honest; analyzer findings explained; no private info (real handles, tokens, contacts) in `SOFT.md`, `runs/` or `data/`.

**Quality**: README explains the skill and links a demo; real `ref_prompt`s; prompt variants that actually vary.

Turnaround target: first response within 7 days, faster during launch.

---

## 7. Folder structure

```
skillhub/
├── ghost/                         # official skills, maintainers only
│   └── tiktok/ ...
├── <github-login>/
│   └── <slug>/                    # matches skill.yaml name
│       ├── skill.yaml
│       ├── README.md
│       ├── SOFT.md
│       ├── helpers.py             # optional: python_action targets
│       ├── validators.py          # optional
│       ├── bench.yaml             # optional
│       ├── demo.webm              # optional, required for Proven (VP9, muted, <=30 s, long side 720 px, <1.5 MB;
│       │                          #   demo.mp4 H.264 or legacy demo.gif also count); not downloaded on install
│       ├── data/                  # optional: reference screens
│       ├── runs/                  # your signed self-runs
│       ├── verifications/         # other people's signed runs, added by their PRs
│       └── SKILL.md               # GENERATED wrapper for skills.sh / LobeHub / Hermes; do not edit
└── registry.json                  # GENERATED by tools/build_registry.py; never hand-edit
```

**Collisions** are fine: `skillhub/alice/whatsapp-check-inbox/` and `skillhub/bob/whatsapp-check-inbox/` coexist; users install by full ref.

**Abandoned skills** are never adopted. Fork under your own namespace and say so in the README.

**Promotion to Official**: maintainers may copy a mature skill to `skillhub/ghost/<slug>/` with author credit. No auto-promotion.

---

## 8. Trust badges (separate from quality tiers)

Trust is about provenance and safety, not about whether the skill works.

| Trust | Where | Install UX |
|---|---|---|
| 🟢 Official | `skillhub/ghost/*` | Silent |
| 🔵 Verified | `skillhub/<login>/<slug>/` merged through the PR flow, listed in `skillhub/registry.json` | "Installing verified community skill by @alice" |
| 🟡 Unverified | `ghost skill install --url <git-url>` outside the hub repo | Warning, requires `y` or `--yes` |
| 🔴 Quarantined | Flagged by maintainers or the scanner | Install blocked; `--force` overrides with a warning |

So a freshly merged skill is trust **Verified** and quality **Draft** or **Runs**. It becomes quality **Proven** only when someone else runs it.

---

## 9. Submission checklist

- [ ] `ghost skill validate` exits 0; `lint` has no errors; `analyze` has no high findings
- [ ] `license:` and `generated_with:` set
- [ ] At least one `runs/*.json` from `ghost skill run --record`
- [ ] `README.md` explains the skill; demo GIF if you are aiming for Proven
- [ ] `SOFT.md` narrates each action for adapt mode
- [ ] Every `ref_prompt` is real; variants are actual variants
- [ ] `data_access:`, `side_effects:`, `destructive:`, `tos_risk:` honest
- [ ] `popup_detectors:` cover the popups you hit
- [ ] Fingerprint matches what you tested (do not wildcard `hardware:` from one device)
- [ ] `version:` bumped if the skill already existed

---

## 10. Bench submission (optional; `ghost skill bench` runs the AndroidWorld replay arm today, the agent arms are planned for v1.7)

```bash
ghost skill bench androidworld/pro-expense --androidworld ExpenseAddMultipleFromMarkor --bridge-cmd "<aw_bridge cmd>"   # replay arm, exists
ghost skill bench skillhub/alice/whatsapp-messaging --action send_msg --brain <model>   # agent arms: planned, not in v1.6.0
```

Will run `test_case.ref_prompt_variants[0]` once without the skill and once with it, and writes a `bench.yaml` entry with steps, tokens, wall time and success for both. A bench on 1 model earns self-evidence points; benches on 2+ models are a Hardened gate. Report the brain you actually use, and report failed baselines as `success: false`.

---

## 11. Common questions

**My skill needs custom Python.** Fine. Put it in `helpers.py`, reference `helpers:<fn>`. The card shows `has_python`, the analyzer scans it, and a maintainer reads it before CI runs the skill on the emulator (Tier 2 in `docs/skillhub/security.md`). Network calls, secrets and obfuscated code are rejected.

**Can my skill call other skills?** Yes: `{action: run_skill, name: alice/login-google, ...}`.

**The app's UI changes often.** Pin `fingerprint.app_version` tightly and publish new versions; use `screen_hash:` or `ocr_text_present:` validators and `checkpoint:` gates where the UI shifts. A weekly drift job opens a `skill-drift` issue when the Play Store ships a version outside your range, and a failing run on a newer app version freezes the tier until a pass arrives.

**It fails on a user's phone with a matching fingerprint.** The engine falls back to adapt mode using your `SOFT.md`. Ask the user for a run artifact; a fix plus a passing run restores the tier.

**iOS?** Set `fingerprint.os: ios` and the bundle id. See `docs/SETUP_IOS.md`.

**I found a bug in someone's skill.** Open a `skill-bug` issue with a run artifact, or a PR to their folder; the owner approves. Accepted bug reports with a reproducing run earn Reviewer medals.

**License?** Declare it in `license:`. MIT matches the repo; anything else needs a `LICENSE` file in the skill dir.

---

## 12. Etiquette

- One skill per PR.
- Do not spam near-identical skills across accounts.
- When an app update breaks your skill, bump `version:` on the same slug rather than starting a new one.
- Run artifacts and bench numbers must come from real runs. Forged artifacts unlist the skill and reset the author's trust.

---

## 13. Getting help

- **Discord**: #help on [our server](https://discord.gg/gmvDX4Juk)
- **GitHub Issues**: label `skill-question`
- **`ghost skill doctor`**: checks your setup
- `docs/skill-schema-v2.md` and `docs/skill-taxonomy-soft-vs-hard.md` are the definitive references

## Recording a demo

Use the same framed terminal-and-phone format as Ghost's Claude showcase demos:

```bash
ghost skill demo alice/example --action main --param query='demo query' --device emulator-5554 --render-host <render-host> --dry
ghost skill demo alice/example --action main --param query='demo query' --device emulator-5554 --render-host <render-host>
```

`--dry` prints the generated showcase spec, MCP config, and capture/render command arguments without running an agent, adb, or an encoder. With an authenticated Claude Code installation, the default uses the real Claude Code TUI through `scripts/showcase/claude_tui_driver.py`, with the Ghost MCP server configured for the selected device and the inherited `ADB_SERVER_SOCKET`. The prompt comes from the action's `ref_prompt`, with resolved parameters; `--prompt` overrides the phrase. The agent is instructed to execute the selected action exactly once with `--record` to retain signed run evidence, then inspect the phone through Ghost MCP.

Claude authentication is checked on the local machine; a missing executable or unavailable login falls back to the deterministic engine pane. `--dry` never checks authentication. `--agent cli` explicitly records `ghost "<prompt>"` in asciinema and requires a configured LLM backend; it is not an automatic fallback. `--agent engine` runs `ghost skill run --live-trace --record` directly as a secondary mode. Live trace prints completed steps, their arguments and duration, the end-state validator result, and the artifact path. `--layout phone` omits the terminal pane while keeping the existing device frame; `--layout split` is the original showcase composite. `--record-size WxH` controls adb's capture size.

Without `--action`, the command records every action sequentially, force-stopping and relaunching the app between clips. It validates all required parameters before recording; repeat `--param k=v` for the union of values the selected actions need. Values are forwarded only to actions that declare them. Output is `demos/<action>.webm` per action; `--out path/demo.webm` is available when one action is selected. A copy of the first action's clip remains at `demo.webm` for older readers. The generated `demos/<action>.spec.yaml` retains the prompt, parameters, MCP config, captions, capture settings, and command for reproducible re-recording. Titles name the skill and action; captions begin with the ref prompt and follow with step captions; the outro shows the skill install command. A `demos/` folder above 10 MB warns without blocking individual clips. The render-host pipeline retains the showcase intro, outro, captions, privacy preparation, terminal scrubbing, and OCR gate. Final output is muted VP9 WebM with a 720-pixel long side and at most 30 seconds. Longer recordings are trimmed with a warning; files above 1.5 MB warn, and files above 3 MB fail before publication. Review the result because trimming can remove the action's ending.

Install adb, asciinema, ssh, and scp locally. Install adb, agg, ffmpeg (including ffprobe), and Tesseract on the render host. The local machine never runs agg, ffmpeg, compositing, or transcodes. The command prints install hints for missing tools; Claude mode also needs Claude Code. Use an emulator or a clean demo phone. A physical phone with any logged-in account, or an unreadable account report, is refused unless you pass `--i-know`. `--no-ocr` skips both pre-record and final OCR explicitly, while keeping text scrubbing and the account guard. These overrides require manual privacy review. No recording, agent execution, or encoding is performed by the tests.

The recorder wraps `scripts/showcase/record_skill_demo.py`, which stages a temporary showcase tree, copies the existing brand assets, generates the per-action intro card, and delegates capture/compositing to `scripts/record_demo.py`. Claude uses an external cast from `claude_tui_driver.py`, so asciinema is started once. The terminal is 60 columns for readability at 720 pixels. `--phone-offset` compensates the phone lead relative to the terminal, defaulting to 3 seconds; use 0 when the recordings are already aligned. `GHOST_DEVICE` is passed through spec env so the serial is absent from the displayed engine command. With OCR enabled, set up the local identifier list described in `scripts/privacy/RECORDING_CHECKLIST.md` before real recording.

Split-host mode is required: pass `--render-host <render-host>` or set `GHOST_DEMO_RENDER_HOST`. `--render-root` / `GHOST_DEMO_RENDER_ROOT` selects the checkout on that host (default `~/ghost-in-the-droid`); `--render-python` / `GHOST_DEMO_RENDER_PYTHON` selects its Python environment. Both checkouts need the demo recorder changes. The local TUI and MCP server use `ADB_SERVER_SOCKET=tcp:<render-host>:5037` and the selected `GHOST_DEVICE`. The render host starts the phone recording, the local machine captures the terminal, then SSH stops the phone capture. Cast, spec, and plan are copied over SCP. The renderer generates the intro and runs agg, compositing, VP9 transcode, OCR, and ffprobe. Only the verified clip and its size/duration report are copied back. Temporary files are cleaned up; failed captures attempt to stop the remote screenrecord too. Synchronization assumes the hosts have synchronized clocks; `--phone-offset` handles recording startup lead.

Use `--actions calculate,convert_units` for a subset, preserving the requested order. `--actions` cannot be combined with `--action` or a positional action. With neither selector, every action gets a clip.

For the calculator pool smoke run, once the updated checkout is available on both machines:

```bash
tools/emulator_pool.sh
tools/emulator_pool.sh client
ghost skill demo skillhub/ghost/calculator --device emulator-5554 --render-host <render-host> \
  --param expression='84-2*6' --param category=Temperature --param value=100 \
  --param from_unit=Fahrenheit --param to_unit=Celsius --dry
ghost skill demo skillhub/ghost/calculator --device emulator-5554 --render-host <render-host> \
  --param expression='84-2*6' --param category=Temperature --param value=100 \
  --param from_unit=Fahrenheit --param to_unit=Celsius
tools/emulator_pool.sh stop
```

Stop the pool after the run, including after a failure. The recorder prints each returned clip's byte size and duration. The pool smoke run has not been performed in the restricted worker sandbox.
