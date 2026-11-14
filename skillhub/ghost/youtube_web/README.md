# youtube_web

Demo shows: `search_videos (query=android emulator, max_results=5)`

> Ghost in the Droid seed skill for YouTube without an account, through `m.youtube.com` in Chrome (`com.android.chrome`).

| Action | What it does | Params |
|---|---|---|
| `search_videos` | Search and return titles, channels, views/age/length, kind, id | `query`, `max_results` (10), `include_shorts` (false) |
| `get_video_info` | Title, channel, handle, subscribers, stats for a video id; pauses playback | `video_id` |
| `list_channel_videos` | Channel name, subscribers, video count, latest uploads | `handle`, `max_results` (10) |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/youtube_web
```

## Use

```bash
ghost skill run ghost/youtube_web search_videos --param "query=sourdough bread" --param max_results=5 --device emulator-5554
ghost skill run ghost/youtube_web get_video_info --param video_id=jNQXAC9IVRw --device emulator-5554
ghost skill run ghost/youtube_web list_channel_videos --param handle=LofiGirl --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/youtube_web", action="get_video_info", params={"video_id": "jNQXAC9IVRw"})
# {"video": {"video_id": "jNQXAC9IVRw", "title": "Me at the zoo", "channel": "jawed", "subscribers": "6.66M subscribers", ...}}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Chrome 113, en-US, fresh Chrome profile (cookie wall) and reused profile. Signed self-runs live in `runs/`.

## Notes

Why not the YouTube app: on a device that was never signed in to Play, the preinstalled app is too old for YouTube's servers and cannot update. The skill always rejects the cookie wall, never signs in, and pauses playback right away. Read-only: no likes, subscriptions or playlists. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 113.0.5672.136 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 9/9 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- Chrome first-run sign-in screen
- Chrome notification explainer

### Other known failure modes

- A/B layouts change the watch header; both known shapes are handled.
- Result order is personalised by IP and changes between loads.
