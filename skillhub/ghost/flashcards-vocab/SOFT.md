# flashcards-vocab - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.quchen.flashcard` (FlashCards, GPL-3.0-only, version 24 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Folders: label rows. Decks: label, a checkbox (`selectList`) per row, `startBtn`. Setup: question side radios, item-count slider (`numberOfListItemsSliderLabel`), Start. Quiz: `tv_progress`, `tv_question`, four `answerTextView`. Results: `tv_resultScore`, cards with `tv_correctAnswerVal` and `tv_selectedAnswerVal`.

## Actions

### `open_decks()`

Force-stops and relaunches.

### `start_quiz(folder, deck, count)`

Restarts the app, opens the folder, ticks the deck, taps Start Selection, drags the item-count slider until its label shows the count and taps Start.

### `get_question()`

The last question group in the dump is the visible one (the next one is preloaded under it).

### `answer(option)`

Taps the option and waits for the next question or the results.

### `answer_many(options)`

Repeats answer while a question is on screen.

### `get_results()`

Reads the score line and the wrong-answer cards.

## Adapting

Questions are random, so the text differs every run; the agent should read the emoji and choose. Emoji arrive as Unicode characters. The quiz is untimed. The results screen lists only the wrong answers. The item-count slider is set by dragging until the label matches.
