# flip-a-coin - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.ecos.logic.flip_a_coin` (Flip a coin, AGPL-3.0-only, version 3 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- One screen: a big coin in the middle (its description reads head or tail), a row of small coin pictures and a Flip button at the bottom.

## Actions

### `open_coin()`

Force-stops and relaunches.

### `flip()`

Taps Flip and waits for the coin to settle.

### `flip_many(count)`

Taps Flip repeatedly, reading the coin after each settles.

### `get_coin()`

Reads the coin description.

## Adapting

The result is read from the coin description after the toss animation settles (about 3.5 seconds per flip). Coin style selection is not driven. flip_many allows up to 20 flips.
