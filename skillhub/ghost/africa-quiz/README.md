# Control Africa Quiz on Android with an AI agent

**Control Africa Quiz on Android with an AI agent.** Quiz yourself on African capitals: an agent starts a round, answers the questions and reads the review.

Target search phrase: _AI agent plays a geography quiz on Android_

Demo shows: `answer (option=1)`

> Ghost in the Droid seed skill for Africa Quiz (`com.mufradat.africaquiz`), an offline quiz on African capitals. Questions, options, the score and the answer review are plain text, so an agent can play and grade a whole round. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `start_quiz` | Restart the app and start a new 10 question round. | none |
| `get_question` | Read the current question: number, score, the prompt and the four options. | none |
| `answer` | Pick an option by position (1-4) or by its text; the quiz moves on at once. | `option`, `expect_question` |
| `answer_many` | Answer several questions in a row, e.g. options=1,3,2. | `options` |
| `get_results` | After the last question: the percent, the score and the full answer review (country, correct capital, your answer). | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | start_quiz |
| Primitives | answer, answer_many |
| Read state | get_question, get_results |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.mufradat.africaquiz/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/africa-quiz
```

## Use

```bash
ghost skill run ghost/africa-quiz start_quiz --device <serial>
ghost skill run ghost/africa-quiz answer --param option=1 --device <serial>
```

```python
run_skill(name="ghost/africa-quiz", action="answer", params={"option": "Kigali"})
# {"result": {"chosen": "Kigali", "state": {"number": 3, "score": 1}}}
```

Try asking: "Start the Africa capitals quiz, answer the first three questions and tell me my score."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Africa Quiz 1. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The default 15 s countdown skips a question that is not answered in time: pass expect_question to answer so a stale answer fails instead of hitting the next question.
- There is no per-answer feedback; the score on screen and get_results show what was right.
- get_results works only after question 10.

### Popups and first-run screens handled

- None.
