# Verify and record a skill run

Run these commands from a Ghost source checkout. `python3 -m gitd.ghost_cli` runs the checkout's CLI; an up-to-date `ghost` entry point accepts the same arguments. Use the explicit skill directory to record the checked-out version rather than an older installed copy.

The commands below use the migrated Google Maps `search_place` action. It opens a public place card without an account. Before running it, open Maps, finish any first-launch prompts, and leave its main search box visible. Review the skill's params, fingerprint, and side effects before using other actions.

## Prerequisites

Install the project in your Python environment, Android platform tools, OpenSSH with `ssh-keygen -Y` signing support, and GitHub CLI. PR submission needs repository access and a configured git identity. The device needs Google Maps installed.

```bash
python3 -m pip install -e .
command -v adb ssh-keygen gh
git config user.name
git config user.email
gh auth status
```

`run --record` and `test --live` use a local Ed25519 SSH signing key at `~/.ghost/run-signing-key`, or under `GHOST_CONFIG_DIR` when set. The artifact includes the public key and signature, never the private key. A local signature establishes integrity, not GitHub account identity or independent device ownership.

## Android emulator

Use an existing Android AVD named `ghost-api-34`, with Google Maps installed. Starting the emulator is a verifier action; fixture tests never start one. If it uses a different serial, substitute the serial shown by `adb devices -l`.

```bash
emulator -list-avds
emulator -avd ghost-api-34 -no-snapshot-load -no-audio &
adb -s emulator-5554 wait-for-device
adb devices -l
adb -s emulator-5554 shell pm path com.google.android.apps.maps
adb -s emulator-5554 shell monkey -p com.google.android.apps.maps -c android.intent.category.LAUNCHER 1
```

Finish first-launch prompts in the emulator, then run one action and record its outcome:

```bash
python3 -m gitd.ghost_cli skill test skillhub/ghost/google_maps --live --action search_place --device emulator-5554 --param 'query=Brandenburg Gate'
```

`test --live` does not write run artifacts; `run --record` does. To record a single action:

```bash
python3 -m gitd.ghost_cli skill run skillhub/ghost/google_maps search_place --device emulator-5554 --param 'query=Brandenburg Gate' --record
```

## Real Android device

Enable USB debugging and authorize the connected host. Choose your device's serial from the listing. These commands operate only on the explicitly selected device.

```bash
adb devices -l
VERIFY_DEVICE_SERIAL=replace-with-your-device-serial
adb -s "$VERIFY_DEVICE_SERIAL" shell pm path com.google.android.apps.maps
adb -s "$VERIFY_DEVICE_SERIAL" shell monkey -p com.google.android.apps.maps -c android.intent.category.LAUNCHER 1
```

Finish first-launch prompts on the device, then:

```bash
python3 -m gitd.ghost_cli skill test skillhub/ghost/google_maps --live --action search_place --device "$VERIFY_DEVICE_SERIAL" --param 'query=Brandenburg Gate'
python3 -m gitd.ghost_cli skill run skillhub/ghost/google_maps search_place --device "$VERIFY_DEVICE_SERIAL" --param 'query=Brandenburg Gate' --record
```

Each invocation records its own outcome. A failed action exits 1 and still writes failed evidence when the runner returns a result. Fingerprint collection or signing errors exit nonzero and do not create a successful artifact.

## Artifact location and contents

Self-run artifacts land beside the loaded skill:

```text
skillhub/ghost/google_maps/runs/<fingerprint-hash>-<timestamp>.json
```

If you run an installed ref instead of the explicit source directory, `runs/` is under the installed version's directory in `GHOST_SKILLS_DIR` or `~/.ghost/skills/`. The CLI prints the complete artifact path.

Artifacts include the concrete device fingerprint, actual app version, fingerprint hash, `finished_at`, success, per-action and per-step outcomes, durations, and a signature. Params, result data, and free-text errors are omitted. The registry reads the signed artifacts into `quality.runs`, including both passed and failed runs.

For iOS recording, provide `--device ios:<udid> --fingerprint /path/to/concrete-fingerprint.json`. The JSON needs concrete `os`, `os_version`, `hardware`, `app_package`, and `app_version` values; version ranges and wildcards are rejected. This runbook's Maps fixture backend supports Android only.

## Independent verification and PR submission

The authenticated GitHub login must differ from the skill author. Verification runs the action again; a self-run log is not promoted into independent evidence. Its artifact lands in the current checkout:

```text
skillhub/ghost/google_maps/verifications/<github-login>-<fingerprint-hash>-<timestamp>.json
```

Preview the submission first. This runs the selected action and writes the artifact, but creates no branch, push, or PR:

```bash
gh api user --jq .login
python3 -m gitd.ghost_cli skill verify ghost/google_maps --action search_place --device "$VERIFY_DEVICE_SERIAL" --param 'query=Brandenburg Gate' --dry-run
```

CI verifies the signature using the PR author's public SSH keys at `https://github.com/<login>.keys`. Before submitting, register the recorder's public key as an SSH authentication key on that same GitHub account. After the first preview has generated the local key, obtain its public half:

```bash
ssh-keygen -y -f "${GHOST_CONFIG_DIR:-$HOME/.ghost}/run-signing-key" > "${GHOST_CONFIG_DIR:-$HOME/.ghost}/run-signing-key.pub"
cat "${GHOST_CONFIG_DIR:-$HOME/.ghost}/run-signing-key.pub"
```

Add that public key in GitHub Settings > SSH and GPG keys > New SSH key, selecting Authentication Key. Keep the private key local. The CI guard requires the signed `verifier` and filename login to match the PR author, refuses self-verification, and checks the signature with the registered keys. Unregistered recorder keys fail that check.

The registry applies the same rule offline: it counts an artifact only when its signature verifies against `skillhub/SIGNERS` (community principals) or `skillhub/verifier-keys.yml` (official and platform principals) for the right principal, the author for `runs/` and the verifier login for `verifications/`. `ghost skill keys --principal <login>` prints the `SIGNERS` line; add it in the same PR as your first artifact. CI accepts a new line only for the PR author's own login and only with a key published on that GitHub account. Tampered payloads, keys not in the trust files, and artifacts copied from another skill directory are rejected and listed under `quality.runs.rejected`.

When ready to submit an independent device run:

```bash
python3 -m gitd.ghost_cli skill verify ghost/google_maps --action search_place --device "$VERIFY_DEVICE_SERIAL" --param 'query=Brandenburg Gate' --push --repo <owner>/<repo>
```

For an emulator, replace the device argument with `--device emulator-5554`. If an installed ref resolves to a different skill version, use `skillhub/ghost/google_maps` in place of `ghost/google_maps` to verify the checked-out version.

Without `--repo`, precedence is `GHOST_HUB_REPO` then the default Android Agent repository. Submission fetches the target's default branch, creates an artifact-only commit and unique branch using a temporary index, pushes to that explicit repository URL, and creates the PR there. It never uses the `origin` remote and leaves your current branch and index untouched. A failed submission retains the local artifact for recovery. PR reviewers/CI must check identity, fingerprint independence, and signature trust.

## Offline fixture replay

This needs no adb, emulator, phone, network, or account. The fixture profile at `tests/fixtures/fake_google_maps/device.json` supplies a fingerprint, XML frames, and a `press_enter` transition from the search box to the place card.

Copy the skill before generating fixture artifacts:

```bash
FIXTURE_SKILL_DIR=$(mktemp -d)
cp -R skillhub/ghost/google_maps "$FIXTURE_SKILL_DIR/google_maps"
GHOST_DEVICE="fake:$PWD/tests/fixtures/fake_google_maps" python3 -m gitd.ghost_cli skill test "$FIXTURE_SKILL_DIR/google_maps" --live --action search_place --param 'query=Fixture Cafe'
python3 -m gitd.ghost_cli skill run "$FIXTURE_SKILL_DIR/google_maps" search_place --device "fake:$PWD/tests/fixtures/fake_google_maps" --param 'query=Fixture Cafe' --record
```

An explicit `--device` wins over `GHOST_DEVICE`, then `DEFAULT_DEVICE`. Fake operations are logged in memory; unsupported operations fail rather than falling back to adb. Fake artifacts have `simulation: true` and `device_backend: fake`. The registry rejects them as evidence (reason `simulated`), so they are safe to keep for local debugging and never confer points.

The automated end-to-end fixture tests execute the real runner, migrated adapter, action, and validator, verify the SSH signature, and assert the resulting registry `quality.runs` counts:

```bash
python3 -m pytest tests/test_skill_cli_fake_device.py -q
```

## CI emulator run

A maintainer can request an optional emulator recording by adding the `skill-emulator` label to a skill submission PR after reviewing its current head commit. Use the PR's Labels control, or `gh pr edit <number> --add-label skill-emulator`. The workflow runs on `pull_request`; the submission detector must identify at least one changed skill. Adding the label triggers the job, and later commits rerun it while the label remains. Remove and reapply the label to request another run, and remove it when review is complete.

The `emulator` job has `continue-on-error: true`. Keep it out of required branch protection checks. It uses an Android API 35 Google Play x86_64 emulator with a Pixel 6 profile and records the migrated Play Store launch action without signing into a Google account:

```sh
ghost skill run skillhub/ghost/play_store open_store --device emulator-5554 --record
```

The recording helper retries a failed action once and collects fresh `runs/*.json` files from this invocation. The Actions run uploads them as the `skill-emulator-play-store-runs` artifact, including recorded failures. Existing PR run files and symlinks are excluded; the temporary signing private key is outside the uploaded directory.

Download the artifact from the Actions run's Artifacts area. Review the recorded skill and action, device fingerprint, app version, steps, success result and SSH signature. These are signed self-run records for this smoke action and emulator fingerprint. Inspect the job logs when the emulator fails to boot or no fresh JSON is produced; an early device or fingerprint failure can leave no artifact. The job uploads evidence for review without committing records back to the repository.
