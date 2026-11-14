# gallery

Demo shows: `open_photo (name=ghost_green.png)`

> Ghost in the Droid seed skill for Fossify Gallery (`org.fossify.gallery`), a FOSS gallery from F-Droid. Offline and read-only.

| Action | What it does | Params |
|---|---|---|
| `list_albums` | Albums with item counts | none |
| `list_photos` | File names in an album | `album` |
| `open_photo` | Open a photo or video by file name | `name` |
| `get_photo_properties` | Name, path, size, resolution, last modified | `name` |

## Install

Install the app from F-Droid (`org.fossify.gallery`), then:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/gallery
```

## Use

```bash
ghost skill run ghost/gallery list_albums --device emulator-5554
ghost skill run ghost/gallery get_photo_properties --param name=IMG_0042.jpg --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/gallery", action="list_photos", params={"album": "Camera"})
# {"album": "Camera", "photos": ["IMG_0042.jpg", ...], "count": 12}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Fossify Gallery 1.13.1, en-US. Signed self-runs live in `runs/`.

## Notes

Grants photo access when asked; declines all-files access. Never edits, shares or deletes. License: MIT (the skill; the app is GPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 1.13.1 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 12/12 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Photos and videos permission
- All-files access request
- OS permission policy: {"allow_permissions": ["photos"]}

### Other known failure modes

- Fossify Gallery asks for access to all files on every launch; the skill declines with BACK and works with media access only.
- Android 14 asks for photo access (`Allow all` is chosen); with partial access only the selected photos are listed.
- Album cards and Properties sit in the top band; taps there go through a guard that refuses while a heads-up notification is pinned.
- Needs at least one image on the device; the test fixture is three 320x240 PNGs in `/sdcard/Pictures/GhostTest/`.
