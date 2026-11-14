# Control Ham Test on Android with an AI agent

**Control Ham Test on Android with an AI agent.** Study for your ham radio license: an agent opens a question pool, reads and answers questions and shows the right answer.

Target search phrase: _AI agent studies for the ham radio exam on Android_

Demo shows: `open_quiz (pool=technician)`

> Ghost in the Droid seed skill for Ham Test (`com.hazelhope.dubster.hamtest`), an offline study app for the US amateur (ham) radio exams. The question, options and feedback are plain text, so an agent can quiz itself or you. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_quiz` | Restart the app and open a question pool: technician (default), general or extra. | `pool` |
| `get_question` | Read the current question: id, text, options A-D, progress. | none |
| `answer` | Pick option A, B, C or D and submit; returns whether it was right and the right answer. | `choice` |
| `next_question` | Go to the next question. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_quiz |
| Primitives | answer, next_question |
| Read state | get_question |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.hazelhope.dubster.hamtest/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/ham-test
```

## Use

```bash
ghost skill run ghost/ham-test open_quiz --param pool=technician --device <serial>
ghost skill run ghost/ham-test answer --param choice=B --device <serial>
```

```python
run_skill(name="ghost/ham-test", action="answer", params={"choice": "B"})
# {"result": {"choice": "B", "state": {"answered": true, "correct": true, "right_answer": "B"}}}
```

Try asking: "Open the Technician ham radio quiz, read the first question, answer it and tell me whether you were right."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Ham Test 122. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 122 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- answer fails if the question is already answered: call next_question first.
- A question you got wrong comes back (the app repeats weak questions), so the next question can be the same id;  open_quiz restarts the app, which resets nothing permanent but the current position.
- The app records which questions you have seen, so progress text changes.

### Popups and first-run screens handled

- None.
