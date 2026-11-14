# Control GPA Calculator on Android with an AI agent

**Control GPA Calculator on Android with an AI agent.** Calculate your GPA on your phone: an agent adds courses with credits and grades and reads the semester GPA.

Target search phrase: _AI agent calculates GPA on Android_

Demo shows: `set_scheme (scheme=UG)`

> Ghost in the Droid seed skill for GPA Calculator (`com.gpa.calculator.gpa_calculator`), an offline GPA calculator. Courses, credits, grades and the result are all readable, so an agent can compute a semester GPA exactly as the app does. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `set_scheme` | Choose the grading scheme: UG or MBA. | `scheme` |
| `add_course` | Add a course: optional name, credit (1, 2, 3, 4 or 6) and grade (A to F); returns the form with the course rows. | `credit`, `grade`, `name` |
| `get_courses` | Read the scheme, every course row and the total quality points. | none |
| `calculate` | Press Calculate and return the semester GPA (needs at least one complete course). | none |
| `clear_courses` | Remove all courses (needs confirm=yes). | `confirm` |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | set_scheme |
| Primitives | add_course, clear_courses |
| Read state | get_courses, calculate |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.gpa.calculator.gpa_calculator/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/gpa-calculator
```

## Use

```bash
ghost skill run ghost/gpa-calculator add_course --param credit=3 --param grade=A --device <serial>
ghost skill run ghost/gpa-calculator calculate --device <serial>
```

```python
run_skill(name="ghost/gpa-calculator", action="calculate")
# {"result": {"gpa": "4.00", "courses": 1, "scheme": "UG"}}
```

Try asking: "Add a 3 credit A in Maths and a 4 credit B in Physics, then calculate my GPA."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), GPA Calculator 13. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 13 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- calculate needs at least one complete course (credit and grade chosen); otherwise it fails with a message.
- Only the credit and grade values the app offers are accepted.
- clear_courses is destructive and needs confirm=yes.

### Popups and first-run screens handled

- None.
