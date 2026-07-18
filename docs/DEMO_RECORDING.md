# Recording a Showcase Demo (internal)

The showcase pipeline is "Ghost records Ghost": a spec-driven recorder drives
a real phone with Ghost's own adb primitives while capturing the terminal and
the phone screen in sync, then composites a branded WebM.

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
