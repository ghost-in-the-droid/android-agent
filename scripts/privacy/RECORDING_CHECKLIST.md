# Pre-Recording Privacy Checklist

Every showcase recording session MUST walk this list top to bottom.
The pipeline (`scripts/record_demo.py`) automates what it can and hard-blocks
on its OCR gates, but several items are physical/manual — the gate can only
catch what ends up as readable text on screen.

## 1. The device

- [ ] Fresh factory reset **or** a dedicated demo profile — never a personal
      daily-driver session
- [ ] No personal accounts logged in anywhere (Google account name shows up in
      Settings, Play Store, share sheets). Sign into demo accounts only, e.g.
      `ghost-demo@…`
- [ ] No personal photos, messages, contacts, or calendar entries on the device
- [ ] Clear app data for every app the demo touches (`pm clear <pkg>` or the
      `clear_app` setup step in spec.yaml)
- [ ] Wallpaper set to the Ghost brand wallpaper (manual until a
      `_brand/wallpaper.png` + automated swap lands)
- [ ] Airplane mode + a generic hotspot ("Ghost Demo") if the demo needs
      network — never a personally-named home/office SSID

## 2. What the pipeline enforces automatically

Run through `record_demo.py` — never record by hand. It will:

- enable Do-Not-Disturb and clear all notifications
- hide the status bar (immersive mode, best-effort per Android version)
- clear recents
- take a pre-record screenshot, OCR it, and **refuse to start** if anything on
  screen matches the forbidden lists
- run every terminal command with a scrubbed environment (no `*_API_KEY`,
  `*_TOKEN`, `*_SECRET`, … variables survive into the recording)
- rewrite the terminal cast (paths → `~`, serials → `<ANDROID_DEVICE>`,
  hostnames → `ghost-dev-*`, key-shaped strings → `<REDACTED_KEY>`)
- OCR 30 frames of the final render and **refuse to output** on any hit

## 3. The forbidden lists

- `scripts/privacy/FORBIDDEN.txt` — committed, **generic patterns only**
  (home-dir shapes, key prefixes, private-repo URLs). Never put a real name,
  hostname, or serial in this file: the repo is public, so the list itself
  would be the leak.
- `scripts/privacy/FORBIDDEN.local.txt` — gitignored, same format. This is
  where the recording operator's real identifiers go (username, hostnames,
  device serials, project names that must never appear). **Create it before
  your first session** — `record_demo.py` warns loudly when it's missing.
- Append patterns freely; plain lines are case-insensitive substrings,
  `re:`-prefixed lines are regexes.

## 4. After recording

- [ ] Watch the output once, full-screen, before committing — OCR misses
      low-contrast/small text, **and the OCR gate samples at most 30 frames
      at 2-second intervals: anything that flashes on the phone for under
      ~2s (a notification sliding in, a toast, an autofill hint) can slip
      between sampled frames.** The cast scan is the strong text gate for the
      terminal side, and DND/notification prep + the brand wallpaper swap
      mitigate the flash risk on the phone — but the human watch-through is
      the only gate for sub-2s phone content. **Do not attempt demos whose
      script requires sensitive content to flash briefly on screen**
- [ ] Devices with a PIN/pattern must be unlocked by hand before recording —
      the pipeline's auto-unlock only clears swipe-only lock screens (the
      pre-record OCR screenshot captures whatever is actually displayed)
- [ ] `python3 scripts/privacy/scrub.py --check <files>` over any hand-edited
      artifacts (snippets, docs, screenshots)
- [ ] CI (`.github/workflows/privacy.yml`) greps every PR as defense-in-depth;
      do not rely on it as the primary gate

## 5. iOS (manual for now)

QuickTime "New Movie Recording" pointed at the iPhone. Before hitting record:
same device hygiene as §1, plus hide the menu bar clock on the Mac if any of
the Mac screen is captured. The terminal side still goes through
`record_demo.py`'s scrubbers.
