# kotlin-quiz - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.example.kotlinquiz` (Kotlin Quiz, MIT, version 3 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Welcome form (name field, START), question screen (question, three options, SUBMIT that becomes GET NEXT QUESTION) and a result screen (name, score, FINISH).

## Actions

### `start_quiz(name)`

Types the name, presses Enter to hide the keyboard that covers START, then taps START.

### `get_question()`

Reads the question and option text.

### `answer(option)`

Taps the option, SUBMIT (the app colours the answers) and GET NEXT QUESTION.

### `answer_many(options)`

Repeats answer and returns what was chosen for each question.

### `get_result()`

Reads the name and the score line.

### `finish_quiz()`

Taps FINISH.

## Adapting

Whether an answer was right is only shown by colour, so the skill cannot report it per question; the score on the result screen (10 points per right answer) is the verdict. The question order is random each run. The name you give is only shown on the result screen.
