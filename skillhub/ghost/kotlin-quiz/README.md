# Control Kotlin Quiz on Android with an AI agent

**Control Kotlin Quiz on Android with an AI agent.** Want to see how well an AI knows Kotlin? Your agent takes the quiz on your phone and reports the score.

Target search phrase: _AI agent takes a Kotlin quiz on Android_

Demo shows: `start_quiz (name=Ghost)`

> Ghost in the Droid seed skill for Kotlin Quiz (`com.example.kotlinquiz`), an offline 10 question Kotlin quiz. The question, the three options and the final score are text nodes, so an agent can take the quiz and report the result. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `start_quiz` | Restart the app, enter a display name and start the quiz; return the first question with its three options. | `name` |
| `get_question` | Read the current question and its three options. | none |
| `answer` | Choose option 1, 2 or 3, submit it and move on to the next question (or the result after the last one). | `option` |
| `answer_many` | Answer several questions in a row (up to 10 option numbers, comma separated), stopping at the result screen. | `options` |
| `get_result` | Read the final result screen: name and score (10 points per right answer). | none |
| `finish_quiz` | Close the result screen and return to the welcome form. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | start_quiz |
| Primitives | answer, answer_many, finish_quiz |
| Read state | get_question, get_result |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.example.kotlinquiz/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/kotlin-quiz
```

## Use

```bash
ghost skill run ghost/kotlin-quiz answer --param option=2 --device <serial>
```

```python
run_skill(name="ghost/kotlin-quiz", action="answer", params={"option": 2})
# {"result": {"question": "...", "chosen": "...", "next": {"screen": "quiz", ...}}}
```

Try asking: "Start the Kotlin quiz, read each question and answer the first three questions with the options you think are right, then tell me the questions."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Kotlin Quiz 3. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 3 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Right or wrong per question is not readable (colour only).
- Going back to a question is not possible in the app.

### Popups and first-run screens handled

- None.
