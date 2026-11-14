# gallery - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another gallery app or version.

**Package**: `org.fossify.gallery` (Fossify Gallery, GPL-3.0 FOSS app, installed from the official F-Droid repository, sha256-verified)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Fossify Gallery 1.13.1, en-US. Offline, no account.
**Skill class**: HARD. Read-only: no edit, share, favorite or delete.

## Layout reference

- Albums: `id/dir_holder` cards with `id/dir_name` and `id/photo_cnt`; toolbar `id/top_toolbar_search` (`Search folders`).
- Album: `id/media_item_holder` thumbnails; names (`id/medium_name`) only appear after `id/toggle_filename` (the choice persists). The search field reads `Search in <album>`.
- Viewer (`ViewPagerActivity`): file name as toolbar title, `id/menu_properties`, bottom bar `id/bottom_favorite`, `id/bottom_edit`, `id/bottom_share`, `id/bottom_delete`.
- Properties dialog: `id/property_label` / `id/property_value` pairs (Name, Path, Size, Resolution, Last modified).

## Permissions and prompts

1. Android 14 photos permission: `Allow all` (the gallery cannot list albums with a partial selection).
2. "Please grant our app access to all your files": shown on every launch; BACK declines. The skill never grants all-files access.

## Top-band safety

Album cards, the filename toggle and Properties are inside the top ~700 px where heads-up notifications appear. Those taps go through `guarded_tap`, which checks SystemUI's `mHeadsUpPinnedMode` and refuses while a heads-up is pinned.

## Actions

### `list_albums()`

Read album cards while scrolling. Returns `albums: [{name, count}]`.

### `list_photos(album)`

Tap the album card, show file names if hidden, read `id/medium_name` while scrolling.

### `open_photo(name)`

Look up the file's MediaStore id (`content query --uri content://media/external/images/media`, then videos) and fire `VIEW` with that content URI to `org.fossify.gallery`. Success: the viewer shows the file name.

### `get_photo_properties(name)`

`open_photo`, tap Properties, pair labels with the value directly below, close with OK. Returns `properties: {name, path, size, resolution, last_modified}`.

## Test fixture

Three 320x240 PNGs pushed to `/sdcard/Pictures/GhostTest/` and media-scanned.
