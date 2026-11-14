# africa-quiz - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.mufradat.africaquiz` (Africa Quiz, MIT, version 1 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Start: title, `Countdown Timer` switch (15 seconds per question), `Start Quiz`.
- Question: `Question n/10`, `Score: s`, the prompt as two texts (`What is the capital of` / `Eritrea?`), four option rows.
- Results: `Quiz Complete!`, percent, `k/10`, then the Answer Review rows (`Correct: ...`, `Your answer: ...`, a tick or cross) and `Play Again`.

## Actions

### `start_quiz()`

Force-stops the app, relaunches and taps Start Quiz. The countdown timer switch keeps its default.

### `get_question()`

Reads Question n/10, Score, the prompt and the four option rows.

### `answer(option, expect_question)`

Taps the option row. The app has no per-answer feedback screen: read the score change or the final review.

### `answer_many(options)`

Reads the screen before every tap so the options of each question are looked up fresh.

### `get_results()`

Reads the result screen and scrolls to collect all 10 review rows.

## Adapting

The countdown switch is not read or changed (its state is not exposed).
