# Control AntennaPod on Android with an AI agent — find podcasts

Demo shows: `search_podcasts (query=Linux)`

> Ghost in the Droid seed skill for AntennaPod (`de.danoeh.antennapod`), the FOSS podcast app from F-Droid. Browse only, no account.

| Action | What it does | Params |
|---|---|---|
| `search_podcasts` | Directory search: podcast titles and authors | `query` |
| `preview_podcast` | Description and latest episodes of one result, without subscribing | `query`, `title` |
| `list_subscriptions` | Subscribed podcasts | none |

## Install

Install the app from F-Droid (`de.danoeh.antennapod`), then:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/antennapod
```

## Use

```bash
ghost skill run ghost/antennapod search_podcasts --param query=history --device emulator-5554
ghost skill run ghost/antennapod preview_podcast --param query=linux --param title=Unplugged --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/antennapod", action="preview_podcast", params={"query": "linux", "title": "Matters"})
# {"podcast": {"title": "Linux Matters", "author": "Linux Matters", "episodes": [{"title": "Old man hands", "date": "September 29, 2026", ...}]}}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), AntennaPod 3.12.2, en-US. Signed self-runs live in `runs/`.

## Notes

Never subscribes, downloads or plays. Search results come from the Apple and Podcast Index directories through AntennaPod. License: MIT (the skill; the app is GPL-3.0).

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 3.12.2 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 9/9 | 2026-10-05 |

Physical-device launch attempts are also recorded on Samsung SM-A156B (Android 16, 1080×2340, en-US). Results remain action-specific; an attempt does not imply success. See the demos and current signed runs for evidence.

Untested so far: other OEM skins, other screen sizes and other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Notification permission prompt

### Other known failure modes

- Needs network for directory search and previews.
- Directory ranking changes over time; pass `title` to pick a specific show.
