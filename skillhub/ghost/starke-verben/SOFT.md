# starke-verben - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.sw24softwares.starkeverben` (Starke Verben, GPL-3.0-or-later, version 16 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Tabs Lesson, Test, List, Settings. Lesson: labelled forms. List: search field and expandable rows. Test: five fields (infinitive, preterite, participle, 3rd person, translation), a sein checkbox, Verify; result screen with the correct forms, Continue and Finish.

## Actions

### `open_verbs()`

Force-stops and relaunches; the Lesson tab shows one verb with its forms.

### `next_lesson()`

Taps the Lesson tab again until the verb changes (a swipe does nothing).

### `get_lesson()`

Reads the lesson text nodes.

### `get_verb(verb)`

Opens the List tab, types the verb, presses Enter (the list filters on submit), expands the exact match and reads the six forms.

### `start_test()`

Taps the Test tab and the orange button; returns which field is given and which are empty.

### `answer_test(infinitive, preterite, participle, third_person, translation, auxiliary)`

Skips the given field, types the others, sets the sein checkbox, taps Verify, reads the correct forms.

### `finish_test()`

Taps Finish on the result screen.

## Adapting

adb can type only ASCII, so umlauts (as in faehrt) cannot be entered; such answers count as wrong, but the result screen still returns the correct forms with umlauts. The list filters on Enter, and the lesson changes only by tapping the Lesson tab again.
