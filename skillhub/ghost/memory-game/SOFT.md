# memory-game - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.secuso.privacyfriendlymemory` (Memo Game (Privacy Friendly), GPL-3.0, version 1.1.3 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- First launch shows a welcome dialog (OKAY = `android:id/button1`). Start screen: game-mode selector (single/multiplayer arrows), `difficultyBar` (3 stars), `playButton` (NEW GAME).
- Game screen: `gameModeText`, `difficultyText`, `timerView`, `player_one_found_value` (e.g. 0/8), `player_one_tries_value`; the cards are clickable ImageViews in a 4x4 grid (easy) in reading order, with **no description**: the face of a flipped card is only visible in a screenshot.
- A mismatched pair flips back after about a second; a matched pair stays face-up.
- The deal is random every game.

## Actions

### `new_game(difficulty)`

Start screen, tap the difficulty star, tap NEW GAME. Success: 0 pairs, 0 tries, 16+ cards.

### `flip_card(row, col)`

Taps the card at (row, col), returns the status before and after.

### `flip_pair(first, second)`

Taps both cards, waits for a mismatch to flip back. Tries goes up by one; pairs found by one on a match.

### `get_status()`

Reads the status texts. Returns `status`.

## Adapting

Other memory games draw cards as images too: an agent pairs the faces from screenshots and uses the counters to confirm. Grid size is derived from the card positions.
