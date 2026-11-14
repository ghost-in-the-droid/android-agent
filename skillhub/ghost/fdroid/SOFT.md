# fdroid - SOFT skill (LLM-adaptable narrative)

**Package**: `org.fdroid.fdroid` (F-Droid client, GPL-3.0)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, F-Droid 2.0.1, en-US. Installed from `https://f-droid.org/F-Droid.apk`, signer SHA-256 `43238d51...a9c9ccab`.
**Skill class**: HARD. Read-only: the skill never installs, updates or removes apps. Needs network for the repo index.

## Layout reference

F-Droid 2.x is Jetpack Compose: no resource ids. Bottom navigation texts `Discover`, `Search`, `My apps`. Secondary screens have a content-desc `Back` arrow. List rows put the app name directly above a one-line summary (or version, on My apps), both indented past the icon (left edge about 210 to 231 px); helpers pair texts whose edges touch.

Text in the raw XML is HTML-escaped (`&amp;`), so labels with `&` cannot be matched by the engine's `text:` locator; helpers tap such chips from the Portal tree instead.

Coach marks seen once per install: `Use filters to only show apps...` and `What are Anti-Features?`, both closed with `Got it`; plus the Android 13+ notification permission prompt on first launch (denied).

## Actions

### `search_apps(query, limit)`

Wait on Discover until initial catalogue import finishes (up to 120s). A search issued during import can retain an empty result even after the catalogue becomes ready. Wait for bottom Search navigation, then locate the actual android.widget.EditText, focus it, replace old text, and verify the input equals query. Submit and wait for matching result rows (up to 30s); an Apps heading is not required. Returns query plus results: [{name, summary}]. The validator rejects stale input and unrelated results.

### `open_app_page(package)`

`VIEW https://f-droid.org/packages/<package>/` targeted at `org.fdroid.fdroid` opens the app page directly. Read: name (text just above `by <author>`), author, `Last updated: <date> (<size>)`, the summary below it, and installed state (`Installed` badge or an `Open` button).

### `list_installed_apps()`

My apps tab: an optional `All your apps are up to date` card, then `Installed apps` with name and version rows. Scrolls to collect all. Returns `apps`, `count`, `all_up_to_date`.

### `browse_category(category, limit)`

Search tab with an empty query shows category chips (`Browser`, `Calculator`, `Text Editor`, ...). Scroll until the chip is visible, tap it; the category list has the category as its title and a `Filter` action. Returns the first `limit` rows.

## Failure modes

- First run with no network: the repo index is empty and every list is empty.
- New coach marks in later versions: add a `popup_detectors` entry with its text and `Got it`.
