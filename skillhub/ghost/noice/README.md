# Control Noice on Android with an AI agent — play ambient sounds

Demo shows: `play_preset (preset=Beach, seconds=3)`

> Ghost in the Droid seed skill for Noice (`com.github.ashutoshgngwr.noice`), an ambient sound generator. No account. Install it from F-Droid.

| Action | What it does | Params |
|---|---|---|
| `list_presets` | Saved presets with author | none |
| `list_sounds` | Every library sound with its category | none |
| `play_preset` | Play a preset briefly, then stop | `preset`, `seconds` (3, max 30) |
| `stop_playback` | Stop whatever Noice plays | none |

## Install

```bash
curl -LO https://f-droid.org/repo/com.github.ashutoshgngwr.noice_72.apk && adb install com.github.ashutoshgngwr.noice_72.apk
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/noice
```

## Use

```bash
ghost skill run ghost/noice list_presets --device emulator-5554
ghost skill run ghost/noice play_preset --param preset=Thunderstorm --param seconds=3 --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/noice", action="play_preset", params={"preset": "Beach", "seconds": 5})
# {"played": "Beach by @eMPee584", "seconds": 5}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Noice 2.5.7, en-US, fresh install and reused state. Signed self-runs live in `runs/`.

## Notes

Never opens the Account tab or signs in. Playback is short and always stopped. Needs network on first play of each sound. License: MIT (the app itself is GPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 2.5.7 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 8/8 | 2026-10-05 |

Physical-device launch attempts are also recorded on Samsung SM-A156B (Android 16, 1080×2340, en-US). Results remain action-specific; an attempt does not imply success. See the demos and current signed runs for evidence.

Untested so far: other OEM skins, other screen sizes and other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Notification permission (playback controls)
- OS permission policy: {"allow_permissions": ["notifications"]}

### Other known failure modes

- Sounds stream from the Noice CDN on first play; without network a preset may stay buffering and `play_preset` fails with "did not start playing".
- Premium sounds (marked by `id/premium_status`) need a subscription; the bundled presets play without one.
