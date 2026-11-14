# ham-test - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.hazelhope.dubster.hamtest` (Ham Test, GPL-3.0-or-later, version 122 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Study tab: cards `Technician Questions`, `General Questions`, `Extra Questions`; bottom tabs Study, Practice, Settings.
- Quiz: progress texts, the question id (`T0C03`), `New` badge, question text, four option rows `A. ...` to `D. ...`, `Submit`; after submitting `Correct`/`Wrong.`, `The right answer was X` and `Next Question`.

## Actions

### `open_quiz(pool)`

Force-stops the app, relaunches and taps the pool card on the Study screen.

### `get_question()`

Reads the question id (e.g. T0C03), the question text and the four options.

### `answer(choice)`

Taps the option row, then Submit. The app then shows Correct/Wrong and the right answer.

### `next_question()`

Taps Next Question (only available after answering).

## Adapting

Only the Study quizzes are driven; the Practice exam mode and Settings are not.
