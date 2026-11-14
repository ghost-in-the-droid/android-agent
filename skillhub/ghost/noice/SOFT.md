# noice - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another ambient-sound app.

**Package**: `com.github.ashutoshgngwr.noice` (Noice 2.5.7 from f-droid.org, sha256 verified against the repo index)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, en-US, no account (the Account tab is never opened).
**Skill class**: HARD. No login, no checkpoints.

## Landmarks

- First run: an AppIntro (`Welcome`) with `id/skip` (`SKIP`) and `id/next`.
- Bottom tabs by id: `id/library`, `id/presets`, `id/sleep_timer`, `id/alarms`, `id/account`.
- Library: category headers are all-caps texts without id (`LIFE`, `PLACES`, `RAW NOISE`, `THINGS`, `TRAVEL`, `WEATHER`); each sound row has `id/title`, `id/info`, `id/download`, `id/play`, `id/volume`.
- Presets: rows with `id/play_button` and `id/title` (`Beach by @eMPee584`) and `id/menu_button`.
- While playing, a bottom controller shows the preset name, `id/playback_state` (`Playing`, then `Stopping` during the fade-out), `id/play_toggle`, `id/stop`.
- Truth for playback is the media session (`dumpsys media_session`, package `com.github.ashutoshgngwr.noice`): `state=PLAYING(3)` or `STOPPED(1)`, `description=<preset name>`.

## Actions

### `list_presets()`

Cold-start, Presets tab, return `{presets: [{preset, name, author}], count}`.

### `list_sounds()`

Cold-start, Library tab, walk all categories: `{sounds: [{sound, category}], count}` (31 sounds in 2.5.7).

### `play_preset(preset, seconds)`

Find the preset row by full title or by the name before ` by @`, tap its play button, wait until the session plays that preset, wait `seconds`, tap the controller's Stop. Success: the session reaches `STOPPED` (the app fades out for a few seconds first).

### `stop_playback()`

If the session is playing, send `KEYCODE_MEDIA_STOP`. Success: not playing.

## Failure modes

- Sounds stream from the Noice CDN on first play; without network a preset may stay buffering and `play_preset` fails with "did not start playing".
- Premium sounds (marked by `id/premium_status`) need a subscription; the bundled presets play without one.
