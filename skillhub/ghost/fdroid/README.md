# Control F-Droid on Android with an AI agent — search Android apps

Demo shows: `search_apps (query=podcast, limit=5)`

> Ghost in the Droid seed skill for the F-Droid client (`org.fdroid.fdroid`). Read-only, no account.

| Action | What it does | Params |
|---|---|---|
| `search_apps` | Search the catalogue, return names and summaries | `query`, `limit` |
| `open_app_page` | Open an app page by package and read its details | `package` |
| `list_installed_apps` | List installed apps F-Droid knows, with versions and update state | none |
| `browse_category` | Open a category and list its first apps | `category`, `limit` |

## Install

The app: `https://f-droid.org/F-Droid.apk` (verify the signer). The skill:

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/fdroid
```

## Use

```bash
ghost skill run ghost/fdroid search_apps --param query="podcast" --param limit=5 --device emulator-5554
ghost skill run ghost/fdroid open_app_page --param package=org.wikipedia --device emulator-5554
```

```python
run_skill(name="ghost/fdroid", action="open_app_page", params={"package": "net.gsantner.markor"})
# {"name": "Markor", "author": "Gregor Santner", "last_updated": "Mar 21", "size": "12.05 MB", "installed": true, ...}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), F-Droid 2.0.1, en-US. Signed self-runs in `runs/`. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 2.0.1 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 12/12 | 2026-10-05 |

Physical-device launch attempts are also recorded on Samsung SM-A156B (Android 16, 1080×2340, en-US). Results remain action-specific; an attempt does not imply success. See the demos and current signed runs for evidence.

Untested so far: other OEM skins, other screen sizes and other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Filter coach mark (first category or search visit)
- Anti-Features coach mark (first app page)
- Notification permission (first launch)

### Other known failure modes

- First run with no network: the repo index is empty and every list is empty.
- New coach marks in later versions: add a `popup_detectors` entry with its text and `Got it`.

## Samsung SM-A156B search regression fix (1.0.1)

Search uses the actual editable field rather than a fixed toolbar coordinate. Existing text is replaced, and the visible input must equal the requested query. The validator also checks returned rows against that query. No install/update buttons are pressed.

A fresh F-Droid install downloads and imports its catalogue. Issuing a search during that import can leave an empty result until the query changes. The skill waits on Discover for initial import completion before searching, then waits for the bottom navigation to settle. It does not require an obsolete Apps heading. Initial import is bounded at 120s; result loading at 30s. A failed import or unmatched query fails explicitly. Queries must be typeable in the tested English UI.

Three consecutive clean-reset Markor searches passed on Android 16 Samsung SM-A156B, F-Droid 2.0.0, on 2026-11-03: 54.09s, 50.69s, 52.57s. Most time is catalogue import; a populated catalogue is faster. The earlier filmed agent's literal-{query} diagnosis was not confirmed: engine traces retain unresolved YAML even though dispatch interpolates it.

Version1.0.2 polls query readback for up to2s before submission. Search results still require a literal query token in visible title/summary; legitimate semantic-only matches can fail safely.

Recorded setup failure: a transient null foreground during launch caused the package guard to refuse before search. The current engine reads the full focused-window line and retries only an empty owner twice at100ms intervals; a denied package is still rejected immediately and persistent unknown focus still fails closed. Final CLI replays use that engine behavior.
