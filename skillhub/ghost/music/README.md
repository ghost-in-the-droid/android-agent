# music

Demo shows: `play_track (title=Ghost Tone A440, seconds=3)`

> Ghost in the Droid seed skill for Fossify Music Player (`org.fossify.musicplayer`), an offline player that needs no account. Install it from F-Droid.

| Action | What it does | Params |
|---|---|---|
| `list_tracks` | Every track with artist, album or folder, duration | `max_items` (200) |
| `play_track` | Play a track by title for a few seconds, then pause | `title`, `seconds` (3, max 30) |
| `get_now_playing` | Media session state, title, artist, album, position | none |
| `pause_playback` | Pause playback | none |

## Install

```bash
curl -LO https://f-droid.org/repo/org.fossify.musicplayer_14.apk && adb install org.fossify.musicplayer_14.apk
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/music
```

## Use

```bash
ghost skill run ghost/music list_tracks --device emulator-5554
ghost skill run ghost/music play_track --param "title=Ghost Tone A440" --param seconds=3 --device emulator-5554
ghost skill run ghost/music get_now_playing --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/music", action="get_now_playing")
# {"now_playing": {"state": "paused", "title": "Ghost Tone A440", "artist": "<unknown>", "album": "GhostSeed", "position_ms": 2669}, "state": "paused"}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Fossify Music Player 1.8.1, en-US, fresh install and reused state, with three self-generated sine-tone WAV files. Signed self-runs live in `runs/`.

## Notes

The player needs audio-library and notification permission; the skill grants both on first run. Playback is always short and paused. License: MIT (the app itself is GPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 1.8.1 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 8/8 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Audio library permission (required)
- Notification permission (required for playback service)
- OS permission policy: {"allow_permissions": ["storage", "notifications"]}

### Other known failure modes

- The repeat mode defaults to "Repeat all", so an unpaused track moves on to the next one; `play_track` always pauses.
- Media keys go to the most recent media session; if another app played more recently, `pause_playback` may pause that app instead.
