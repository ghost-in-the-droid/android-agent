# dialer - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another phone app or version.

**Package**: `com.google.android.dialer` (Google Phone)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Phone 100.0, en-US, no Google account.
**Skill class**: HARD. No login, no checkpoints. The skill never taps Call.

## Layout reference

Bottom tabs keyed by resource id: `id/tab_speed_dial` (Favorites), `id/tab_call_history` (Recents; its content-desc grows to `Recents, 1 new notification`, so match by id), `id/tab_contacts`, `id/tab_voicemail`. The dialpad shows the number in `id/digits` and offers matching contacts as `id/primary` rows above it.

Call log cards: `id/new_call_log_entry_card` with content-desc like `The latest is a missed call from Grace Hopper, Mobile, Just now.`; inside it `id/primary_text` (name or number) and `id/secondary_text` (`Mobile • Just now`).

## Actions

### `dial_number(number)`

Fire `android.intent.action.DIAL` with `tel:<number>` (spaces and dashes stripped). The dialpad opens pre-filled. Success: `id/digits` ends with the same digits and the Call button is present. The call is not placed.

### `get_call_log(limit)`

Open Recents, read each card (name, detail line, type from the card description: missed, incoming, outgoing, rejected, blocked, voicemail), scroll until `limit` entries or no new cards. Returns `calls`, `count`, `missed`.

### `list_favorites()`

Open Favorites; read names from `Call <name>` / `Quick contact for <name>` descriptions. An empty state (`id/empty_content_view_message`) returns `[]`.

## Test fixture

The emulator has no real calls. A missed call can be simulated on the emulator host with `adb -s <serial> emu gsm call 5550100` followed by `emu gsm cancel 5550100` (console commands must run where the emulator runs).

## Failure modes

- A notification permission dialog may appear on first launch; the detector denies it.
- Other dialers (Samsung) use different tab ids; ACTION_DIAL works everywhere.
