# camera

Demo shows: `take_photo (defaults: camera=back, timer_s=0)`

> Ghost in the Droid seed skill for the AOSP Camera (`com.android.camera2`). No account; verified through MediaStore, not screenshots.

| Action | What it does | Params |
|---|---|---|
| `take_photo` | Take a photo, return the saved path | `camera` (back, front), `timer_s` (0, 3, 10) |
| `take_selfie` | Front-lens photo | `timer_s` |
| `record_video` | Record an N-second clip | `seconds` (1 to 60), `camera` |
| `last_capture` | Newest photo and video in MediaStore | none |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/camera
```

## Use

```bash
ghost skill run ghost/camera take_photo --param camera=back --param timer_s=3 --device emulator-5554
ghost skill run ghost/camera record_video --param seconds=5 --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/camera", action="take_selfie")
# {"camera": "front", "timer_s": 0, "photo": {"path": "/storage/emulated/0/Pictures/IMG_20261005_202128.jpg", ...}}
```

On a physical phone with Ghost's MCP server, the `open_camera` tool opens OEM cameras in a mode with a timer; this skill is the deterministic, verifiable capture path for AOSP Camera.

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi, emulated cameras), Camera 2.0.002, en-US, fresh app data and reused state. Signed self-runs live in `runs/`.

## Notes

Geotagging is switched off on first run and location is denied. The skill never deletes media. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 2.0.002 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0, 1.0.1 | 12/12 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Camera permission (required)
- Microphone permission (video sound)
- Location permission (geotagging stays off)
- OS permission policy: {"allow_permissions": ["camera", "microphone"]}

### Other known failure modes

- Other camera apps registered for the same intents: the intents are targeted at `com.android.camera2`; on devices without it, adapt by targeting the OEM camera and its shutter landmark.
- Very slow devices can take more than 15 s to write a photo; the wait is 15 s plus the countdown.
