# navy-fleet-battle - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `net.tigr.navyfleetbattle` (Navy Fleet Battle, GPL-3.0-only, version 8 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Menu: Play the computer. Placement: Random, Ready. Battle: status line (Your turn / Computer's shot), hint line, enemy ships left, a Fire! button; the enemy field is 10 x 10 (rows A-J, columns 1-10) tapped by pinned coordinates.

## Actions

### `open_menu()`

Force-stops and relaunches.

### `new_game()`

Restarts the app, taps Play the computer, Random and Ready. Placement is random, so the fleet differs every game.

### `fire(cell)`

Taps the cell and Fire!, then waits. After a hit you shoot again; after a miss the computer shoots and the call returns when it is your turn. Refuses a cell that was already fired at.

### `fire_many(cells)`

Repeats fire and stops when the game is over.

### `get_state()`

Reads the status text and the ship counters.

## Adapting

Cells are tapped by pinned coordinates for a 720x1600 screen. Hit and miss on a cell are not readable as text: a hit is announced in the hint line (hit, shoot again), a miss is recognised because the computer answers. Keep your own list of cells already fired at; the skill refuses a repeated cell. The computer's own shot result is not readable.
