# dialer

Demo shows: `dial_number (number=555 123 4567)`

> Ghost in the Droid seed skill for Google Phone (`com.google.android.dialer`). Works without an account. Never places a call.

| Action | What it does | Params |
|---|---|---|
| `dial_number` | Open the dialpad pre-filled with a number (no call) | `number` |
| `get_call_log` | Recent calls with name, detail and type (missed, incoming, ...) | `limit` (default 20) |
| `list_favorites` | Starred contacts on the Favorites tab | none |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/dialer
```

## Use

```bash
ghost skill run ghost/dialer dial_number --param "number=+1 555 123 4567" --device emulator-5554
ghost skill run ghost/dialer get_call_log --param limit=5 --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/dialer", action="get_call_log")
# {"calls": [{"name": "Grace Hopper", "detail": "Mobile | 1 min ago", "type": "missed"}], "count": 1, "missed": 1}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Phone 100.0, en-US. Signed self-runs live in `runs/`.

## Notes

Read-only; `dial_number` stops at the dialpad so a human or another skill decides whether to call. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 100.0.512999549 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 9/9 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Notification permission prompt

### Other known failure modes

- A notification permission dialog may appear on first launch; the detector denies it.
- Other dialers (Samsung) use different tab ids; ACTION_DIAL works everywhere.
