# baby-name - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `fr.hnit.babyname` (Baby Name, GPL-3.0-or-later, version 204 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- A list screen of saved searches (menu entry New Baby adds one), a preferences form with gender radios, a Pattern field (Java regular expression), origin checkboxes and a live (N Names) counter, and a name view with PREVIOUS / REMOVE / NEXT and an (i/N) counter.

## Actions

### `open_filter()`

Force-stops, relaunches and opens the overflow menu entry New Baby.

### `set_filter(gender, pattern)`

Deletes earlier saved searches, picks the gender radio, types the pattern, waits for the counter to settle, saves and opens the first match.

### `get_name()`

Reads name, details line and the position counter.

### `next_name()`

Taps NEXT and waits for the position counter to change.

### `previous_name()`

Taps PREVIOUS (disabled at the first name).

### `list_names(count)`

Reads the current name then taps NEXT, collecting each name and its details.

## Adapting

Every set_filter first deletes the earlier saved searches (in-app only), so the new search is the only one. The names come in the app's own order, not alphabetical. Origin checkboxes are not driven; the pattern is a Java regular expression (^ and $ anchor, .+ any letters). Characters that cannot be typed through adb text input may fail.
