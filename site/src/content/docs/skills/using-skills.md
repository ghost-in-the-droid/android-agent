---
title: "⚡ Using Skills"
description: Install skills from the hub, run them via ghost skill run, record signed runs, verify other people's skills, and combine them with any MCP client.
---

## Your first skill

After [Hello World](/getting-started/hello-world/), install and run one skill from the hub. `ghost/calculator` is a good first one: low risk, no account, one required parameter.

```bash
ghost skill install ghost/calculator
ghost skill run ghost/calculator calculate --param expression='1234*5' --device <serial>
# → the result string from the calculator display (6170)
```

Then look at what you ran: `ghost skill info ghost/calculator` shows its trust, quality tier, actions and the device it was tested on. How that tier is earned is explained on [How skills are scored](/skills/scoring/).

---

## Install

```bash
pip install ghost-in-the-droid>=1.6.0   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`

ghost skill search maps                    # search the hub registry
ghost skill find "share my location"      # rank skill actions for an intent (installed, checkout, hub)
ghost skill info ghost/google_maps         # trust, quality, versions, actions, fingerprint
ghost skill install ghost/google_maps      # latest version
ghost skill install alice/foo --yes            # non-official installs print an install card (has_python, data_access, side_effects, tos_risk, tested-on); a community skill with Python needs --yes or a y/N the first time
ghost skill install alice/keep-checklist@1.0.0   # a pinned version
ghost skill list                           # installed skills with version, trust and path
```

Installed skills live in `~/.ghost/skills/<author>/<slug>/<version>/` (set `GHOST_SKILLS_DIR` to move it). Several versions can sit side by side.

**Where installs come from.** The client reads the hub's `skillhub/registry.json`, then downloads each file from jsDelivr at a pinned revision, falling back to the signed GitHub Release tarball. It never fetches from `raw.githubusercontent.com`. Every file is checked against the sha256 in the registry before anything is written.

**What the installer asks you.**

| Situation | What happens |
|---|---|
| Official or Verified skill | Installs silently (Verified prints "Installing verified community skill by @author") |
| `--url <git-url>` outside the hub | Unverified: warns that the skill contains Python, asks y/N; `--yes` accepts |
| Quarantined | Refused; `--force` overrides with a warning |
| `status: blocked` | Installs, with a warning that it cannot complete on its own today |
| `status: deprecated` | Installs, with a warning to look for a replacement |
| Legacy v1 skill | Refused, with a hint to run `ghost skill migrate` |

Keep skills current:

```bash
ghost skill outdated                 # installed vs latest
ghost skill update ghost/tiktok      # or --all
ghost skill uninstall ghost/tiktok
```

---

## Run

```bash
ghost skill run <skill-ref-or-path> <action> [--param k=v ...] --device <serial>
```

Examples:

```bash
# Read-only action, no params
ghost skill run ghost/tiktok get_active_account --device <serial>
# → {"handle": "<your_handle>"}

# Parameterized action
ghost skill run ghost/tiktok upload_video \
    --param video_path=/sdcard/DCIM/clip.mp4 \
    --param caption="look at this" \
    --param hashtags='["cat","fyp"]' \
    --param action_mode=draft \
    --device <serial>
```

The runner prints `✓` + duration + returned data on success, or a full trace + error hint on failure.

### Record a signed run

```bash
ghost skill run <path> <action> --record --device <serial>
```

`--record` writes `runs/<fingerprint-hash>-<timestamp>.json` into the skill directory: device fingerprint, app version, per-step outcome, duration, and an SSH Ed25519 signature over the canonical JSON. Your params, results and error text are left out. The signing key is created on first use at `~/.ghost/run-signing-key` (or under `GHOST_CONFIG_DIR`). iOS recordings need `--fingerprint <file.json>`.

A self-run is what takes a skill from Draft to **Runs**.

### Verify someone else's skill

```bash
ghost skill verify <author>/<slug>[@version] --device <serial>          # preview (default)
ghost skill verify <author>/<slug>[@version] --device <serial> --push   # open the PR
```

`verify` runs the skill, writes a signed `verifications/<your-login>-<fingerprint-hash>-<timestamp>.json`, and by default only prints the PR it would open. `--push` commits just that artifact on a new branch, pushes it, and opens the PR with `gh`. `--repo owner/repo` (or `GHOST_HUB_REPO`) picks the target. Verifying your own skill is refused.

The registry counts an artifact only when its signature verifies against `skillhub/SIGNERS` (run `ghost skill keys --principal <you>` for your line; fake-device runs never count). CI checks the artifact's signature against the SSH keys on your GitHub account, so add `~/.ghost/run-signing-key.pub` to your GitHub SSH keys once before your first `--push`. A failing run is evidence too: submit it.

One accepted independent run on a different device is what takes a skill to **Proven**.

---

## From an MCP client

Every action is exposed through the MCP tool `run_skill`, so Claude Code, Cursor, Codex and custom LangChain agents all get the same surface.

```
run_skill(name="ghost/tiktok", action="get_active_account", params={})
# → {"handle": "<your_handle>"}

run_skill(name="ghost/tiktok", action="switch_account", params={"handle": "<other_handle>"})
```

The client picks the action by matching your prompt against each action's `ref_prompt`.

### Answering an ask

Some skills pause mid-run to ask the calling agent a question (an `ask` step with `who: parent_agent`). Instead of a result, `run_skill` then returns:

```
{"status": "needs_input", "resume_token": "<token>", "prompt": "Which contact did the user mean?",
 "schema": {"type": "enum", "values": ["first", "second"]}, "attachments": {...}}
```

Answer with the MCP tool `run_skill_resume`, passing the answer as JSON text:

```
run_skill_resume(token="<token>", answer="\"first\"")
```

or from a shell:

```bash
ghost skill resume <token> --answer '"first"'
```

The answer is validated against the schema. An invalid answer is rejected and the token stays usable; a valid one consumes the token and the run continues on the same device. Paused state is stored privately under `~/.ghost/runs/`. Questions for a human (`who: human`) appear on the dashboard like a checkpoint instead.

---

## Test a skill

```bash
ghost skill test <path> [--live] [--action <name>] [--param k=v] [--device <serial>]
```

**Dry mode** (default): schema and import checks, about a second, no device:

```bash
ghost skill test skillhub/alice/whatsapp-messaging
# ✓ skill.yaml parses + validates Schema v2
# ✓   name: whatsapp-messaging v1.0.0 (hard)
# ✓   actions (2): ['send_msg', 'reply_last_msg']
# ✓ all python_action + custom_python refs resolve
```

**Live mode** runs each action on the device:

```bash
ghost skill test skillhub/alice/whatsapp-messaging --live --device <serial>
# ── running send_msg ──
# ✓ send_msg (14512ms): {"delivered": true}
# ── running reply_last_msg ──
# ✗ reply_last_msg (22013ms): TimeoutError_: wait_for_text('Read') exceeded 15s
```

`test --live` does not write run artifacts; use `run --record` for evidence.

---

## Telemetry (opt-in, off by default)

```bash
ghost telemetry status
ghost telemetry on      # saves consent and a random, rotatable install id
ghost telemetry off     # turns it off and deletes the id
```

Telemetry is off unless you turn it on, and `DO_NOT_TRACK=1` always wins. With it on, only `ghost skill run --record` sends an event, and only when `GHOST_TELEMETRY_ENDPOINT` is set; no endpoint is configured by default, so out of the box nothing is sent. Set `GHOST_TELEMETRY_DEBUG=1` to see the exact event printed instead of sent.

The event is seven categorical fields (schema version, skill, app version, passed or failed, OS, real or fake device, install id). It carries no params, results, error text, screen content, serials or account names. See the [public field list](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/telemetry.md).

---

## Benchmark a skill (planned)

`ghost skill bench <ref> --androidworld <Task> --bridge-cmd "<cmd>"` exists today: it replays the skill on an AndroidWorld emulator and lets AndroidWorld's own evaluator judge it (results in `bench/androidworld.json`, display only). The agent arms are planned: `ghost skill bench <path> --action <name> --brain <model>` will run an action's first prompt variant once without the skill and once with it and record steps, tokens and wall time in `bench.yaml`. It is not implemented in v1.6.0. You can still hand-write `bench.yaml` entries from your own runs; they are trust-on-honesty.

---

## List engine primitives

```bash
ghost skill list-registered      # every step type and validator kind the engine supports
```

---

## Related

## Next

- **[Creating Skills](/skills/creating-skills/): scaffold, edit, test your own** (next in the path)
- [Publishing Skills](/skills/publishing/): PR flow and verification
- [How skills are scored](/skills/scoring/): tiers, points, and a worked example
- [Contribute](/skills/contribute/): the contributor ladder
- [Skill System](/features/skill-system/): architecture
