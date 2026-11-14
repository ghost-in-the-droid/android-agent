# wikipedia - SOFT skill (LLM-adaptable narrative)

**Package**: `org.wikipedia` (official Wikimedia app, Apache-2.0; installed from F-Droid)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, app r/50606-r-2026-09-09, en-US, no account.
**Skill class**: HARD. Network needed. No login (editing and sync are out of scope).

## Layout reference

Bottom tabs: `org.wikipedia:id/nav_tab_home` (Explore feed), `nav_tab_reading_lists` (Saved), `nav_tab_search`, `nav_tab_edits`, `nav_tab_more`. Article screen (`PageActivity`): toolbar with content-desc `Navigate up`, bottom bar `id/page_save`, `page_language`, `page_find_in_article`, `page_theme`, `page_contents`.

Article bodies render in a WebView. Ghost Portal exposes the whole article as text nodes in document order: the title node, then the short description with resource id `pcs-edit-section-title-description`, then hatnotes and the lead paragraph split into many inline text nodes. Helpers join them, drop citation markers like `[6]` and leading hatnotes (`For the Oregon artwork, see ...`, `"Turing" redirects here...`).

First run shows four onboarding pages (`Forward` x3, then `Skip` on the interests page) and later a search widget promo (`Close`). All are `popup_detectors`, so any action works on a fresh install.

## Actions

### `search_articles(query, limit)`

Search tab, tap `id/search_card`, type into `id/search_src_text`. Results are title lines directly above description lines. Returns `results: [{title, description}]`.

### `open_article(title)`

`VIEW https://en.wikipedia.org/wiki/<title>` targeted at `org.wikipedia` opens the article in the app. Success: the title node matches the request (underscores and case ignored) and a lead of more than 40 characters was read. Returns `title`, `description`, `lead` (about the first 900 characters, cut at a sentence end).

### `get_featured_article()`

Home feed (`Community` tab). The feed keeps its scroll position, so the helper scrolls to the top and then steps down until the `Featured article` header and its card are rendered together. Returns `date`, `title`, `description`, `extract`.

### `save_article(title)`

Open the article, tap `id/page_save`. A bottom sheet opens listing the article with a bookmark whose content-desc is `Saved` (the same sheet opens on an already-saved article, so the action is idempotent). Read the sheet, press Back. Success: the sheet listed the requested title as Saved.

## Failure modes

- Titles that redirect (e.g. `Turing`) open the target article; the title check then fails by design. Pass the canonical title.
- Very short stubs can have a lead under 40 characters.
