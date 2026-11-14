# tasks - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another to-do app or version.

**Package**: `org.tasks` (Tasks.org, GPL-3.0 FOSS app, installed from the official F-Droid repository, sha256-verified)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Tasks.org 15.12, en-US.
**Skill class**: HARD. No login, no checkpoints. Local lists only: first run is answered with `Continue without sync`; the skill never adds an account (Google Tasks, CalDAV, DAVx5, EteSync) and never syncs.

## Layout reference

- List (Compose host with Android views inside): rows `id/rowBody` with `id/completeBox` (checkbox), `id/title`, `id/description`; section headers `id/header` (`No due date`, `Today`, ...). Bottom bar: `id/menu_search`, `id/menu_sort`, `id/menu_voice_add`; FAB `id/fab` (`Create new task`).
- Editor: title field (text = title), description, dates, priority, list chip. The only Save control is the toolbar icon (content-desc `Save`) at the top left. BACK asks "discard your changes?" instead of saving.
- An `Enable reminders` banner card appears at the top of the list until dismissed (detector taps `Dismiss`).

## Top-band safety

Save sits where heads-up notifications appear, and a heads-up may carry one-tap actions (for SMS: smart replies that send). `helpers.guarded_top_tap` reads `mHeadsUpPinnedMode` from the SystemUI dump and refuses to tap while a heads-up is pinned (waits up to 15 s, then fails). Test pools should also run with `settings put global heads_up_notifications_enabled 0`.

## Actions

### `add_task(title, notes)`

Share a text to Tasks.org (`android.intent.action.SEND`, `text/plain`, `-p org.tasks`, `EXTRA_SUBJECT` = title, `EXTRA_TEXT` = notes): the editor opens prefilled. Guarded tap on `Save`. Success: a list row with that exact title.

### `list_tasks()`

Read rows (title, notes, section) while scrolling. The validator rewinds and rereads the device list, requiring equality with the returned rows and count.

### `search_tasks(query)`

Tap the bottom-bar search, type the query, dismiss the keyboard with BACK, and require the requested query to remain in `id/search_src_text` before reading the filtered rows. Dismissing the keyboard prevents scrolling gestures from typing into the focused search field. Scrolling can collapse the query toolbar offscreen, so the validator rewinds to reveal it before checking the query. It then independently rereads the filtered device list and rewinds again to verify the query stayed unchanged. It requires equality with the returned rows/count and checks that every returned task mentions the query in its title or notes. A falsely empty result is rejected when matching rows are visible; two empty reads cannot pass under a changed or missing query.

### `complete_task(title)`

Tap the `id/completeBox` on the row with that exact title. Completed tasks leave the open list (default "hide completed"). Success: no open row with that title.

## Failure modes

- With "show completed" on, completed tasks stay visible with a strike-through; `complete_task` would then need a checked-state check.
- Duplicate titles: `complete_task` ticks the first match.
