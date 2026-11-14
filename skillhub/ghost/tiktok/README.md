# tiktok

> Ghost in the Droid skill: TikTok automation for your own account. ToS-safe surface only.

**8 actions**, all deterministic hard-skill:

| Action | What it does |
|---|---|
| `open_my_profile` | Navigate to your profile tab |
| `open_inbox` | Navigate to your inbox |
| `get_active_account` | Return current active `@handle` |
| `get_unread_count` | Read the unread-notifications badge count |
| `get_my_stats` | Scrape your handle + display-name + followers/following/likes |
| `list_accounts` | Enumerate all logged-in accounts on this device |
| `switch_account` | Switch active account to a given `@handle` |
| `upload_video` | Upload a video via share intent: caption, hashtags, optional TTS, draft or post |

## Install

```bash
pip install ghost-in-the-droid>=1.6.0   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/tiktok
```

## Use

```bash
# Simple: read your own stats
ghost "how many followers do I have on tiktok" --device asus

# Switch accounts
ghost "switch to my my_other_account tiktok" --device asus

# Upload a draft
ghost "upload cat.mp4 to tiktok as a draft with caption 'look at this' and #cat #fyp" --device asus
```

Or programmatically via MCP:

```python
run_skill(name="ghost/tiktok", action="get_my_stats")
# → {"stats": {"handle": "yourhandle", "following": 62, "followers": 10, ...}}

run_skill(name="ghost/tiktok", action="switch_account", params={"handle": "my_other_account"})
# → {"switched_to": "my_other_account"}

run_skill(name="ghost/tiktok", action="upload_video", params={
    "video_path": "/sdcard/DCIM/cat.mp4",
    "caption": "look at this",
    "hashtags": ["cat", "fyp"],
    "action_mode": "draft",
})
```

## Fingerprint

- Android ≥13
- Any hardware (wildcard; tested on ASUS ROG <serial>)
- TikTok app `com.zhiliaoapp.musically` ≥44.0.0

Fingerprint mismatch: the engine falls back to Tier 2 Adapt (LLM re-mines the flow using `SOFT.md` as reference).

## Data access

- `files` (video upload)
- `notifications` (unread badge read)

## Popup handling

`skill.yaml` declares 10 popup detectors auto-dismissed before every step:
FB/Contacts access, notifications enable, TikTok Shop relevance, draft resume overlay, rate-app nag, security checkup, invisible promo overlays, etc.

Unknown popups: the engine takes a screenshot and raises `UnknownPopupError` so the catalog can be extended.

## Not in this skill

- Outreach / DMs to strangers
- Mass-crawl / mass-scrape
- Auto-like / auto-comment / auto-follow
- Account signup (would be a soft-skill with HITL captcha)
- Account deletion

## References

- Schema: [`docs/skill-schema-v2.md`](../../../docs/skill-schema-v2.md)
- Concepts: [`docs/skill-taxonomy-soft-vs-hard.md`](../../../docs/skill-taxonomy-soft-vs-hard.md)
- Contributing: [`docs/contributing-skills.md`](../../../docs/contributing-skills.md)
- Full flow narrative for LLM adapt: [`SOFT.md`](./SOFT.md)

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Evidence |
|---|---|---|---|
| 44.3.3 | 12 (run artifact fingerprint) | asus/ASUS_I002D (ROG, physical, 1080x2400) | 1 signed self-run in `runs/` (`get_my_stats`, pass, 2026-10-05) |
| 44.3.3 | as above | same ROG | maintainer live runs, not signed artifacts: 7/8 actions green, later 8/8 with `upload_video` 10/10 steps (2026-10-05) |

Untested: emulators (TikTok is not installable there without a Play account), other OEMs, other screen sizes, locales other than en-US.

### Recorded failures

None in the signed self-runs. Known from maintainer runs: `upload_video` once stopped at 9/10 steps because the hashtag autocomplete list covered the Drafts button.

### Popups and first-run screens handled

FB friends and contacts access, Facebook access, TikTok Shop relevance, shared collections, notifications, security checkup, rate-the-app, draft resume overlay, avatar upsell (BACK), precise-location upgrade. Storage permission is allowed (`os_popup_policy`) for uploads.

### Other known failure modes

- The home feed autoplays video, so the accessibility tree never reaches idle: `uiautomator dump` fails there. Navigation to Profile uses a coordinate tap on the bottom bar (y 2214 on 1080x2400) and only reads the tree on the static profile page; other screen heights need a new coordinate.
- `dumpsys` reports `SplashActivity` for 30 s or more after the feed is visible; wait on the `Profile` content-desc instead.
- The display name that opens the account switcher has no stable id; `helpers.py` falls back to coordinates.
- "Learn more" alone is too broad to use as a promo detector (it appears on feed captions and ads).
- New TikTok versions add popups; unknown ones raise `UnknownPopupError` with a screenshot so the catalog can grow.
