# kana-quiz - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.noprestige.kanaquiz` (The Kana Quiz, GPL-3.0, version 20 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Quiz screen: `lblQuestion` (the kana), `lblResponse` (prompt), `lblScore` ('Score: 50.0% / 1 / 2', only after the first answer) and one Button per choice (A I U E O for the first set).
- Menu (More options): Question Selection, Quick Reference, Options, View Logs, About. The skill uses the quiz screen only and backs out of menus.

## Actions

### `get_question()`

Launches the app and backs out of menus until lblQuestion shows.

### `answer(choice)`

Finds the button by text (case-insensitive). was_correct is inferred from the score counter rising.

### `get_score()`

Parses lblScore; 0/0 before the first answer.

## Adapting

The skill never knows the right answer: the agent reads the character in get_question and chooses. Question sets (hiragana, katakana, kanji) are chosen in the app's Question Selection menu, which this version does not drive.
