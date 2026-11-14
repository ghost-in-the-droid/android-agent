# youtube_web - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to the YouTube app or another browser.

**Package**: `com.android.chrome` driving `https://m.youtube.com` (no account)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Chrome 113, en-US, German IP.
**Skill class**: HARD. No login, no checkpoints.

## Why the web client

The YouTube app preinstalled on the image (19.17.42) shows "Update available" and every search fails with "There was a problem with the server [400]". Updating needs a Play account, so on a never-signed-in device the mobile site is the dependable path. On a device with a current YouTube app, adapt these actions to the app (same URLs open in it).

## How it works

Each action opens a URL with a VIEW intent targeted at Chrome (`--es com.android.browser.application_id ghost.youtube_web` keeps it in one tab): `/results?search_query=<q>`, `/watch?v=<id>`, `/@<handle>/videos`. From an EU IP the first visit redirects to `consent.youtube.com` ("Before you continue to YouTube"); the skill scrolls to `Reject all` and taps it. The consent endpoint sometimes hangs or returns 502; the skill reloads the target URL after 12 s and rejects again if needed.

## Landmarks

- Video rows: a text node `<title> by <channel> <N views> <age> <length>` (live: `... by <channel> 19 thousand watching`); the channel also appears as `Go to channel <channel>` just before it. Ids come from nodes whose desc contains `watch?v=<11 chars>` near the row; YouTube does not expose one for every row, so `video_id` can be null.
- Shorts shelf rows: `<title>, <N views>, <channel>, <age> - play Short`.
- Watch page: `id=movie_player` (the player), then either one header text `<title> @handle <likes> <views or watching> more` or separate nodes (title, `Uploaded by x.`, likes, views, age), then a node with desc `<channel>, <subs> subscribers. Go to channel.`.
- Channel page: `<name>, Official Artist Channel`, `@handle`, `<N> subscribers`, `<N> videos`, tab row, then video rows as above.

## Actions

### `search_videos(query, max_results, include_shorts)`

Return `{query, videos: [{title, channel, meta, kind, video_id}], count}`, scrolling until `max_results` or the end of the page. Shorts are skipped unless `include_shorts`.

### `get_video_info(video_id)`

Return `{video: {video_id, title, channel, handle, subscribers, stats}}`. The video autoplays muted; the skill sends `MEDIA_PAUSE` immediately.

### `list_channel_videos(handle, max_results)`

Return `{channel: {handle, name, subscribers, videos_total, videos[]}}` from the Videos tab (newest first).

## Failure modes

- A/B layouts change the watch header; both known shapes are handled.
- Result order is personalised by IP and changes between loads.
