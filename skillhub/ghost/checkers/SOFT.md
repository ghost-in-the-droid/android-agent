# checkers - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.secuso.privacyfriendlydame` (Checkers (Privacy Friendly), GPL-3.0, version 1.3.4 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- First launch shows 4 welcome slides (`btn_skip`). Start screen: opponent selector (`section_label` Human/Bot, `arrow_right`), `play_button` (NEW GAME), `continueButton`.
- Game screen: an 8x8 board of 89 px squares starting at x 4, y 154 (720 px width). The 32 dark squares are clickable ImageViews **without any description**; piece colours and positions are NOT in the accessibility tree. The only readable state is the text under the board (`White player's turn`, `AI player's turn`, a winner text at the end).
- A move is two taps (from square, to square). Squares use standard names: a1 is the dark bottom-left square, you are white at the bottom, the bot is black.

## Actions

### `new_game(opponent)`

Start screen, pick the opponent with the arrow, tap NEW GAME. Success: turn text shown.

### `move(from, to)`

Taps both squares, then watches the turn text flip away from White and back. `accepted: false` means nothing happened (illegal move). Returns the turn text.

### `play_moves(moves)`

Same as move per entry; stops at the first rejected move or at game over.

### `get_turn()`

Reads the text under the board.

## Adapting

The position can only be read from a screenshot (an agent with vision). Multi-jump captures are two taps per jump in the app; play them as separate moves.
