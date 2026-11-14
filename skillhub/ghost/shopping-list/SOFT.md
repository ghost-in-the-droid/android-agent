# shopping-list - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.woefe.shoppinglist` (Shopping List, GPL-3.0, version 0.11.0 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- List screen: toolbar (`id/toolbar_main`), one row per item with `id/text_description` and `id/text_quantity`, the add button `id/fab_add`.
- Add panel (bottom of the screen): `id/new_item_description`, `id/new_item_quantity`, `id/button_add_new_item` (Done). The panel stays open after Done so several items can be added; the first BACK hides the keyboard, the second closes the panel.
- A checked item is drawn grey (not exposed in the accessibility tree), so the skill does not toggle or validate checks.

## Actions

### `add_item(name, quantity)`

Open the add panel (tap the add button if closed), type the name, optionally tap the quantity field and type it, tap Done. Success: a row with that name (and quantity) is visible.

### `add_items(items)`

Same panel flow once per item, no quantities. Success: every item shows as a row.

### `get_items()`

Close the add panel (BACK until the add button shows), then pair each `text_description` with the `text_quantity` on the same row. Returns `items: [{name, quantity}]`.

### `check_item(name)`

Tap the row whose `text_description` equals the name. The app does not expose the checked state to accessibility, so the result reports the tapped row.

### `remove_checked(confirm)`

Tap the toolbar delete button, wait for "Remove all checked items?", tap OK. Refuses unless confirm=yes. Returns the remaining items.

## Adapting

Other list apps keep the same ideas: an add field, an optional quantity, rows of text. Re-find the ids with `dump_xml`; the helpers only depend on the ids listed in the layout reference.
