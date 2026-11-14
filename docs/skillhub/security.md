# Skill Hub security policy

Status: maintainer-approved model for Skill Hub CI, v1 (2026-10-08), revised after review rounds 1 and 2 of mirror PR #67. Applies to community skill PRs under `skillhub/<author>/<slug>/`. Official skills under `skillhub/ghost/` are maintainer-authored and maintainer-reviewed. Machine-readable input: `skillhub/trusted-vendors.yml`, read by `tools/ci/trusted_vendor.py`.

Every control below is tagged **[enforced]** (CI does it today on `feat/skillhub`) or **[planned]** (policy we have agreed on, not yet enforced by code). Do not rely on a [planned] control.

## 1. The real boundary [enforced, plus one public-transition setting]

The security of PR CI rests on what a PR job cannot reach, not on what it cannot run. Any PR can run arbitrary code in CI today: the general test workflow installs the package from the PR head, and GitHub runs `pull_request` workflow files from the PR's merge ref, so a PR can edit the workflows themselves. What protects us:

- **Ephemeral GitHub-hosted runners.** Every job starts on a fresh VM that is destroyed afterwards; nothing persists between runs and none of our machines is involved.
- **No secrets.** PR workflows trigger on `pull_request`, never `pull_request_target`, so a fork PR gets no repository secrets.
- **Read-only token.** PR jobs declare `permissions: contents: read`; checkouts use `persist-credentials: false`.
- **Write access only where no PR code runs.** The reporters (`skill-submission-report.yml`, `skill-emulator-report.yml`) run on `workflow_run` from default-branch code. They download bounded JSON artifacts, validate them against a strict schema, and post the sticky comment and labels. They never check out or execute PR code.
- **Secrets only after merge.** Release signing (Sigstore OIDC) and registry commits live in `skillhub-registry.yml`, which runs on `push` to `main` after a maintainer merged.
- **Pinned and linted workflows.** Every action is pinned to a commit SHA; `zizmor` and `actionlint` run on workflow changes.

**Repository setting:** the **"Require approval for all outside collaborators"** setting (Settings, Actions, General, fork pull request workflows) must be enabled on the repository, so no workflow runs for an outside contributor's PR until a maintainer clicks "Approve and run".

## 2. What the skill gate enforces today

- **[enforced]** Static checks on every changed skill: `validate` and `analyze` block (high analyzer findings fail; medium findings add `needs-security-review`), `lint` warns, ownership and one-author-dir rules, SemVer bump, no hand-edited registry files. The analyzer is an AST review aid, not a sandbox: it names shell and process execution, dynamic imports, network, writes outside the skill dir, non-literal attribute access and raw device commands so a maintainer reads exactly those lines; it cannot prove the absence of anything. The quality signals in the sticky comment are computed by the registry's own `doc_signals` (trusted base copy of `tools/`, mounted read-only into the sandbox), so the comment matches the post-merge registry.
- **[enforced]** `network-exfil` is high for helper calls through requests, httpx, urllib, socket, aiohttp or http.client, and calls with a literal HTTP(S) URL, unless every statically resolved destination is listed as an exact hostname in `data_access: {network: [api.example.org]}`; the legacy list entry `data_access: [network]` alone grants no host allowance, and unknown destinations remain high (constructors without endpoints and local URL/cookie utilities are not outbound calls).
- **[enforced]** `aliased-exec` is high for calls through assignments, tuple unpacking, import aliases or attribute lookup to exec/eval/compile/__import__, shell and process callables; string concatenation and constant interpolation are resolved without execution, and `importlib.import_module` with a module name that cannot resolve to a literal is high `dynamic-import`.
- **[enforced]** `soft-injection` is high in SOFT.md and manifest descriptions/prompts for agent override instructions, concealed instructions, external send directives, tool-call syntax, hidden Markdown comments, zero-width/bidi characters and long encoded blobs, with the matched text and source line included; these are conservative review signals, not proof that all prompt injection is detectable.
- **[enforced]** `typosquat-slug` compares slugs against the local registry index and is high for a different author's near-name (edit distance 1–2 or 0/o, 1/l, rn/m and hyphen confusables), except an explicit `forked_from: author/slug@version` matching that skill; same-author renames and exact app slugs in separate namespaces remain allowed.
- **[enforced]** These findings share the analyzer used by text/JSON analyze output, lint, submit and CI document signals; a false or unknown shared static-scan result becomes a failing submission analysis check, including when the CLI check passes.
- **[enforced]** The check scripts run from the **base** branch's copy of `tools/ci/`, and `trusted-vendors.yml` is read from the base checkout, so a PR cannot change the scripts or the allowlist that judge it. The workflow YAML itself is still PR-controlled; the reporters compensate (below).
- **[enforced]** Trust gate before the emulator job (`tools/ci/trusted_vendor.py`), per changed skill: `allowed = (app trusted AND no submitter Python) OR approved for this head commit`. The emulator matrix runs only when every changed skill is allowed.
- **[enforced]** Submitter Python is detected: any `.py` file in the skill dir, or any `python_action` / `custom_python` reference, outside `skillhub/_base/`. That directory does not exist yet, so today every skill with its own Python needs approval before the emulator runs it.
- **[enforced]** The reporter can never add an approval label itself; only a maintainer can.
- **[enforced]** Reporters (`skill-submission-report.yml`, `skill-emulator-report.yml`) run from default-branch code and **recompute the verdict from origin code**: they fetch the PR's changed files and its head `skill.yaml` and skill-dir listing through the API, and evaluate them with the default branch's `trusted_vendor.py` and `trusted-vendors.yml`, never trusting the PR's own verdict artifact.
- **[enforced]** PRs that touch CI or trust policy are flagged: when a PR changes anything under `.github/` or `tools/ci/`, or `skillhub/trusted-vendors.yml`, or the run did not come from the expected workflow file, the sticky comment opens with "this PR modifies CI or trust policy; results are not trusted", result artifacts are ignored, and `pending-security-review` is applied.
- **[enforced]** Approval is bound to a commit. It is the label `approved:<full 40-hex sha>` for the PR's current head commit, applied by an actor with admin or maintain permission. The origin reporter fetches label events and checks the latest matching label actor's live repository permission. SHA prefixes and labels applied by write-only users grant no approval. After every submission run, including the one triggered by a new push, the reporter removes any stale `approved:*` or legacy `security-approved*` label that does not match the current head, so a later commit never inherits an approval. When recomputing its verdict, the reporter also accepts a comment `security-approved <full head sha>` from a user with admin or maintain permission. The early gate independently verifies the same label actor or comment author through the API.
- **[enforced]** Only skill-directory changes are trusted: when any changed path (including a rename source) is outside the detected `skillhub/<author>/<slug>/` directories, or the run did not come from the expected workflow file, the sticky comment opens with "this PR modifies CI or trust policy; results are not trusted", result artifacts are ignored, and `pending-security-review` is applied.
- **[enforced]** Vendor GitHub repos are curated: signal 3 only reads a `vendor_repo` listed next to a prefix in `trusted-vendors.yml`. A `vendor_repo` in the submitter's `skill.yaml` is ignored and reported as a warning. The v1 list has no curated `vendor_repo` entries yet, so today this signal never grants trust.
- **[enforced]** CI emulator runs only target apps that ship on the stock emulator image. Nothing installs an APK.
- **[enforced]** Independent verification artifacts must be signed with an SSH key published on the PR author's GitHub account (section 6).
- Network failures while checking a signal never grant trust.

## 3. Still planned

- APK install sources and sha256 pinning (section 5).
- Automatic Tier 3 rejection; today it is a reviewer decision.
- Recording the tier on the registry entry after merge.

## 4. Three tiers

The tiers decide what CI may **execute unattended**, not what the hub accepts. Skills with their own Python are welcome; a maintainer reads that Python before CI runs it.

### Tier 1: auto-run [enforced, except item 3]

1. **No submitter Python**: no `.py` file in the skill dir and no `python_action` / `custom_python` outside `skillhub/_base/`.
2. **Allowlisted app**: `fingerprint.app_package` meets at least one signal: matches a `prefix` in `trusted-vendors.yml` (exact id, or the prefix followed by `.`); has an F-Droid package page (`https://f-droid.org/en/packages/<package>/`); or a curated `vendor_repo` for its prefix has 1000+ stars and releases.
3. **APK from an allowed source with pinned sha256.** **[planned]** (section 5)

Package-prefix trust is only meaningful together with pinned APK sources; that is acceptable for now because CI only targets apps on the stock image.

### Tier 2: manual review before CI [enforced]

A PR lands here if it has submitter Python, or if its app meets no signal (then the submitter names an allowlist-eligible source and its sha256). CI runs only the static checks; the emulator job waits until a maintainer adds `approved:<full 40-hex sha>` for the current head commit. A new push needs a new approval.

### Tier 3: reject [planned as automatic]

Network calls from skill code, anything touching secrets, arbitrary APK URLs, obfuscated code. Automatic rejection is planned; today this is a **reviewer decision**, helped by the analyzer (which blocks high findings such as shell execution, `eval` / `exec`, undeclared outbound calls and encoded blobs in agent instructions; encoded Python strings remain medium review findings).

**[planned]** The tier is recorded on the registry entry after merge.

## 5. APK install sources [planned]

Nothing installs APKs yet; CI only targets apps on the stock image. When APK installs arrive, these are the only allowed sources, listed under `apk_sources` in `trusted-vendors.yml`:

| Source | Rule |
|---|---|
| **F-Droid** | `https://f-droid.org/repo/<package>_<versionCode>.apk`; sha256 from the signed `index-v2.json`, checked after download |
| **Vendor direct** | Only the pages in `vendor_direct` (Signal, Telegram, Mozilla's archive plus the frozen Firefox GitHub releases up to v125.3.0, Termux GitHub releases); sha256 pinned in the PR, plus the vendor's signing-cert fingerprint where published |

Never allowed: APKMirror, APKPure, any other mirror or aggregator, arbitrary URLs from a skill or a PR, and APKs committed to the repository. A sha256 mismatch will be a hard failure.

## 6. Run records

**[enforced] Helper binding.** Both gates reject `unbound-helper` when a skill ships any `.py` helper and the artifact lacks a well-formed `skill_sha256` content digest; only skills without shipped Python retain legacy digest-free evidence, and unbound helper artifacts receive no current or previous-version credit.

**[enforced] App binding.** The registry and PR verifier reject `wrong-app` when an artifact's `fingerprint.app_package` or top-level `app_package` names a package outside the manifest's `fingerprint.app_package` / `fingerprint.apps` (including fingerprint lists and legacy flat package fields); omitted package fields retain compatibility.

**[enforced] App freshness.** Both gates reject `stale-app` when a recorded `fingerprint.app_version` or top-level `app_version` is outside the declared app version range in every applicable primary app fingerprint (legacy `app_version_tested` also applies), using the shared `version_matches` rules, including upper bounds, wildcard ranges, caret/tilde ranges and non-numeric actuals; companion apps without their own version declaration remain unconstrained.

`ghost skill run --record` and `ghost skill verify` write an **integrity-signed run record**: JSON signed with an SSH Ed25519 key. The signature shows the record was not altered after it was written. It is **not proof of provenance**: when a record is produced in CI, the key is generated inside the PR-controlled runner, and locally it is whatever key the author holds. **[enforced]** for verification PRs: CI checks the signature against the SSH keys on the PR author's GitHub account, and the filename login and signed `verifier` field must equal the PR author, which binds a record to an account, not to a device or a run.

**[enforced]** in the registry build (`tools/build_registry.py`): every `runs/` and `verifications/` artifact must verify (`ssh-keygen -Y verify`, namespace `ghost-skill-run`) against the trust files before it counts: `skillhub/SIGNERS` lists community principals (one line per key; CI accepts additions only for the PR author's own login with a key published on that GitHub account), `skillhub/verifier-keys.yml` lists the official `ghost` principal and platform verifiers (`ghost-ci-emulator`, `ghost-aw-replay`; maintainer-owned, CODEOWNERS). The principal is the author for self-runs and the verifier login for verifications. Simulated runs (`simulation: true` or a non-device backend), payloads altered after signing, keys not in the trust files, artifacts whose signed `skill` names another directory, and malformed `bench` blocks are rejected; the count and reasons appear in `quality.runs.rejected`. The embedded `public_key` in an artifact is informational only. The optional nested `bench` block (AndroidWorld task id, arm, seed, tokens, wall-clock) is display only and never scores.

**[enforced] Evidence classes (scoring v1.2, after the 2026-10-22 independent audit).** The registry classifies every verified artifact by the SIGNING KEY, never by its `verifier` label: `self` (the author), `maintainer` (signed with the author's or a maintainer-tier key, whatever principal name it carries; the registry re-verifies the signature against those keys), `ci` (a platform-tier principal with its own key; none exists yet, `verifier-keys.yml` lists empty key sets for `ghost-ci-emulator` and `ghost-aw-replay`), `independent` (a `SIGNERS` key that is neither). Only `independent` earns independent points; maintainer and CI runs feed maintenance and the card. A key may appear under exactly one principal and never in both trust files; the registry build refuses otherwise. A run counts only for the code on disk (same `version`, and the same `skill_sha256` content digest when the artifact carries one; new artifacts always do); older runs are shown as previous versions. Run credit and validator credit are per action (the weakest action decides), an independent device class needs a fingerprint the author never recorded on, and the `verifier` field is mandatory. Trust `verified` requires a line in `skillhub/REVIEWED`.

## 7. Who approves

- `.github/CODEOWNERS` is generated by `tools/build_codeowners.py` (the registry workflow rewrites it on every merge; it used to land in `skillhub/CODEOWNERS`, a path GitHub ignores): a catch-all plus `.github/`, `tools/ci/`, `tools/build_registry.py`, `tools/quality.py`, `skillhub/scoring/`, `skillhub/verifier-keys.yml`, `skillhub/trusted-vendors.yml`, `skillhub/ghost/` and this policy go to `@C-K-Loan`; every `skillhub/<login>/` maps to `@<login>`, and later lines win. The `maintainers` team must exist in the GitHub org for the handle to resolve (maintainer access required).
- **The maintainer** approves the `approved:<full 40-hex sha>` label on Tier 2 PRs, including the read of any submitter Python (or a maintainer delegated in writing), every change to `skillhub/trusted-vendors.yml`, every `private_cache` entry, and any change to this policy or the CI workflows.
- Maintainers may apply `needs-security-review`, ask for changes, or reject a PR; they cannot promote a PR to auto-run.

## 8. Getting a prefix added

Open a PR that changes only `skillhub/trusted-vendors.yml`:

1. Add `{prefix, vendor, category}` under the right category, with a one-line comment pointing at the app's official Google Play listing (`https://play.google.com/store/apps/details?id=<package>`).
2. Explain in the PR body why the vendor should be trusted (install base, known publisher, open source repo).
3. To propose an APK source, add it under `apk_sources.vendor_direct` with the vendor's own download page and how its integrity can be checked. Mirrors and aggregators are refused.
4. The maintainer reviews and merges. Prefixes are never added as a side effect of a skill PR, and a PR that touches this file is itself flagged as untrusted for review.

## Device coverage grid (2026-10-23)

Device coverage has four axes: **app version × OS version × screen (WxH + density) × locale**.
The builder reads `fingerprint.app_version`, `os_version`, `screen_wxh`, `density`, and `locale` from each
verified current artifact. Missing, empty or wildcard values become `"*"`; such a record covers no cell.
Skills default to en-US, but that default is never substituted for a missing recorded locale.

`quality.runs.device_grid` contains `cells` with `app_version`, `os_version`, `screen`, `density`, `locale`,
`independent` and `maintainer` run counts, plus `independent_cells`. Values of the axes are strings.
Each complete combination with at least one independent run covers one cell. Each current verified run
increments its cell's run count, including failures; coverage means tested, not passed. Repeated runs
and multiple fingerprints in the same cell do not increase the covered-cell count. A different locale
or another axis value on the same fingerprint is a different cell. Independent fingerprints also recorded
by the author remain excluded under the existing anti-gaming rule. Previous-version and rejected artifacts
never enter this grid. The existing latest-per-fingerprint rule for independent **scoring** remains unchanged.

The `maintainer` counter combines self and maintainer records; these remain visible, greyed and labelled
“not independent”, even in a cell that also has independent evidence. CI stays in the separate run breakdown
and never contributes independent coverage. Incomplete independent records remain visible with an explicit
no-coverage label. With zero covered independent cells the page says “No independent device runs yet.”

For **one release**, `quality.runs.independent_devices` (also in `quality.signals`) is a compatibility alias
for `device_grid.independent_cells`, **not physical devices**. Point values, device-class scoring and tier
requirements are unchanged. There are currently no independent runs in the hub, so every skill has zero
covered cells. The site uses the verified registry grid; it does not infer cells from unchecked local artifacts.

Unrooted showcase validators read exposed app state rather than treating inaccessible private databases as success. Clock's bounded, app-scoped snapshot JAR is shipped with source and an offline rebuild tool, runs as the adb shell user without installing an app, and is removed after each read. Tasks treats an unknown notification state as unsafe unless the intended app owns the focused, unobscured target. Pro Expense reopens saved entries without pressing UPDATE and rejects inputs that exceed its field limits before entry.

Native hierarchy reads can bypass Portal when validation needs package ownership or checked state; converted Portal XML alone cannot establish either. Markor dismisses its specific optional rating prompt with NO THANKS and never opens the store.

Clock uses its app-scoped snapshot for navigation and visible-state checks even on rooted devices, because expired timers can prevent idle reads on other tabs. Its saved-city validator requires the city-list screen, not a search result. Tasks can cross-check Compose controls against the focused app window and every higher visible window; missing geometry or overlapping windows refuse the tap.

Adding an already-visible Clock city is a no-op; selecting it again would remove it. The end-state validator still independently rereads the saved city list.

Markor confirms filename-field focus with fresh native UI state before typing; keyboard-induced dialog movement must not redirect input into the format field.

Device-grid names are display-only labels from a fixed mapping of known signed fingerprint models (for example Samsung Galaxy A03s). Unknown hardware is left unnamed; serials and arbitrary device-name strings are never copied into the grid. Multiple known models may share one measured coverage cell; adding a label does not add run or coverage credit.

Login state badges are declarations backed by positive visible selectors. Account-dependent TikTok, Play Store and recorded mail-send actions require `logged_in`; a missing or unreadable selector stops with `needs_state`. The signup action declares `provides_state: [logged_in]`. Its human-assisted captcha demo is a narrative note, not a scored replay or independent verification.

Showcase recording resets are opt-in and restricted to newly installed demo apps or explicitly snapshot-authorized fleet demo installs; system apps are never cleared, fixtures and HOME are verified before recording, and normal `run_action` calls preserve user data.

Skill Hub and showcase media are presentation-only: a clean-demo catalog binds each served clip to its bytes and ordered reset, verified fixture, HOME, capture-before-launch, and completed-action protocol; absent or invalid catalog entries never fall back to legacy or fixture videos and never grant independent-verification credit.
