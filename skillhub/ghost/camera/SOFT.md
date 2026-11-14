# camera - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another camera app.

**Package**: `com.android.camera2` (AOSP Camera, shipped on emulator and many AOSP builds)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Camera 2.0.002, en-US, emulated back and front cameras.
**Skill class**: HARD. No login, no checkpoints.

## How it works

- Open with the public intents `android.media.action.STILL_IMAGE_CAMERA` (photo mode) or `android.media.action.VIDEO_CAMERA` (video mode).
- Viewfinder landmarks: `id/shutter_button` (desc `Shutter`), `id/mode_options_toggle` (desc `Options`). The Options row holds `id/camera_toggle_button` (desc `Back camera` / `Front camera`), `id/countdown_toggle_button` (desc `Countdown timer is off`, `... 3 seconds`, `... 10 seconds`; each tap cycles), grid and flash toggles. The row collapses after a capture.
- Success is never read from the UI: the skill notes the device clock before opening the camera and waits for a new MediaStore row (`content query --uri content://media/external/images/media` or `.../video/media`) with `date_added` at or after it and a non-zero size. Photos land in `Pictures/IMG_*.jpg`, videos in `Movies/VID_*.mp4`.

## First run

"Remember photo locations?" with a pre-ticked checkbox and `NEXT`: untick, then `NEXT`. If the location permission dialog still appears, answer `Don’t allow`. Camera and microphone are granted by default on the emulator; if a device asks, the skill answers `While using the app`.

## Actions

### `take_photo(camera, timer_s)`

Photo mode, pick lens and countdown, press the shutter, return `{photo: {path, date_added, size}, camera, timer_s}`.

### `take_selfie(timer_s)`

Same as `take_photo` with the front lens fixed; the validator also checks the front lens was selected.

### `record_video(seconds, camera)`

Video mode, press the shutter, wait `seconds`, press it again, return `{video: {path, date_added, size, seconds}}`.

### `last_capture()`

No UI: return the newest photo and video rows from MediaStore and whichever is newer.

## Failure modes

- Other camera apps registered for the same intents: the intents are targeted at `com.android.camera2`; on devices without it, adapt by targeting the OEM camera and its shutter landmark.
- Very slow devices can take more than 15 s to write a photo; the wait is 15 s plus the countdown.
