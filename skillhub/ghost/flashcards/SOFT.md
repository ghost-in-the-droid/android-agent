# flashcards - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `m.co.rh.id.a_flash_deck` (Flash Deck, GPL-3.0, version 64 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Home: Add Deck, Add Card, Start Test, Notification Timer, Export/Import, three Gemini generators (never used). When cards are due a `Study due (N)` button appears on top and shifts the grid, so the skill finds buttons by id.
- Add Deck is a dialog (`edit_text_name`, SAVE); the dialog moves up while the keyboard is open. Add Card: Select Deck dialog (`text_deck_name`, `text_total_cards`, OK), then a form (`text_input_edit_question`, `text_input_edit_answer`, menu Save).
- Review: `text_question`, `text_answer` ('[Tap to view answer]' until revealed), `text_progress`, grade buttons AGAIN/HARD/GOOD/EASY, PREVIOUS/EXIT/NEXT.
- First run asks to allow notifications: the helpers press CANCEL.

## Actions

### `add_deck(name)`

Add Deck dialog, type the name, SAVE. Success: the deck is in the deck list.

### `add_card(deck, question, answer)`

Add Card, pick the deck, fill the form, Save. Success: the deck's card count rose by one.

### `list_decks()`

Opens the Select Deck dialog, reads it, cancels.

### `start_review()`

Taps `Study due (N)`; due: 0 when nothing is due.

### `reveal_answer()`

Taps the answer area.

### `grade(rating)`

Reveals if needed, taps the grade button.

### `get_card()`

Question, answer if revealed, progress.

## Adapting

Text is limited to letters, digits, space and . , ? ! ' - (typed through adb). Decks are shared state inside the app, so the agent should use unique deck names. Import/export, notification timers and the Gemini generators are not driven.
