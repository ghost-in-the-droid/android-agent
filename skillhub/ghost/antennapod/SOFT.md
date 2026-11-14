# antennapod - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another podcast app or version.

**Package**: `de.danoeh.antennapod` (AntennaPod, GPL-3.0 FOSS app, installed from the official F-Droid repository, sha256-verified)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, AntennaPod 3.12.2, en-US. No account (AntennaPod has none; gpodder/Nextcloud sync is never touched).
**Skill class**: HARD. Browse only: never Subscribe, Download or Play.

## Layout reference

- Search opens with AntennaPod's own deep link `https://antennapod.org/deeplink/search?query=<q>` (VIEW, `-p de.danoeh.antennapod`). It first searches local subscriptions; the `id/actionButton` `Search online` runs the directory search (Apple and Podcast Index, footer `id/search_powered_by`).
- Results: `id/txtvTitle` with `id/txtvAuthor` directly below.
- Feed preview (`OnlineFeedViewActivity`): `id/txtvTitle`, `id/txtvAuthor`, `id/headerDescriptionLabel`, `id/butSubscribe` (never tapped), then `Episodes preview` rows: `id/txtvTitle`, `id/txtvPubDate` (desc carries the full date), `id/size`, `id/txtvDuration`.
- Bottom tabs: `id/bottom_navigation_home|queue|inbox|subscriptions|more`.

## Top-band safety

`Search online` and the first results sit in the band where heads-up notifications appear; taps there go through `guarded_tap` (refuses while SystemUI's `mHeadsUpPinnedMode` is true).

## Actions

### `search_podcasts(query)`

Deep link search, `Search online`, poll until results render (network). Returns `results: [{title, author}]`.

### `preview_podcast(query, title)`

Search as above, open the first result whose title contains `title` (or the first result), read the preview. Returns `podcast: {title, author, description, episodes: [{title, date, duration, size}]}`. Success also requires the Subscribe button to still be offered, which proves nothing was subscribed.

### `list_subscriptions()`

Subscriptions tab; titles of subscribed podcasts, `[]` on a fresh install.

## Failure modes

- Needs network for directory search and previews.
- Directory ranking changes over time; pass `title` to pick a specific show.
