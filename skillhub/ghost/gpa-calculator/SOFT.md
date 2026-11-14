# gpa-calculator - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.gpa.calculator.gpa_calculator` (GPA Calculator, MIT, version 13 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Form: UG/MBA radios, per course a name EditText plus Credit and Grade buttons (each opens a dropdown whose options are buttons), an Add Course button, Clear Courses and Calculate at the bottom.
- Result screen: `UG GPA Result`, `Current semester GPA is:` and the number; the back key returns to the form.
- Credit menu: 1, 2, 3, 4, 6. Grade menu: A, A-, B+, B, B-, C+, C, C-, D+, D, F.

## Actions

### `set_scheme(scheme)`

Taps the UG or MBA radio. Success: that radio is checked.

### `add_course(credit, grade, name)`

Fills the last empty row (name, Credit menu, Grade menu) and taps Add Course. Success: one more complete row.

### `get_courses()`

Reads the name fields and the Credit/Grade buttons of each row.

### `calculate()`

Taps Calculate, reads the result screen, closes it.

### `clear_courses(confirm)`

Taps Clear Courses. Success: no complete rows left.

## Adapting

The app computes the GPA; the skill only enters data and reads the result. A CGPA screen exists behind the result and is not driven.
