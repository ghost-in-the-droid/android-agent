# Recording a Showcase Demo

The showcase pipeline is "Ghost records Ghost": a spec-driven recorder drives
a real phone with Ghost's own adb primitives while capturing the terminal and
the phone screen in sync, then composites a branded WebM.

## Skill hub videos: `ghost skill demo`

From a source checkout (`pip install -e .`), use the first-class wrapper:

```bash
ghost skill demo ghost/calculator calculate --mode hard --device <device> --render-host <render-host>
ghost skill demo ghost/calculator calculate --mode soft --device <device> --render-host <render-host> --max-tokens 12000
ghost skill demo ghost/calculator calculate --mode hard --device <device> --dry --title "Calculator in action"
```

This extends the original `scripts/record_demo.py` pipeline; it does not synthesize
a terminal. Hard mode runs `ghost skill run` through asciinema. Soft mode records a
real Claude Code TUI (with replay tools and built-in shell tools withheld) through `scripts/showcase/claude_tui_driver.py`, using its sample
prompt and `get_skill_notes`, the Haiku model alias, a response output cap and a
per-clip transcript token budget. The driver counts input, output and cached tokens
per unique message and stops at the threshold. A response in flight may cross it.
Authentication failure stops soft mode; it never silently replays a hard action.

Terminal capture stays local; phone capture, agg and ffmpeg run on `--render-host`.
The original `_brand/asciinema-ghost.json` theme and `_brand/frames.json` are reused.
Both checkouts must have the current scripts and Pillow/pexpect installed, plus the
tools listed below. The sample demo app must be installed as a non-system app on a
clean demo device. Its data is erased on every recording: force-stop, `pm clear`,
app-scoped seed broadcasts, HOME, start capture, launch. System and absent packages
are refused. With no seeds, the empty app state is the sample state.

`--spec spec.yaml` accepts:

```yaml
cards:
  header: GHOST IN THE DROID
  eyebrow: SKILL SHOWCASE
  title: Calculator in action
  byline: "@ghost"
  subheader: "ghost/calculator: calculate"
  outro_title: ghost/calculator
  outro_cmd: ghost skill install ghost/calculator
  outro_url: https://ghostinthedroid.com/skills/ghost/calculator/
# Optional fixture receiver implemented by the demo app (always package-targeted):
seed:
  - action: org.example.demo.SEED
    extras: {fixture: showcase}
```

All eight strings also accept CLI overrides: `--header`, `--eyebrow`, `--title`,
`--byline`, `--subheader`, `--outro-title`, `--outro-cmd`, `--outro-url`.
CLI wins over spec; omitted strings derive from the skill and action. The default
header is GHOST IN THE DROID, eyebrow SKILL SHOWCASE, subheader author/skill: action,
and outro command is the real `ghost skill install author/skill` command.

`--trim-idle` applies `mpdecimate` to the final composite only, keeping both panes
in sync. It never edits the captured cast or phone stream independently. Privacy
scans scrub and inspect the terminal, then OCR-gate the final clip. `--no-ocr`
requires manual privacy review. Output `demos/<action>.webm` is silent VP9, at most
30 seconds and 3 MB; it is accepted by the hub's upload/validate flow. Its `.spec.yaml`
saves the card settings. Omit the action to record every action independently.
The original `scripts/record_showcase_reel.py` remains the grid reel builder.

The underlying recorder workflow follows.

## Before / after pairs: `demos/before-after.*`

A skill page can show one recorded pair next to its demos: the same prompt on the same
phone, once without the skill (the agent drives the UI by hand) and once with it
(`find_skill` + `run_skill`). Two files in the skill dir, both outside the install set
and the signed digest:

- `demos/before-after.webm` (or `.mp4`/`.gif`): the composite, left = no skill, right =
  with skill, at most 3 MB. VP9 at 10 fps and 1600 px wide keeps a three minute pair
  near 2 MB with the shell text legible.
- `demos/before-after.json` (schema 1): the measured numbers.

```json
{
  "schema_version": 1,
  "action": "generate_qr",
  "prompt": "Generate a QR code for https://example.org/solar",
  "model": "claude-haiku-5-5",
  "device": "samsung-demo",
  "ok_means": "verified_task_check",
  "before": {"seconds": 52.24, "tokens": 254235, "tool_calls": 18, "ok": false},
  "after":  {"seconds": 27.49, "tokens": 127442, "tool_calls": 5, "ok": true},
  "notes": "Same clean temporary app per side; ..."
}
```

`ok_means` is `verified_task_check` when `ok` comes from an independent check of the
final phone state, or `agent_finished_turn` when it only says the agent ended its
turn. The site derives the headline ("11.8x fewer tokens, 1.9x faster") and says
slower or more-tokens results as plainly as better ones; a malformed json drops the
numbers and keeps the clip. The registry exposes the pair as `before_after`. The pair is not a signed run and adds no
run evidence (scoring v1.3 counts it as a docs item). Every pair clip passes the same privacy gate as a
demo (terminal panes OCR'd frame by frame, source casts scrubbed of home paths and
device identifiers) before it is committed.

## Adding clips to the hub

Hub clips are rendered and OCR-gated outside this repository, then copied into
`skillhub/<author>/<slug>/` (`demo.webm`, `demos/<action>.webm`,
`demos/before-after.webm` + `.json`). Only an output that passed the privacy gate
(terminal panes and the keyboard suggestion strip OCR'd frame by frame, casts scrubbed
of home paths and device identifiers) is committed, and every `.webm` must be complete
(EBML header, DocType webm, known Segment size, Cues element). Run
`tools/build_registry.py` afterwards so the registry carries the new file hashes.

## TL;DR

```bash
# 0. once per machine: asciinema, agg, ffmpeg, tesseract, adb on PATH
#    + scripts/privacy/FORBIDDEN.local.txt filled in (see checklist)
# 1. walk scripts/privacy/RECORDING_CHECKLIST.md — every session, no exceptions
# 2. validate
python3 scripts/record_demo.py --dry-run --demo langchain
# 3. record (device serial via --serial or ANDROID_SERIAL, never in the spec)
python3 scripts/record_demo.py --demo langchain --serial <SERIAL>
# 4. after several demos exist, stitch the hero reel
python3 scripts/record_showcase_reel.py
```

Outputs land in `site/public/showcase/<demo>/`: `demo.webm` (720p VP9),
`poster.png` (frame at t=3s), `snippet.py` (the demo's terminal commands).
`record_showcase_reel.py` writes `site/public/showcase/hero-reel.webm`.

## Where a demo is defined

| file | owns | owner |
|---|---|---|
| `site/public/showcase/copy.yaml` | title, hook, captions, CTAs, sizzle_order | marketing |
| `site/public/showcase/<demo>/spec.yaml` | device, setup, timeline, highlight_window | pipeline |

`record_demo.py` joins the two by demo id. The full spec.yaml schema is in
the docstring at the top of `scripts/record_demo.py`.

Timeline actions: `terminal_type` (simulated keystrokes, then the command
really runs), `phone_tap`, `phone_swipe`, `phone_key`, `wait_for_phone`,
`phone_screenshot_pause`, `sleep`. Setup steps: `wake_unlock`,
`kill_all_apps`, `launch_app`, `clear_app`, `install_apk`, `shell`.

iOS/both demos automatically get `GITD_ENABLE_IOS=1` in the recorded shell
(the platform gate defaults off). Extra demo env goes in spec `env:` —
validation rejects secret-shaped names/values.

## How the pipeline works

1. **Phone privacy prep** — DND, clear notifications, hide status bar, clear
   recents, then a screenshot→OCR gate that refuses to start on a dirty screen.
2. **Recording** — `adb shell screenrecord` (SIGINT-finalized, pulled after);
   terminal via `asciinema rec` running this script's `--_inner` mode, which
   replays the timeline in real time with a scrubbed environment.
3. **Scrub** — the cast is rewritten (`/home/<user>` → `~`, serials →
   `<ANDROID_DEVICE>`, hostnames → `ghost-dev-*`, key-shaped strings →
   `<REDACTED_KEY>`), then scanned; a hit aborts before rendering.
4. **Render** — agg (Ghost theme from `_brand/asciinema-ghost.json`, idle time
   NOT compressed so terminal and phone stay in sync) → ffmpeg composite:
   terminal left, phone inside the device frame (`_brand/frames.json` +
   `frame-pixel8.png`), ASS captions from timeline `caption:` fields, 1s
   intro/outro cards.
5. **OCR gate** — 30 frames at 2s intervals through tesseract, scanned against
   `scripts/privacy/FORBIDDEN.txt` + `FORBIDDEN.local.txt`. Any hit leaves the
   output quarantined in `.recordings/<demo>/` and exits nonzero. Only a clean
   video is copied into `site/public/showcase/`.

## CI

- `.github/workflows/demos.yml` — `--dry-run` on every spec: schema drift,
  missing brand assets, or a broken pipeline import fails the PR.
- `.github/workflows/privacy.yml` — greps committed artifacts against the
  generic forbidden list (defense-in-depth behind the OCR gates).

## Debugging

`--keep-workdir` preserves `.recordings/<demo>/`: raw + scrubbed casts,
`phone.mp4`, `terminal.mp4`, `captions.ass`, OCR frames with their `.txt`
output, and the pre-prep screenshot. `--skip-phone-prep` skips device hygiene
for iteration speed — never ship a recording made that way.

## iOS (manual for now)

`record_demo.py` refuses `device: ios` recording: point QuickTime at the
iPhone, record manually per the checklist, and composite by hand with the
`iphone15pro` entry in `_brand/frames.json`. Automating this is future work.
