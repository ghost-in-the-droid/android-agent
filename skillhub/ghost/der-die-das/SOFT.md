# der-die-das - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.machiav3lli.derdiedas` (Der Die Das, GPL-3.0-or-later, version 3000 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Menu with Practice, Stats and Settings. Practice shows a German noun, its English meaning, three buttons Der / Die / Das and a Pending / Mastered counter. Stats shows learned words / all words.

## Actions

### `open_practice()`

Force-stops, relaunches and taps Practice in the menu.

### `get_word()`

Reads the noun, translation and counter text.

### `answer(article)`

Taps the article button and compares the noun before and after: a changed noun means the answer was right.

### `answer_many(articles)`

Repeats answer and returns a right or wrong flag per article.

### `get_stats()`

Goes back to the menu if needed and taps Stats.

## Adapting

A right answer jumps to the next noun at once; a wrong answer keeps the noun on screen and the app then swallows the next right press, so the skill presses the same article once more before it calls an answer wrong (taps=2 in the result). There is no feedback text; right or wrong is inferred from whether the noun changed. Nouns come in random order. Mastered only grows after repeated right answers.
