# tally-counter - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `me.tsukanov.counter` (Counter, Apache-2.0, version 35 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Main screen: toolbar with a hamburger (`desc="Open the list of counters"`), the active counter's title, reset (`desc="Reset counter"`) and edit buttons; the whole body is one tap target (`id/counterFrame`) with the big number (`id/counterLabel`).
- Drawer: `id/add_counter` ("Add counter") and one row per counter with `id/row_title` and `id/row_count`.
- Add dialog (AlertDialog): `id/edit_name` (Title), `id/edit_value` (Value), `android:id/button1` (ADD), `android:id/button2` (CANCEL).
- A fresh install already holds one counter named `First counter` at 0. Adding or selecting a counter makes it the active one.

## Actions

### `add_counter(name, value)`

Open the drawer, tap "Add counter", type the title and the starting value (typed by a helper because callers pass digits as integers), tap ADD. Success: the toolbar shows the title and the big number equals the value.

### `increment_counter(name, times)`

Open the drawer, tap the row whose title is `name`, tap the big number area `times` times. Success: the number rose by exactly `times`.

### `select_counter(name)`

Open the drawer and tap the row. Returns `active: {name, value}`.

### `reset_counter(name)`

Select the counter, tap Reset in the toolbar (confirm if the app asks). Success: the value is 0.

### `get_counters()`

Open the drawer and read every row. Returns `counters: [{name, value}]`.

## Adapting

Other counter apps usually keep the same three ideas: a list of named counters, a create dialog and a big tap target. Re-find the ids with `dump_xml`; the helpers only depend on `row_title`, `row_count`, `counterFrame` and `counterLabel`.
