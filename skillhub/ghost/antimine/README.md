# Control Antimine on Android with an AI agent — play Minesweeper

Demo shows: `reveal_first_tile (defaults: difficulty=beginner)`

> Ghost in the Droid seed skill for Antimine (`dev.lucanlm.antimine`), a FOSS minesweeper from F-Droid. Offline, no account.

| Action | What it does | Params |
|---|---|---|
| `start_new_game` | New game at a difficulty | `difficulty`: beginner, intermediate, expert, master |
| `reveal_first_tile` | New game plus the safe opening move | `difficulty` |
| `get_stats` | Recorded statistics | none |
| `get_settings` | Every on/off setting and its state | none |

## Install

Install the app from F-Droid (`dev.lucanlm.antimine`), then:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/antimine
```

## Use

```bash
ghost skill run ghost/antimine start_new_game --param difficulty=expert --device emulator-5554
ghost skill run ghost/antimine reveal_first_tile --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/antimine", action="reveal_first_tile", params={"difficulty": "intermediate"})
# {"game": {"difficulty": "intermediate", "mines_left": 40, "timer": "00:02", "hints": 5, "started": true}}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Antimine 17.6.3, en-US. Signed self-runs live in `runs/`.

## Notes

The board is a canvas, so the skill does not play beyond the first move. License: MIT (the skill; the app is GPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 17.6.3 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 8/8 | 2026-10-05 |

Physical-device launch attempts are also recorded on Samsung SM-A156B (Android 16, 1080×2340, en-US). Results remain action-specific; an attempt does not imply success. See the demos and current signed runs for evidence.

Untested so far: other OEM skins, other screen sizes and other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- First-game tutorial offer

### Other known failure modes

- Further moves need cell coordinates from a screenshot or OCR, because the board is not in the tree; this skill stops after the safe opening move.
