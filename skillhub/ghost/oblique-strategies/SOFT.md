# oblique-strategies - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `garden.lina.oblique_strategies` (Oblique Strategies, GPL-3.0-only, version 2 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- A stack of card Views at one fixed rectangle; the last in the dump is on top. The first card is the help card, then the title card, then random strategies. Controls appear only after a tap and are not used.

## Actions

### `open_deck()`

Force-stops and relaunches.

### `draw_card()`

Swipes the card and waits until a different card is on top. The first two cards are the help card and the title card.

### `draw_cards(count)`

Repeats the swipe; the strategies list holds only real strategy cards.

### `get_card()`

Reads the content-desc of the top card.

## Adapting

Cards are shuffled, so the text differs every run: check that a new card appeared, not a fixed value. The in-app undo is the Back button, which the skill never presses (it would leave the app).
