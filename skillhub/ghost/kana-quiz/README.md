# Control The Kana Quiz on Android with an AI agent — learn Japanese hiragana and katakana

**Control The Kana Quiz on Android with an AI agent.** Practice Japanese on your phone: an agent reads the kana question, picks the romaji answer and tracks the score.

Target search phrase: _AI agent Japanese kana quiz on Android_

Demo shows: `answer (choice=a)`

> Ghost in the Droid seed skill for The Kana Quiz (`com.noprestige.kanaquiz`), an offline multiple-choice quiz that asks for the romaji of a Japanese kana character. Question, choices and score are all readable. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `get_question` | Open the quiz; read the kana, the choices and the score | none |
| `answer` | Tap the answer with this text; returns was_correct, score and the next question | `choice` |
| `get_score` | Read correct, total and percent | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | get_question |
| Primitives | answer |
| Read state | get_score |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.noprestige.kanaquiz/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/kana-quiz
```

## Use

```bash
ghost skill run ghost/kana-quiz get_question --device <serial>
ghost skill run ghost/kana-quiz answer --param choice=a --device <serial>
```

```python
run_skill(name="ghost/kana-quiz", action="answer", params={"choice": "a"})
# {"result": {"picked": "a", "was_correct": true, "state": {"correct": 1, "total": 1, ...}}}
```

Try asking: "Open the Kana Quiz and answer the first three questions."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), The Kana Quiz 20. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 20 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Questions are random; the agent must read the kana, a fixed answer is only right by chance.
- The score line appears only after the first answer.
- Choice text must match a visible button, otherwise the action fails and lists the choices.

### Popups and first-run screens handled

- None.
