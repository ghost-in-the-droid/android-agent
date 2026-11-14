# photos - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another gallery app.

**Package**: `com.google.android.apps.photos` (Google Photos)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Photos 6.29, en-US, no account.
**Skill class**: HARD. No login, no checkpoints.

## Landmarks

- Without an account Photos is a local gallery with two bottom tabs: `id/tab_photos` and `id/search_destination`.
- Grid tiles have no resource id; each is a clickable node with content-desc `Photo taken on Oct 5, 2026 8:12:33 PM` or `Video taken on ...`. Device folders appear as `id/collection_title` headers.
- Viewer: `id/photos_photofragment_components_background_photo_view` carries the same desc as the tile; bottom buttons `Share`, `Edit`, `Lens`, `Delete`.
- Navigation drawer (`Show Navigation Drawer`) holds `Photos`, `Trash`. Empty trash shows `id/photos_trash_ui_empty_state_title_view` = `Nothing in Trash`.

## First run and popups

1. "Keep your memories safe" bottom sheet with `Sign in to back up` and no dismiss button: tap the dimmed area above it. It can slide in a few seconds after launch, so `open_home` waits until the Photos tab has been visible for three polls in a row.
2. "You're missing out / Update your Google Photos app" promo: `Not now` (there is no Play account to update with).

## Actions

### `list_photos(max_items)`

Cold-start on the home grid and walk it, scrolling, returning `{items: [{kind, taken, folder}], count, folders}`. Pages are merged by the longest overlap of tile descriptions, because several tiles can share the same timestamp.

### `open_photo(index)`

Open the index-th item (0 = newest). Tiles say whether they are a photo or a video. A photo opens in the photo view, whose content-desc must contain the tapped tile's date; a video opens in the player (`photos_videoplayer_videolayout`). The first full-screen view shows Android's "Viewing full screen" hint; the engine's OS popup layer taps `Got it`.

### `count_trash()`

Open Trash from the drawer and return `{trash_count, trash_empty}`.

## Failure modes

- Photos hides exact duplicates (same pixels), so the item count can be lower than the file count.
- Search without backup only offers device-folder chips; it is not used.
