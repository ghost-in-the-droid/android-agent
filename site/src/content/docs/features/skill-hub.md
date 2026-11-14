---
title: "📦 Skill Hub"
description: The registry of Ghost skills. One folder per author in the hub repo, versioned by git tags, installed from an immutable CDN, with separate trust and quality badges.
---

The **Skill Hub** is where Ghost skills are published, found and installed. The hub repo itself is the registry: every skill is a folder under `skillhub/<author>/<slug>/`, every release is a git tag, and a generated `registry.json` indexes them. There is no separate account or upload service; GitHub identity and pull requests do the work.

Browse it at [ghostinthedroid.com/skills/](/skills/).

---

## Layout

```
skillhub/
├── ghost/                         official namespace (maintainers only)
│   ├── tiktok/
│   └── google_maps/ ...
├── <author>/<slug>/               community skills, one folder per GitHub handle
│   ├── skill.yaml                 the skill (Schema v2)
│   ├── README.md   SOFT.md        docs for people and for adapting agents
│   ├── helpers.py                 optional python_action targets
│   ├── runs/                      signed self-run evidence (ghost skill run --record)
│   └── verifications/             signed independent runs (ghost skill verify)
├── registry.json                  GENERATED discovery index, never hand-edited
└── registry/index/<author>.<slug>.json   per-skill release history
```

`registry.json` lists every skill with its trust, status, quality and per-version files (each with a sha256). The per-skill index file records each release: version, tag, commit, the git tree hash of the skill folder (the integrity pin), the release tarball sha256 and the attestation. Both are written by `tools/build_registry.py`; CI regenerates them on every merge.

A version is the git tag `<author>/<slug>-v<semver>`, created only by the release workflow.

---

## Installing

```bash
ghost skill search whatsapp                 # name, description, actions, package; --json for scripts
ghost skill info ghost/tiktok               # trust, tier, versions, actions, fingerprint
ghost skill install ghost/tiktok            # latest release
ghost skill install alice/whatsapp-messaging@1.1.0
ghost skill list                            # what is installed, with version and trust
ghost skill outdated                        # installed skills with a newer release
ghost skill update --all
ghost skill uninstall alice/whatsapp-messaging
```

The installer reads `registry.json`, then downloads every file of the chosen version pinned to its commit or tag and checks each sha256 before writing anything. Files come from jsDelivr at the immutable tag first, and from the signed GitHub Release tarball second. They are never fetched from `raw.githubusercontent.com`, which rate-limits without warning. Skills land in `~/.ghost/skills/<author>/<slug>/<version>/` (override with `GHOST_SKILLS_DIR`).

Every skill page on the site shows the install command, built from registry data rather than from the README.

---

## Two badges: trust and quality

Every skill carries two separate badges. They answer different questions and never stand in for each other.

**Trust** says who published the skill and how it got into the hub. The author never sets it; the registry assigns it from where the skill lives.

| Trust | Where it comes from | Install |
|---|---|---|
| **Official** | `skillhub/ghost/*`, maintained by the Ghost team | Silent |
| **Verified** | A community folder, merged through a reviewed PR | Prints "Community skill by @author" |
| **Unverified** | `ghost skill install --url <git-url>` outside the hub repo | Warns that the skill contains Python that will run on your machine and phone, and asks before installing (`--yes` to accept) |
| **Quarantined** | Flagged by the registry | Blocked unless `--force` |

**Quality** says whether the skill works and how well it is documented. It is a five-rung ladder: **Draft, Runs, Proven, Hardened, Reference**. A skill moves up only with evidence: signed self-runs, independent runs on other devices, validators, docs, and freshness. Downloads and likes are shown but are worth zero points. The full formula is public on the [scoring page](/skills/scoring/), and the [leaderboard](/skills/leaderboard/) ranks skills by it.

A success rate appears only once a skill has 20 recorded runs. Until then the page says "not enough runs", so a handful of lucky passes cannot rank a skill.

---

## Skill status

`skill.yaml` can declare a lifecycle `status:`:

| Status | Meaning | On the hub |
|---|---|---|
| `active` (default) | Works as described | Listed normally |
| `blocked` | Cannot finish on its own right now, for example a mandatory phone check | Grey **Blocked** badge, hidden from the default browse and leaderboard until "Show blocked" is on; install still works and prints a warning |
| `deprecated` | Scheduled for removal | **Deprecated** badge; install prints a warning |

Any other value is a validation error.

---

## Evidence: record, verify, submit

Quality points attach only to signed run artifacts.

```bash
# Your own run: writes a signed artifact to the skill's runs/ folder
ghost skill run skillhub/alice/whatsapp-messaging send_msg --device <serial> --record \
    --param contact_name=Mom --param message="Running late"

# Someone else's skill on your device: writes to verifications/ and previews a PR
ghost skill verify alice/whatsapp-messaging --device <serial>
ghost skill verify alice/whatsapp-messaging --device <serial> --push   # actually opens the PR
```

`--record` captures a concrete device fingerprint (OS, hardware, app version and so on) and signs the result with a local Ed25519 SSH key that Ghost creates on first use. The signature proves the artifact was not edited afterwards. It does not prove who you are; reviewers and CI check account and device independence.

`ghost skill verify` refuses to run under the skill author's own GitHub account, because a self-run never counts as independent. Without `--push` it only prints the PR it would open. With `--push` it commits just the artifact on a fresh branch of the target repo (`GHOST_HUB_REPO`, or `--repo owner/repo`) and opens the PR, without touching your checkout.

Maintainers can also ask CI for a recording: the `skill-emulator` label on a submission PR starts an optional emulator job that records a smoke action and uploads the signed run for review; it is never a required check (see the [verify runbook](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/skills/verify-runbook.md#ci-emulator-run)).

`ghost skill submit <path> --dry-run` prints the PR title, branch, file list and body for a new skill, after running the static analyzer. The submission CI runs `validate`, `analyze` and `lint` and posts one results comment; see [Publishing Skills](/skills/publishing/).

---

## Telemetry

Telemetry is off by default and opt-in only.

```bash
ghost telemetry status
ghost telemetry on      # saves consent and a random, rotatable install id
ghost telemetry off     # turns it off and deletes the id
```

Even when it is on, Ghost sends an event only from `ghost skill run --record`, after the signed artifact is written, and only if `GHOST_TELEMETRY_ENDPOINT` is set to an HTTPS endpoint. No endpoint ships enabled, so by default nothing leaves your machine. `DO_NOT_TRACK=1` always wins over consent, and `GHOST_TELEMETRY_DEBUG=1` prints the event instead of sending it. Live tests and `verify` never send events, and a failed delivery (two-second timeout, no retry) never fails your run.

Telemetry is display only: it never adds quality points or moves a tier, which come solely from signed run and verification artifacts. An event holds seven categorical fields: schema version, skill id, app version, passed or failed, OS, real or fake device, and the install id. No action names, params, results, errors, screen content, serials, logins or timestamps. The collector rejects anything else. The exhaustive list is in the [public field list](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/telemetry.md). Counts from it feed a skill's success rate, which is shown only from 20 runs, per app version.

---

## Phone links and QR codes

Each skill page shows a QR code. It encodes an Android App Link of the form `https://ghostinthedroid.com/skills/install/<author>/<slug>@<version>`. With the Ghost app installed and the link verified, the phone opens the skill in the app; without it, the link lands on a web page with the install command. A `ghost://install/<author>/<slug>` link sits next to the QR as a fallback for phones where the App Link is not verified yet.

Verification needs `/.well-known/assetlinks.json` on the hub domain. The site serves it already; it holds placeholder values until the release signing certificate is filled in.

---

## Related

- [Scoring](/skills/scoring/): the public quality formula
- [Publishing Skills](/skills/publishing/): PR flow and review
- [Creating Skills](/skills/creating-skills/): author guide
- [Skill System](/features/skill-system/): architecture
- [Validate a skill.yaml](/skills/validate/): in-browser schema check
