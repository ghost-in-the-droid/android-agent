# Control FlashCards on Android with an AI agent — study flashcards

**Control FlashCards on Android with an AI agent.** Quiz yourself on emoji, English, German or Spanish words: the agent starts the quiz, answers every question and tells you the score.

Target search phrase: _AI agent plays a vocabulary quiz on Android_

Demo shows: `start_quiz (folder=English, deck=Animal Emoji, count=3)`

> Ghost in the Droid seed skill for FlashCards (`com.quchen.flashcard`), built-in vocabulary quizzes with multiple choice answers and a results screen. Questions, options and the score are real text, so an agent can read an emoji or a word, pick the answer and read its score. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `open_decks` | Restart the app and read the folder list. | none |
| `start_quiz` | Start a multiple choice quiz from a folder and deck with a given number of questions. | `folder`, `deck`, `count` |
| `get_question` | Read the question on screen (an emoji or a word) with its four options and the progress. | none |
| `answer` | Answer the current question by option number (1-4, left to right and top to bottom) or by option text. | `option` |
| `answer_many` | Answer several questions in a row from a comma separated list of options. | `options` |
| `get_results` | Read the results screen: score, comment and the wrongly answered questions with the correct and chosen answer. | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | open_decks, start_quiz |
| Primitives | answer, answer_many |
| Read state | get_question, get_results |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.quchen.flashcard/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/flashcards-vocab
```

## Use

```bash
ghost skill run ghost/flashcards-vocab start_quiz --param folder=English --param deck='Animal Emoji' --param count=5 --device <serial>
```

```python
run_skill(name="ghost/flashcards-vocab", action="start_quiz", params={"folder": "English", "count": "5"})
```

Try asking: "Start a 3 question emoji quiz in the FlashCards English folder, answer each question using the emoji, then tell me my score."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), FlashCards 24. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 24 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The count is capped by the deck size.
- Folder and deck names must match the list (for example Animal Emoji).

### Popups and first-run screens handled

- None.
