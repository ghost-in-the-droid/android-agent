# coin-flip - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.ecos.logic.flip_a_coin` (Flip a coin, AGPL-3.0-only, version 3 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- `coin` (image, content-desc head or tail), `coinLabel` (the result text), `flipAction` (Flip), and a strip of small decorative coin images.

## Actions

### `open_coin()`

Force-stops and relaunches.

### `flip()`

Taps Flip, waits for the animation and reads the coin label.

### `flip_many(count)`

Repeats flip and counts.

### `get_result()`

Reads the coin label.

## Adapting

The app has one coin and no settings. Its versionName is the text DVNE (not a number), so the skill accepts any app version (tested with versionCode 3).
