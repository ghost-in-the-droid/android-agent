# logical-fallacies - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `za.co.lukestonehm.logicaldefence` (Logical Defence, GPL-3.0, version 25 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- One list per category: a sticky category header and entries whose accessibility description is `number / name / definition / example`. The list scrolls.
- The navigation drawer (menu button, top left) lists the categories: Appeal to the Mind, Appeal to the Emotions, Faulty Deduction, Garbled Cause & Effect, Manipulating Content, On the Attack. Tapping one switches the list.

## Actions

### `list_categories()`

Opens the drawer and reads the category entries, then closes it.

### `list_fallacies(category, limit)`

Selects the category in the drawer, scrolls the list from the top and collects the entry descriptions.

### `get_fallacy(name)`

Walks the categories until the entry shows and parses its description.

## Adapting

The skill reads entry descriptions, so another encyclopedia-style list app can reuse the same scroll-and-collect helper. get_fallacy needs the exact name as shown in list_fallacies.
