# Control Code Word on Android with an AI agent — play Wordle-style word puzzles

**Control Code Word on Android with an AI agent.** Play a Wordle-style word game on your phone: an agent starts a puzzle, types guesses and reads which words it has tried.

Target search phrase: _AI agent plays Wordle on Android_

Demo shows: `guess (word=crane)`

> Ghost in the Droid seed skill for Code Word (`com.peaceray.codeword`), an offline Wordle-style word game (secret word, 6 guesses). The typed guesses are readable; the per-letter feedback is only a tile colour and is NOT in the accessibility tree. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_puzzle` | Start a fresh puzzle (5 letters, 6 guesses) and return the seed | none |
| `guess` | Type a word and submit it; reports whether the row was accepted | `word` |
| `get_board` | Read the guesses made so far, word length and rows | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_puzzle |
| Primitives | guess |
| Read state | get_board (letters only, NOT the colour feedback) |

## Install

The app: F-Droid, or `https://f-droid.org/packages/com.peaceray.codeword/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/code-word
```

## Use

```bash
ghost skill run ghost/code-word new_puzzle --device <serial>
ghost skill run ghost/code-word guess --param word=crane --device <serial>
```

```python
run_skill(name="ghost/code-word", action="guess", params={"word": "crane"})
# {"result": {"word": "CRANE", "accepted": true, "board": {"typed_rows": ["CRANE"], ...}}}
```

Try asking: "Start a new Code Word puzzle and guess crane, then pound."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Code Word 1.4.4. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.4.4 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- HONEST LIMIT: the per-letter colour feedback is not readable from the accessibility tree; use a screenshot.
- Words the dictionary does not know are rejected by the app; the row stays empty and accepted is false.
- The guess length must match the puzzle (5 letters by default).
- The first-run How to play dialog is closed automatically.
- A guess the app does not accept (not in its dictionary) is reported as a failed guess (accepted: false fails the step).

### Popups and first-run screens handled

- The How to play dialog is closed by the open_game subroutine.
