# Control Checkers (Privacy Friendly) on Android with an AI agent

**Control Checkers (Privacy Friendly) on Android with an AI agent.** Play checkers on your phone: an agent starts a game, moves pieces by square name and reads whose turn it is.

Target search phrase: _AI agent plays checkers on Android_

Demo shows: `new_game (opponent=bot)`

> Ghost in the Droid seed skill for Checkers (Privacy Friendly) (`org.secuso.privacyfriendlydame`), a simple offline checkers (draughts) game from the SECUSO privacy-friendly apps. COORDINATE TOOLKIT: the position is not readable, see the limits below. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `new_game` | Start a game against the bot (or a human on the same phone) | `opponent` |
| `move` | Move a piece by square name; reports whether it was accepted | `from`, `to` |
| `play_moves` | Play several moves (c3-b4,e3-d4) | `moves` |
| `get_turn` | Read the turn or game-over text | none |

## Toolkit

An agent can drive the whole app with these; compose them.

| Role | Action |
|---|---|
| Entry | new_game |
| Primitives | move, play_moves |
| Read state | get_turn (turn/game over only, NOT the position) |

## Install

The app: F-Droid, or `https://f-droid.org/packages/org.secuso.privacyfriendlydame/`. The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/checkers
```

## Use

```bash
ghost skill run ghost/checkers new_game --device <serial>
ghost skill run ghost/checkers move --param from=c3 --param to=b4 --device <serial>
```

```python
run_skill(name="ghost/checkers", action="move", params={"from": "c3", "to": "b4"})
# {"result": {"accepted": true, "text": "White player's turn"}}
```

Try asking: "Start a checkers game and play c3-b4, then e3-d4."

## Tested on

Real Samsung phone, Android 13 (720x1600, 300 dpi, en-GB), Checkers (Privacy Friendly) 1.3.4. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Dates |
|---|---|---|---|---|
| 1.3.4 | 13 | Samsung real phone (720x1600, 300 dpi, en-GB) | 1.0.1 | 2026-11-06 |

### Recorded failures

- Replacing a resumable board opens an overwrite confirmation. `new_game` confirms that specific prompt before playing; multi-move validation requires every requested move to be accepted.
- HONEST LIMIT: piece positions and colours are not readable; only the turn text is. Use a screenshot to see the board.
- `accepted` is inferred from the turn text flipping; an illegal move leaves the text unchanged and is reported as accepted: false.
- The turn text arrives double HTML-escaped in the dump; the helper unescapes it.
- The bot answers within a second or two; a mandatory capture for you must be played as its own move.

### Popups and first-run screens handled

- The 4-slide welcome is skipped in the start_screen subroutine.
