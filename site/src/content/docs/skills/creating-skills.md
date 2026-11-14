---
title: "🔨 Creating Skills"
description: Author a Ghost skill end-to-end. Scaffold or import, edit skill.yaml, add helpers, validate and lint, test in dry and live mode, record a signed run, submit as a PR.
---

The **highest-impact contribution** to Ghost is adding skills for real apps. Every new skill turns your one-time authoring effort into $0-per-invocation replays for everyone else on your fingerprint.

This page walks the full loop.

---


### Toolkit shape

Author an app toolkit with **one entry action**, **3–6 focused primitives**, and
**one read-state action** that returns visible structured data. Add actions beyond
that range only when the app needs distinct operations; this is an authoring rule,
not a schema-enforced action limit. Entry opens or resets the demo app; primitives
perform one operation; read-state observes without opening unrelated apps or
changing user data. Reuse the toolkit across prompts instead of embedding one
benchmark task in a single long action.

Include a **Toolkit** table in README with each action's role, parameters, returned
data and side effects. Document honest limits and the tested app/device scope.
Record every action three times after the final definition-file edit; editing
README, SOFT.md, helpers.py or skill.yaml changes the content digest. Prior runs
remain historical evidence and do not verify the new files.

For Android Python helpers, share the engine APIs instead of copying parsers or
launching a separate ADB process:

```python
from gitd.skills.engine.nodes import parse, by, centre

nodes = parse(device.dump_xml())
rows = by(nodes, "id", "com.example:id/row")
# centre(rows[0]) returns coordinates; it does not tap.
png = device.screencap_png()  # PNG bytes, transport errors and package policy checked
```

The node helpers preserve document order and raw XML attribute entities, reject
invalid/off-screen bounds, and use exact selectors. Decode display text explicitly
when needed. The screenshot API is Android-specific. Adopting either API in an
existing recorded skill requires fresh content-bound runs after its final edits.

## The flow

```bash
ghost skill scaffold <user>/<slug> --app <package> --actions <a,b>   # 1. create skillhub/<user>/<slug>/
# ... edit skill.yaml, helpers.py, SOFT.md, README.md ...
ghost skill validate <path>                                         # 2. schema + import checks
ghost skill lint <path>                                             #    stricter authoring checks
ghost skill analyze <path>                                          #    security scan of your Python
ghost skill test <path> --live --device <serial>                    # 3. run on a device
ghost skill run <path> <action> --record --device <serial>          # 4. signed self-run
ghost skill demo <path> <action> --mode hard --device <serial> --render-host <host>
ghost skill submit <path>                                           # 6. PR
```

Already have a flow somewhere else? Start from [Import](#import-from-maestro-or-automate) instead of scaffold. Have a v1 skill? See [Migrate](#migrate-a-v1-skill).

---

## 1. Scaffold

```bash
ghost skill scaffold alice/whatsapp-messaging \
    --app com.whatsapp \
    --skill-class hard \
    --actions send_msg,check_inbox,reply_last
```

Creates:

```
skillhub/alice/whatsapp-messaging/
├── skill.yaml       ← action stubs, license + generated_with placeholders
├── helpers.py       ← python_action target stubs, one per action
├── SOFT.md          ← narrative template, one section per action
└── README.md        ← template
```

v2 skills are flat: one `helpers.py` next to `skill.yaml`.

---

## 2. Edit skill.yaml

```yaml
name: whatsapp-messaging
version: 1.0.0
author: alice
license: MIT
generated_with: "hand-written"        # or the model/tool that helped
skill_class: hard
status: active                        # active | blocked | deprecated
data_access: [contacts, notifications]
side_effects: [sends_message]
destructive: false
tos_risk: low
locale: [en-US]

fingerprint:
  os: android
  os_version: ">=14"
  hardware: "samsung-s24"
  app_package: com.whatsapp
  app_version: ">=2.24.15"

popup_detectors:
  - {detect: "Allow WhatsApp", button: "Allow"}
  - {detect: "Not now", button: "Not now", label: "Update nag"}

subroutines:
  - name: open_chat_list
    steps:
      - {action: launch_app, package: com.whatsapp}
      - {action: wait_for_element, desc: "Chats"}

actions:
  - name: send_msg
    description: "Send a text to a contact by name"
    ref_prompt: "Text John Smith saying I'm running late"
    params:
      - {name: contact_name, type: str, required: true}
      - {name: message, type: str, required: true}
    steps:
      - subroutine: open_chat_list
      - {action: tap_element, id: search_button}
      - {action: type_text, text: "{contact_name}"}
      - {action: wait_for_text, text: "{contact_name}", timeout_s: 5}
      - {action: tap_element, text: "{contact_name}"}
      - {action: type_text, text: "{message}"}
      - {action: tap_element, desc: Send button}
    end_state_validator:
      all_of:
        - {kind: text_visible, text: "{message}"}
        - {kind: element_present, desc: message_sent_check}
    test_case:
      ref_prompt_variants:
        - "text mom I'll be home late"
        - "message Jane about the meeting"
      expected_success: true
```

Every action needs `ref_prompt`, typed `params`, `steps`, an `end_state_validator` and a `test_case`. The Proven tier needs at least 3 step-level validators, so write them as you go.

Manifest fields new in v1.6.0:

| Field | Required | Meaning |
|---|---|---|
| `license` | yes | SPDX id; MIT matches the repo |
| `generated_with` | yes | How the skill was authored. AI help is fine; say so. |
| `status` | no (default `active`) | `blocked` = cannot complete on its own today; `deprecated` = being retired |
| `side_effects` | no | `sends_message`, `posts_content`, `makes_payment`, `modifies_account`, `deletes_data`, `none` |
| `destructive` | no | `true` needs a `checkpoint` confirmation step or dry-run support |
| `tos_risk` | yes (the hub build refuses a skill without it) | `low`, `medium`, `high` |
| `locale` | no | BCP-47 list you tested in |
| `fingerprint.screen_wxh`, `density`, `locale`, `theme` | no | Extra matrix fields |

Paste a `skill.yaml` into the [online validator](/skills/validate/) for instant schema feedback.

---

## 3. Edit helpers.py

Anything YAML can't express (custom OCR, media prep, complex checks) goes in `helpers.py`. Python is welcome, with one consequence: CI will not run a skill with submitter Python on its emulator until a maintainer has read the code (Tier 2 in the [security policy](https://github.com/ghost-in-the-droid/android-agent/blob/main/docs/skillhub/security.md)). A YAML-only skill for an allowlisted app runs straight away. Helpers must not make network calls, touch secrets or be obfuscated; those PRs are rejected.

```python
from gitd.skills.base import ActionResult

def check_contact_online(device, params, context) -> ActionResult:
    """python_action target: verify contact status via a11y scrape."""
    xml = device.dump_xml()
    if 'online' in xml.lower():
        context.result['contact_online'] = True
        return ActionResult(success=True, data={'online': True})
    return ActionResult(success=False, error="Contact not online")
```

Return a plain payload dict, such as `{"count": 5}`, to merge its fields into `context.result`. `ActionResult(success=True, data=payload)` and `{"success": True, "data": payload}` are also supported. Dict keys `success`, `error` and `data` identify a result envelope: if your payload uses those names, put it under `data`. A result with `success=False` fails the step.

Reference it as `<file>:<function>`, relative to the skill directory:

```yaml
steps:
  - python_action: "helpers:check_contact_online"
```

The engine loads the file by path, so the skill works wherever it is installed. Dotted module paths such as `gitd.skills.*` are rejected.

Custom validators work the same way:

```python
def message_delivered(device, context) -> bool:
    return 'delivery_status_read' in device.dump_xml()
```

```yaml
end_state_validator:
  all_of:
    - {kind: custom_python, function: "helpers:message_delivered"}
```

---

## Checkpoints (gates and confirmations)

A `checkpoint` step pauses for a human, for a CAPTCHA, a code from outside the phone, or a confirmation before something destructive:

```yaml
- checkpoint:
    reason: captcha          # captcha | sms | email | login | llm_decision | generic
    prompt: "Solve the CAPTCHA on the phone, then resume."
    success: {kind: text_visible, text: "Welcome"}
    timeout_s: 600           # default 600; 0 waits forever
```

The engine publishes `reason` and `prompt`, then waits until a human resumes or aborts, or until the `success:` validator passes. A timeout raises `CheckpointTimeoutError`, an abort `CheckpointAbortedError`; neither triggers the automatic retry. A checkpoint with no way to be resumed and no `success:` is skipped. From the dashboard or MCP, resume or abort a waiting run with `POST /api/skills/runs/{id}/resume`.

---

## Ask (a human or an agent answers mid-run)

An `ask` step collects one typed answer and stores it in `{context.<store_as>}` for later steps:

```yaml
- ask:
    who: parent_agent          # human | parent_agent | sub_agent
    prompt: "Which contact did the user mean?"
    attach: [screenshot, a11y, {params: [query]}]
    schema: {type: enum, values: [first, second]}   # str | int | enum | json
    store_as: selection
    timeout_s: 0               # 0 waits forever
    fallback: fail             # or {value: first}
```

- **`human`** answers through the same channel as checkpoints (dashboard or MCP).
- **`parent_agent`** pauses the run: it returns `status: needs_input` with a `resume_token`, the prompt, attachments and schema. The calling agent answers with the MCP tool `run_skill_resume(token, answer)` or `ghost skill resume <token> --answer '<json>'` (see [Using Skills](/skills/using-skills/#answering-an-ask)).
- **`sub_agent`** asks a bounded Claude Code call (tools off, three turns at most) and uses the fallback when none is available.

Answers are validated strictly against `schema`. An ask without `fallback: {value: ...}` makes the run gated (the legacy schema calls it `skill_class: soft`), and agent asks mark the skill as spending tokens at replay. Dry runs use the fallback or a typed placeholder. Traces and signed run artifacts record who answered and how long it took, never screenshots.

---

## 4. Validate, lint, analyze

```bash
ghost skill validate skillhub/alice/whatsapp-messaging
```

About a second, no device: Schema v2 conformance, required fields (including `license` and `generated_with`), every `python_action` and `custom_python` reference resolves, known step types, parseable fingerprint, `SOFT.md` and `README.md` present.

```bash
ghost skill lint skillhub/alice/whatsapp-messaging
```

Stricter: unused or undeclared params, TODO prompts, duplicate prompt variants, missing `SOFT.md` sections per action, coordinate taps without a note, steps after a terminal HOME press. Exit 1 on errors, 0 with warnings.

```bash
ghost skill analyze skillhub/alice/whatsapp-messaging
```

AST review of every `.py` file (signals for a human reviewer, not a sandbox): shell and process execution (`os.system`, `os.popen`, `subprocess.*`, `os.exec*`), `eval`/`exec`/`compile`/`__import__`, dynamic imports (`importlib`, `runpy`), `ctypes`, raw sockets, network calls outside `gitd.http`, writes outside the skill dir through `open`, `Path.write_*`, `shutil` or `os` (unknown destinations are flagged too), non-literal `getattr`/`setattr`, long encoded blobs, and every raw `device.adb` / `device.shell` call. Exit 2 on a high finding; medium findings add the `needs-security-review` label. CI runs the same scan on your PR.

---

## 5. Test

**Dry mode** (no device): parses and resolves everything; in a run, checkpoints resolve immediately and other steps are reported as skipped.

```bash
ghost skill test skillhub/alice/whatsapp-messaging
```

**Live mode** runs on a connected device:

```bash
ghost skill test skillhub/alice/whatsapp-messaging --live --device <serial>
ghost skill test skillhub/alice/whatsapp-messaging --live \
    --action send_msg --param contact_name=John --param message="hey" --device <serial>
```

---

## 6. Record a signed run

```bash
ghost skill run skillhub/alice/whatsapp-messaging send_msg \
    --param contact_name=Me --param message="test" --record --device <serial>
```

Writes `runs/<fingerprint-hash>-<timestamp>.json`, signed with your local key (`~/.ghost/run-signing-key`). It counts toward Runs only once that key is listed for your author name in `skillhub/SIGNERS` (`ghost skill keys --principal <you>` prints the line; add it in your first PR). Fake-device runs are flagged `simulation: true` and never count. Commit it with the skill. A README plus one self-run takes the skill to **Runs**.

---

## 7. Submit

```bash
ghost skill submit skillhub/alice/whatsapp-messaging --dry-run
```

Prints the PR title (`[skill] alice/whatsapp-messaging v1.0.0`), branch (`skill/alice-whatsapp-messaging`), file list and body (actions, fingerprint, data access, Python, bench, demo, checklist). Add `--push` (needs `gh auth login`) to fork the hub, push `skill/alice-whatsapp-messaging` and open the PR. See [Publishing Skills](/skills/publishing/).

---

## Import from Maestro, Automate or AndroidWorld

```bash
ghost skill import --maestro flow.yaml [--out skillhub/<you>/<slug>]
ghost skill import --automate flow.flo [--out skillhub/<you>/<slug>]
ghost skill import --androidworld <android_world checkout> [--out skillhub/androidworld] [--force]
```

- **Maestro**: `launchApp`, `tapOn` (text or id), `inputText`, absolute-coordinate `swipe`, `back` and `assertVisible` map straight to v2 steps.
- **Automate**: structured JSON exports with straight-line flows (app start, interact, input text, delay, back, swipe, assert visible); one action per flow.

Anything that does not map becomes a commented TODO step, with the original payload kept under `import_unmapped` and a lint warning, so nothing is silently lost. The source file is copied byte for byte. Native binary `.flo` files and branching graphs need manual translation. Output defaults to `skillhub/local/<source-name>/` and never overwrites an existing directory. Imported skills are scaffolded with `license` and `generated_with` set.

**AndroidWorld**: reads a `google-research/android_world` checkout statically (nothing is executed) and writes one draft skill per app (`skillhub/androidworld/<app>/`, author `androidworld`), one action per benchmark task. AndroidWorld defines goals and evaluators, not UI steps, so each action gets its `ref_prompt` and params from the task template, a single TODO step, and an `end_state_validator` pointing at a `validators.py` stub that documents the upstream evaluator and returns False until you port it. Skills land as `status: draft`, `license: Apache-2.0` (upstream license copied, attribution in the README) and `generated_with: ghost skill import --androidworld`. Re-running only rewrites skills that still carry the generated marker unless you pass `--force`.

---

## Migrate a v1 skill

```bash
ghost skill migrate path/to/v1-skill [--author <github-login>] [--dry-run]
```

Reads the v1 classes statically (nothing is imported), appends a v2 block to `skill.yaml` between markers, writes a `helpers.py` adapter that runs the v1 code unchanged, and generates a `SOFT.md` with one section per action. Running it again changes nothing. If the result does not validate, the files are rolled back and the skill is reported as legacy with a reason. All eight v1 official skills were migrated this way.

---

## LLM-driven authoring (planned)

`ghost skill mine <path> --action <name> --ref-prompt "..."` will run an agent on the app, record the trace and write the steps, validator and popup detectors for you. It is not implemented in v1.6.0. Until then, drive the phone with your agent of choice, then turn the trace into steps by hand, and set `generated_with:` accordingly.

---

## Best practices

- **Locators**: prefer `desc:` (content-desc, most stable) over `id:` (changes between builds) over `text:` (locale-dependent) over coordinates (only for known-stable landmarks, with a `note:`).
- **Waits**: `wait_for_element` / `wait_for_text`, not `sleep`.
- **Popup catalog**: grow it from what you hit; `UnknownPopupError` screenshots show you what to add.
- **Subroutines**: if 3+ actions share a preamble, extract it.
- **Idempotency**: actions should be safe to re-run.
- **Honest manifest**: `data_access`, `side_effects`, `destructive`, `tos_risk` and `generated_with` drive the hub badges and what users see before installing.

---

---

## 8. Icon and per-action demos

**Icon.** Put a 96 px `icon.webp` (16 KB or less) next to `skill.yaml`; the loader picks it up automatically, or point `icon:` at another file. Hub cards, skill pages and demo posters use it. `python3 tools/fetch_app_icons.py` fetches the store icon from Google Play or F-Droid for the skill's `app_package`; AOSP system apps without a store listing fall back to a glyph.

**Per-action demos.** One clip per action lives at `demos/<action>.webm` (or `.mp4`, `.gif`), next to a `demos/<action>.spec.yaml` that makes it reproducible. Clips must be 30 seconds or less and 3 MB or less (a warning starts at 1.5 MB). `demos/` holds files only; anything not named after an action fails `validate`. The skill page shows one click-to-play tab per action, never autoplay. A top-level `demo:` picks the default clip; otherwise the first action's clip is used. A demo earns docs points: 3 for any demo, 2 more when every action has one.

**`demo_params`.** Give each action a `demo_params:` map so recording needs no flags and shows values that look good on screen, without touching private data:

```yaml
- name: convert_units
  demo_params: {category: Temperature, value: "100", from_unit: Fahrenheit, to_unit: Celsius}
```

`--param k=v` on the command line overrides them.

### Record with `ghost skill demo`

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

The terminal is 60 columns and the final long side defaults to 720 pixels. Use
`--phone-offset` to compensate startup lead (default 3 seconds, 0 when aligned),
`--record-size WxH` for phone capture, and `--layout phone` for a phone-only clip.
`--out` selects a custom WebM path for one action. A folder above 10 MB warns.
`--actions a,b` records a subset in that order; omit the selector for every action.
Parameters interpolate the action's `ref_prompt`; `--prompt` overrides that phrase.
The configurable subheader opens the captions and the outro installs the real skill.

Capture uses a local asciinema cast; phone capture and every encoding step run on
`--render-host` (or `GHOST_DEMO_RENDER_HOST`). `--render-root` and `--render-python`
select the remote checkout and Python environment. Both checkouts need the current
recorder scripts and must have synchronized clocks. The local MCP server reaches
the render host's adb server via `ADB_SERVER_SOCKET`; the device serial is passed
through environment variables, keeping it out of the displayed replay command.
Only a verified clip and metrics are copied back; temporary capture files are cleaned up.

Use a clean demo device. Physical phones with accounts or unknown account state
require `--i-know`. Prepare the private identifier list described in
`scripts/privacy/RECORDING_CHECKLIST.md`. `--no-ocr` requires manual privacy review.
Legacy `--agent` modes remain available for older scripts; use explicit `--mode`
for the hard replay or notes-driven soft workflow described here.

---

## Related

- [Publishing Skills](/skills/publishing/): PR flow, CI, verification
- [Contribute](/skills/contribute/): the contributor ladder
- [Execution Engine](/features/skill-execution-engine/): runtime and primitives
- [API Reference](/api/skill-classes/): full YAML spec
