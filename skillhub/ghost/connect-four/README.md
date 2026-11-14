# Control ConnectFour Studio on Android with an AI agent — play Connect Four

**Control ConnectFour Studio on Android with an AI agent.** Play Connect Four against a perfect-play engine on your phone: an agent starts the game, drops the discs and reads the engine replies.

Target search phrase: _AI agent plays Connect Four on Android_

Demo shows: `new_game (columns=4,4,3)`

> Ghost in the Droid seed skill for ConnectFour Studio (`io.github.patrickric.connectfourstudio`), an offline Connect Four game with a perfect-play engine from F-Droid. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Start a new game | none |
| `play_column` | Drop a disc in column 1-7 and read the reply | `column` |
| `play_moves` | Play a sequence of columns on a fresh board | `columns` |
| `get_state` | Read move number, side to move and status | none |
| `undo_move` | Take back one move (the `<` button) | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | play_column, play_moves, undo_move |
| Read state | get_state |

## Install

The app: F-Droid, or `https://f-droid.org/packages/io.github.patrickric.connectfourstudio/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/connect-four
```

## Use

```bash
ghost skill run ghost/connect-four new_game --device <serial>
ghost skill run ghost/connect-four play_moves --param columns=4,4,3 --device <serial>
```

```python
run_skill(name="ghost/connect-four", action="play_column", params={"column": "4"})
# {"column": 4, "state": {"move": 3, "status": "Computer played 2 in 0.00 s.", "to_move": "Human"}}
```

Try asking: "Play three moves in Connect Four: columns 4, 4 and 3."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), ConnectFour Studio 1.0.1. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.0.1 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.0 | 2026-11-02 |

### Recorded failures

- The engine's reply column is random among equal moves: do not assert it, assert the move counter and the status text.
- The labels lag right after a tap: a status of "Computer is thinking..." is not a finished move; the helpers wait for "Computer played" and a counter increase of 2.
- A finished game (win or draw) shows a different status: the helpers stop and return it.

### Popups and first-run screens handled

- None: the app has no first-run screens and asks for no permissions.
