# music - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another offline music player.

**Package**: `org.fossify.musicplayer` (Fossify Music Player 1.8.1 from f-droid.org, sha256 verified against the repo index)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, en-US, no account. Test audio: three self-generated sine-tone WAV files (5 to 8 s) pushed to `/sdcard/Music/GhostSeed/` and media-scanned.
**Skill class**: HARD. No login, no checkpoints.

## Landmarks

- Bottom tabs: `id/tab_item_label` with text `Playlists`, `Folders`, `Artists`, `Albums`, `Tracks`.
- Track rows: `id/track_title`, `id/track_info` (`<artist> • <album or folder>`, unknown artist shows `<unknown>`), `id/track_duration` (`00:06`).
- Tapping a row opens the full-screen player (`TrackActivity`: `id/activity_track_title`, `id/activity_track_play_pause`, `id/next_track_label`) and starts playback.
- Truth for playback is the media3 session in `dumpsys media_session` for package `org.fossify.musicplayer`: `state=PlaybackState {state=PLAYING(3), position=2950 ...}` and `metadata: ... description=<title>, <artist>, <album>`.

## First run

Two Android 14 permission dialogs: "Allow Music Player to access music and audio" (Allow, required) and "Allow Music Player to send you notifications?" (Allow; with notifications denied the app refuses to start playback).

## Actions

### `list_tracks(max_items)`

Open the Tracks tab and walk it: `{tracks: [{title, artist, album, duration}], count}`.

### `play_track(title, seconds)`

Tap the row with that exact title, wait until the session is `PLAYING` that title, wait `seconds`, send `KEYCODE_MEDIA_PAUSE`. Success: session `PAUSED` on that title with position above zero.

### `get_now_playing()`

Return the session (`state`, `title`, `artist`, `album`, `position_ms`), or `state: none` when the player has no session.

### `pause_playback()`

Send `KEYCODE_MEDIA_PAUSE`. Success: the session is not `PLAYING`.

## Failure modes

- The repeat mode defaults to "Repeat all", so an unpaused track moves on to the next one; `play_track` always pauses.
- Media keys go to the most recent media session; if another app played more recently, `pause_playback` may pause that app instead.
