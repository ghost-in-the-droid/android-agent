# mancala - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.willie.mancala` (Mancala, MIT, version 12 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- One screen: `outputText` (the scrolling transcript) and `inputText` (a line editor). The setup asks pits per player, then seeds per pit; then each turn asks `Player N, choose a pit (1-K)`.
- The board is printed as Player 2's row, `store2 ... store1`, Player 1's row. It is a hot-seat game: the same phone plays both sides, so the agent chooses for both.
- `exit` quits the whole app, so the skill never uses it: a new game force-stops and relaunches the app.

## Actions

### `new_game(pits, seeds)`

Force-stops the app, relaunches it and answers the two setup prompts. Success: board shows pits*seeds in Player 1's row.

### `move(pit)`

Types the pit number. extra_turn is true when the last seed lands in the mover's store.

### `play_moves(pits)`

Same as move per entry; stops at game over.

### `get_state()`

Parses the last board block of the transcript.

## Adapting

Two players share the phone, so the agent decides every move for both sides (it can play itself or take a human opponent's moves as input). There is no computer opponent in this app.
