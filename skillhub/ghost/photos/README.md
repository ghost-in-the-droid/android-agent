# photos

Demo shows: `list_photos (defaults: max_items=50)`

> Ghost in the Droid seed skill for Google Photos (`com.google.android.apps.photos`) as an on-device gallery, no account.

| Action | What it does | Params |
|---|---|---|
| `list_photos` | List photos and videos (newest first) with date taken and folder | `max_items` (default 50) |
| `open_photo` | Open an item full screen | `index` (0 = newest) |
| `count_trash` | Report how many items are in Trash | none |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/photos
```

## Use

```bash
ghost skill run ghost/photos list_photos --device emulator-5554
ghost skill run ghost/photos open_photo --param index=0 --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/photos", action="list_photos", params={"max_items": 10})
# {"items": [{"kind": "photo", "taken": "Oct 5, 2026 8:12:33 PM", "folder": "GhostSeed"}], "count": 1, "folders": ["GhostSeed"]}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Photos 6.29, en-US, fresh app data each run (`pm clear`). Test media was created on the device with `screencap` into `/sdcard/Pictures/GhostSeed/`. Signed self-runs live in `runs/`.

## Notes

Never signs in and never turns on backup; the skill only reads the library and opens the viewer. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 6.29.0.519265844 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0, 1.0.1 | 11/12 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

- 2026-10-05, v1.0.0, `open_photo`: `TimeoutError_`; the newest library item was a video and Android's one-time "Viewing full screen" hint covered the viewer; fixed in 1.0.1 (video player accepted) and in the engine's OS popup layer (hint dismissed).

### Popups and first-run screens handled

- Notification permission
- Update promo (no Play account to update with)
- OS permission policy: {"allow_permissions": ["storage"]}

### Other known failure modes

- Photos hides exact duplicates (same pixels), so the item count can be lower than the file count.
- Search without backup only offers device-folder chips; it is not used.
