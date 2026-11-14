# Control Flash Deck on Android with an AI agent — study flashcards

**Control Flash Deck on Android with an AI agent.** Make and study flashcards on your phone: an agent creates decks and cards, quizzes itself or you, and grades each card.

Target search phrase: _AI agent makes flashcards on Android_

Demo shows: `add_deck (name=Spanish)`

> Ghost in the Droid seed skill for Flash Deck (`m.co.rh.id.a_flash_deck`), an offline flashcard app with spaced-repetition grading. Every control has a resource id, so decks, cards and the review session are fully readable and drivable. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `add_deck` | Create a deck | `name` |
| `add_card` | Add a card to an existing deck | `deck`, `question`, `answer` |
| `list_decks` | List decks with card counts | none |
| `start_review` | Open Study due and read the first card | none |
| `reveal_answer` | Show the answer of the current card | none |
| `grade` | Grade the card again/hard/good/easy; returns the next card | `rating` |
| `get_card` | Read the card on screen | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | add_deck, start_review |
| Primitives | add_card, reveal_answer, grade |
| Read state | list_decks, get_card |

## Install

The app: F-Droid, or `https://f-droid.org/packages/m.co.rh.id.a_flash_deck/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/flashcards
```

## Use

```bash
ghost skill run ghost/flashcards add_deck --param name=Spanish --device <serial>
ghost skill run ghost/flashcards add_card --param deck=Spanish --param question=hola --param answer=hello --device <serial>
```

```python
run_skill(name="ghost/flashcards", action="grade", params={"rating": "good"})
# {"result": {"rating": "good", "state": {"question": "gato", "progress": "2 / 2"}}}
```

Try asking: "Make a Spanish flashcard deck, add hola/hello and gato/cat, then study them."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Flash Deck 64. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 64 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- Cards typed with other characters (accents, emoji) are refused: adb text input is ASCII only.
- Grading the last due card ends the session; get_card then reports in_review: false.
- The first-run notifications prompt is dismissed with CANCEL, notifications stay off.

### Popups and first-run screens handled

- The notifications prompt is dismissed by go_home.
