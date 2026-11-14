# Phone CI (Tier 1: emulator on GitHub-hosted runners)

`.github/workflows/phone-smoke.yml` boots a throwaway Android emulator on a GitHub-hosted
`ubuntu-latest` runner and runs Ghost hard-skill smoke tests (tap / swipe / type) against it.
It is separate from `ci.yml`, which stays device-free.

Real-device runs (self-hosted runner with USB phones) are out of scope here.

---

## How it works

```
plan job                          smoke job  (one per skill, in parallel, fail-fast off)
────────                          ─────────
glob tests/phone/test_*.py   ──▶  checkout → enable KVM → pip install -e ".[test]"
filter by dispatch input          → restore AVD snapshot (actions/cache)
emit skills=[...] matrix          → reactivecircus/android-emulator-runner boots the emulator
                                  → scripts/ci/phone_smoke.sh <skill>
                                      prep device (animations off, stay awake)
                                      pytest tests/phone/test_<skill>.py --junitxml
                                  → on failure: upload phone-ci-artifacts/
```

| Piece | File |
|---|---|
| Workflow | `.github/workflows/phone-smoke.yml` |
| Per-skill entry point | `scripts/ci/phone_smoke.sh <skill>` |
| Fixtures, failure capture | `tests/phone/conftest.py` |
| UI-tree helpers | `tests/phone/helpers.py` |
| Skill tests | `tests/phone/test_<skill>.py` |

**Runner / emulator:** `ubuntu-24.04` (pinned: `ubuntu-latest` moves to 26.04 from 2026-10-19, and emulator/KVM setup is what breaks on image bumps), API 34, `google_apis`, `x86_64`, AVD profile `pixel_6` (1080x2400), software GPU
(`swiftshader_indirect`), no window, no audio. The tests assume 1080x2400 because
`_base` `SwipeDirection` swipes from a fixed `(540, 1200)` centre, and the `phone` fixture asserts that size.

**Isolation:** each matrix job runs on its own ephemeral GitHub VM with its own emulator on the
default `emulator-5554`. Nothing touches self-hosted machines or any existing emulator fleet.

**What the tests exercise:** Ghost's real `_base` skill actions (`LaunchApp`, `TapElement`,
`SwipeDirection`, `TypeText`) and `Device.dump_xml()`, against stock Settings and Contacts only. No logins,
APKs, LLM keys or secrets are needed.

| Skill | Checks |
|---|---|
| `tap_smoke` | Launch Settings, tap **Battery** by text, assert the Battery page renders |
| `swipe_smoke` | Launch Settings, swipe up 1000px, assert list rows entered *and* left the viewport |
| `type_smoke` | Open Contacts' *Create contact*, tap **First name**, type `ghostci`, assert the field holds it (not saved) |
| `screenshot_smoke` | `TakeScreenshot` writes a valid PNG whose IHDR size equals `wm size` |

---

## Triggers and cost guards

To keep CI minutes down, the workflow runs only:

- on **pull requests** to `main` / `master` / `rc/**`, **when phone-relevant paths change**
  (`gitd/bots/common/**`, `gitd/skills/{__init__,base,locations}.py`, `gitd/skills/_base/**`, `tests/phone/**`,
  `scripts/ci/phone_smoke.sh`, the workflow, `pyproject.toml`), and **not for draft PRs**;
- on **manual dispatch** (Actions → *Phone smoke* → *Run workflow*), with optional inputs
  `skills` (comma list, blank = all) and `api-level` (default `34`).

It never runs on push. `concurrency` cancels superseded runs on the same PR. Each job is capped at
**15 minutes**.

To run it on every PR, delete the `paths:` block. To widen it, add globs to `paths:`.

---

## Adding a skill test

1. Create `tests/phone/test_<skill>.py`. The file name **is** the matrix entry: `test_scroll_smoke.py`
   becomes the job `smoke (scroll_smoke)`. No workflow edit is needed.
2. Take the `phone` fixture (a `gitd.bots.common.adb.Device`). Every test starts on an unlocked
   home screen (autouse `home_screen` fixture).
3. Drive the device through Ghost's actions or skills, not raw `adb input`, so the test covers
   Ghost code. Assert on the UI tree with `helpers.screen_texts` / `helpers.edit_texts` and poll
   with `helpers.wait_until`, not with fixed `sleep`s.
4. Use only apps present on a stock `google_apis` image (Settings, Contacts, Clock, Files,
   Chrome...). If a test needs an APK, install it inside the test or script and say so in the docstring.
5. Run it locally (below) a few times before pushing. Flaky tests in a matrix cost real minutes.

Minimal template:

```python
"""scroll_smoke — <one line: what Ghost behaviour this proves>."""

from gitd.skills._base.actions.core import LaunchApp

from .helpers import screen_texts, wait_until


def test_something(phone):
    assert LaunchApp(phone, None, package="com.android.settings").run()
    assert wait_until(lambda: "Search settings" in screen_texts(phone))
```

Pitfalls found while building the first three:

- `Device.find_bounds(text=...)` compares against the raw XML, where `&` is `&amp;`. A label like
  "Network & internet" will not match. Pick labels without XML-escaped characters (or fix
  `find_bounds`).
- Skills use `gitd.skills.base.Element(name, text=..., content_desc=...)`, not
  `gitd.bots.common.elements.Element` (TikTok RID registry; it has no `.find()`).
- Settings' search header is sticky, so it stays in the tree after scrolling. On GH runners, rows
  scrolled off the top also stay in the tree with clipped bounds. Assert on a row's *position*,
  not on which rows are present.
- **`dump_xml()` can return a stale tree.** On a screen that never goes idle (e.g. Settings →
  About), `uiautomator dump` prints `ERROR: could not get idle state.`, exits 0 and leaves the
  previous screen's `/sdcard/tt.xml` in place. Pick screens that go idle, and suspect this when a
  failure's `ui.xml` disagrees with its `screen.png`.
- Avoid Settings search as a test surface. It lives in a separate Google app that indexes and
  updates itself for minutes after a fresh boot, and it flaked repeatedly on GH.
- Layouts shift after first paint (e.g. an account avatar loads late). Tap only after
  `helpers.wait_settled(...)`, and keep poll timeouts at about 30 s: a single uiautomator dump takes
  2–4 s locally and longer on CI.

---

## Running locally

Any emulator or device works. Use a port that does not clash with emulators you already run:

```bash
emulator -avd <api34-google_apis-x86_64-avd> -port 5680 -read-only -no-window -no-audio -no-boot-anim -no-snapshot &
adb -s emulator-5680 wait-for-device

PHONE_CI_DEVICE=emulator-5680 scripts/ci/phone_smoke.sh tap_smoke   # exactly what CI runs
PHONE_CI_DEVICE=emulator-5680 python3 -m pytest tests/phone -v        # whole suite
```

The tests read `PHONE_CI_DEVICE`, **not** `DEVICE`, so a `DEVICE` exported for your personal
phone never makes them drive it by accident. Without `PHONE_CI_DEVICE` the whole directory skips.

---

## Failure artifacts

On a failed **or timed-out/cancelled** job the workflow uploads `phone-smoke-<skill>-api<level>` (kept 14 days):

| File | Source |
|---|---|
| `<test-id>/screen.png`, `ui.xml`, `window.txt`, `logcat.txt` | captured by the `conftest.py` hook at the moment the test failed |
| `final-screen-<skill>.png`, `logcat-<skill>.txt` | captured by `phone_smoke.sh` after pytest exits non-zero |
| `adb-devices-<skill>.txt`, `boot-logcat-<skill>.txt` | captured by `phone_smoke.sh` when the emulator never boots |
| `junit-<skill>.xml` | pytest JUnit report |

---

## Known limits

- **KVM:** GitHub's standard Linux runners expose `/dev/kvm`; the *Enable KVM* step makes it
  accessible to the runner user. Without KVM the emulator falls back to software emulation and
  will not boot within 15 minutes. macOS and Windows runners are not supported by this workflow.
- **Boot time and the AVD cache:** on a cache miss the job boots twice (create and snapshot, then
  test). The first hosted run took **about 4.5 min per job** on a cold cache. `actions/cache`
  entries are ref-scoped: a cache saved by a PR run is only visible to *that* PR. A PR can also
  restore its base branch's and the default branch's caches. So **seed the cache once per base
  branch** by dispatching the workflow on that branch (Actions → *Phone smoke* → *Run workflow*,
  branch = `rc/...` or `main`); every PR into it then starts warm. The snapshot counts against the
  repo's 10 GB cache quota. The system image is downloaded on every run. Bump the `-v1` suffix in
  the cache key to force a fresh snapshot.
- **Runner disk:** a cold AVD needs about 7.4 GB free for its userdata partition. The 2026-11
  `ubuntu-24.04` image leaves about 6.8 GB on `/`, so the emulator exited `FATAL ... Not enough space
  to create userdata partition` and `android-emulator-runner` reported *Timeout waiting for emulator
  to boot* 10 min later. The *Free runner disk* step removes unused toolchains first and logs `df -h /`
  before and after. If boots time out again, check that line and the emulator's `FATAL` output first.
- **Boot failure:** if the emulator doesn't report `sys.boot_completed` within about 4 min,
  `phone_smoke.sh` exits 3 with `::error::` and saves `adb devices` and boot logcat. Artifacts also
  upload when the 15-min timeout cancels a job.
- **Fresh-image quirks:** Google apps keep indexing and updating themselves for minutes after
  boot. Assert on what Ghost did (field text, row position), not on app-side state such as search
  results.
- **Cost scales with skills:** every skill boots its own emulator. That is fine for a handful of
  smoke tests. Past roughly 8 skills, group related tests into one file per job, or add a "suite"
  mode that runs several skills against one boot.
- **Software GPU:** `swiftshader_indirect` is slow for animation-heavy apps. Animations are
  disabled, and tests should poll the UI tree rather than time things.
- **Emulator ≠ phone:** no OEM skins, real sensors, Play-signed apps or logged-in accounts. Those
  need real devices.
- **Single API level** per run. Add `api-level` to the matrix for coverage across versions, at a
  multiplied cost.


## Skill submission emulator recordings

`.github/workflows/skill-emulator-run.yml` runs only on `pull_request` changes to `skillhub/**`, with `contents: read` and no user secrets. The hub lives at `skillhub/<author>/<slug>`; `registry/skills/**` does not exist. The matrix uses `tools/ci/common.py:skill_dirs`, filters deleted manifests and allows two concurrent jobs. There is one emulator path; the old label-gated runner is removed.

The runner first calls the reusable `skill-submission.yml` gate. Its `checks` job validates schema, analyzes security and performs dry checks. The new `trust` job depends on those checks. This explicit dependency supports fork PRs without granting them a write token. Direct skill-submission PR checks continue to run as well. All execution jobs use read-only credentials, and no secrets are inherited.

`tools/ci/trusted_vendor.py` recognizes a vendor from F-Droid HTTP 200 or a maintainer-curated prefix in `skillhub/trusted-vendors.yml`. Prefix entries may contain an optional `vendor_repo: owner/name`; those entries use their mapped repository's at least 1000 stars and at least one release as the GitHub signal. Entries without a repository use direct package-prefix trust, with a dot boundary. A `vendor_repo` supplied in `skill.yaml` is ignored with a warning. Network or policy errors cannot grant trust.

The PR-side trust job is an early signal only. The authoritative verdict is recomputed by trusted default-branch code in `skill-submission-report.yml`. It obtains the changed file list, fetches each changed skill's manifest using the GitHub contents API at the full PR head SHA, and inspects the skill directory listing for existing Python files. It parses YAML data without checking out or importing PR code. The PR-run trust artifact is informational and is never read to determine the verdict or labels.

Automatic execution requires a trusted vendor and no submitter Python. `helpers.py`, `validators.py`, other skill Python files, and `python_action` or `custom_python` references outside `skillhub/_base` require approval even for a trusted package. Reports identify the exact decision branch: `vendor-no-python`, `sha-approval` or `blocked`.

Approval is bound to the current commit. The maintainer may add `approved:<full 40-hex sha>` for the current head. The origin reporter checks the latest matching labeled event and accepts only an actor with admin or maintain permission. It also accepts `security-approved <full sha>` comments from an admin or maintainer, after checking live permission. The reporter never creates approval labels. SHA prefixes, write-only actors, and approvals for previous commits grant no approval. On synchronized PR heads it removes stale `approved:*` and legacy `security-approved*` labels. Static checks still must pass. Both reporters trust results only when every changed path is within the detected skill directories; changes to runtime code, docs, generated registry files, or any other path make results untrusted.

Both origin reporters fetch `pulls/<number>/files` and check the run's workflow path against the expected workflow file. If the PR changes `.github/**`, `tools/ci/**` or `skillhub/trusted-vendors.yml`, or the workflow path does not match, the comment header is `this PR modifies CI or trust policy; results are not trusted`. Such comments contain no green verdict and skip PR result downloads. Changed-file lookup or origin recomputation failures also fail closed. The origin reporter applies `pending-security-review` to blocked or untrusted changes. The main PR workflow never posts comments or changes labels.

Each row keeps the phone-smoke API 34 `google_apis` x86_64 Pixel 6 AVD, Ubuntu 24.04, KVM, v2 snapshot cache and 15-minute timeout. The boot flow reuses the #61 `phone_smoke.sh --settle-only` script verbatim: two consecutive UI dumps must complete in at most six seconds before the UI is considered idle. The snapshot and execution steps both use this settle flow, replacing the old snapshot echo. Compatible actions run `PYTHONPATH=. python3 -m gitd.skills.engine.cli test <skill dir> --live --device emulator-5554 --action <name>`, followed by `run <skill dir> <name> --device emulator-5554 --record`. Both use action `demo_params`, then `test_case.params`, then no supplied parameters. These are two executions under a shared 180-second action deadline. A per-action `adb shell screenrecord --time-limit 170` MP4 spans both calls and is pulled even after failures. Fingerprint mismatches, unavailable optional fields and missing installed apps produce explicit skip reasons.

Any action failure fails its matrix job. Missing videos or fresh integrity-signed run records also fail that action. The stable aggregate check `skill-emulator-proof` fails on gate, boot, action or evidence failures. These checks are non-required by default through branch protection, rather than suppressing failures with `continue-on-error`. The maintainer can make `skill-emulator-proof` required when ready; no branch protection settings are changed by this code.

`.github/workflows/skill-emulator-report.yml` runs on completed `workflow_run` events from `Optional skill emulator runs`. It checks out only the trusted default branch, downloads only result-summary artifacts containing exactly one bounded `result.json`, and validates exact object fields, bounded arrays and strings, enums, numeric ranges, concrete passing fingerprints, duplicate JSON keys and absence of HTML/control characters. ZIP and expanded JSON sizes are capped at 1 MB and 200 KB. It never downloads or executes PR scripts, MP4s or signed-run files. It posts or updates one sticky run-result comment with red failures, per-action wall time and step counts, fingerprints and video/evidence links. Old or closed PR runs cannot update comments.

MP4s and integrity-signed run-record JSON are uploaded as `skill-emulator-media-<index>` artifacts for 14 days without repository commits. Each record is integrity-signed using a key created on the PR runner; it authenticates those recorded bytes, not independent reviewer approval or provenance. The private key remains outside uploaded paths. Reporting JSON is uploaded separately. `.github/workflows/skill-submission-report.yml` preserves the existing trusted submission comment and labels and recomputes the authoritative execution gate and manages commit-bound approval and pending-security-review labels. This separation prevents the reusable gate from requesting write privileges. Reporter credentials are never exposed to the PR execution workflow.

Local tests mock HTTP, GitHub and device subprocesses. Hosted execution stays on GitHub-hosted runners.
