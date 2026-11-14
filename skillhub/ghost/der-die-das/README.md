# Control Der Die Das on Android with an AI agent

**Control Der Die Das on Android with an AI agent.** Learning German articles? Your agent practises der, die or das for you and keeps score.

Target search phrase: _AI agent learns German noun genders der die das on Android_

Demo shows: `answer (article=die)`

> Ghost in the Droid seed skill for Der Die Das (`com.machiav3lli.derdiedas`), an offline German noun gender trainer with about 10000 nouns. The noun, its translation and the three answer buttons are text nodes, so an agent can play it. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_practice` | Restart the app, open the Practice screen and read the first noun. | none |
| `get_word` | Read the noun on screen, its English meaning and the Pending / Mastered counters. | none |
| `answer` | Answer the current noun with der, die or das and report whether it was right (a right answer shows the next noun, a wrong one keeps the same noun). | `article` |
| `answer_many` | Answer several nouns in a row (up to 10 articles, comma separated). A wrong answer keeps the same noun, so the next article is tried on it. | `articles` |
| `get_stats` | Open the Stats screen and read the fully learned / all words figure. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_practice |
| Primitives | answer, answer_many |
| Read state | get_word, get_stats |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.machiav3lli.derdiedas/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/der-die-das
```

## Use

```bash
ghost skill run ghost/der-die-das answer --param article=die --device <serial>
```

```python
run_skill(name="ghost/der-die-das", action="answer", params={"article": "die"})
# {"result": {"word": "Uhr", "chosen": "die", "correct": true, "next_word": "Prozent"}}
```

Try asking: "Open the Der Die Das trainer, read the noun on screen and answer it with the right article, then answer two more nouns."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Der Die Das 3000. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 3000 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- There is no reset for progress inside the app; a clean reset (pm clear) starts at 0 mastered.
- A wrong guess keeps the same noun, so answering blindly can need several tries.

### Popups and first-run screens handled

- None.
