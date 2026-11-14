# tiktok — SOFT skill (LLM-adaptable narrative)

This document describes the TikTok skill at a **semantic level** — what each action does, what it depends on, and how to recognize success. LLMs use this to adapt the skill to a device or app-version the shipped hard-skill doesn't match.

**Package**: `com.zhiliaoapp.musically`
**Verified**: 2026-08-30 on ASUS ROG (Zenfone 10-class, Android 15, 1080x2400), TT 44.3.3
**Skill class**: HARD (all 8 actions are deterministic; no HITL checkpoints)
**Scope**: user's-own-account, ToS-safe surface only. No mass-outreach, mass-scrape, engagement automation.

---

## Bottom navigation (reference for all actions)

TT bottom-nav has 5 tabs, left → right:
- **Home** (`content-desc="Home"`)
- **Friends** (`content-desc="Friends"`)
- **Post** (center plus button)
- **Inbox** (`content-desc="Inbox"`)
- **Profile** (`content-desc="Profile"`)

Tabs are `clickable=true` and always keyed by `content-desc:`. Empirical y-center on 2400h screens: `~2214`. X-centers: Home=108, Friends=~324, Inbox=756, Profile=972.

---

## Actions

### `open_my_profile()` — LOW complexity

1. Launch `com.zhiliaoapp.musically`
2. Wait for `content-desc="Profile"` (bottom-nav landmark; use this rather than dumpsys — dumpsys reports `SplashActivity` for 30s+ even after the home feed is visible)
3. Tap `content-desc="Profile"`
4. Success signal: `content-desc="Profile menu"` appears (the hamburger in top-right of profile page)

### `open_inbox()` — LOW complexity

Same shape as open_my_profile but tap `content-desc="Inbox"`. No stable post-tap landmark on all TT variants — some land on a notification list, some on a chat list. Accept success on presence of the Inbox tab confirming we made the tap.

### `get_active_account()` — MEDIUM complexity

1. `open_my_profile()`
2. Grep the a11y dump for `@<handle>` — the FIRST match is the active handle (profile header renders it under the display name)

Handle pattern: `@[a-zA-Z0-9_.][a-zA-Z0-9_.]{1,29}` — 2 to 30 chars, letters/digits/`.`/`_`.

### `get_unread_count()` — MEDIUM complexity

1. Navigate to any page that shows the bottom-nav (open_my_profile is convenient)
2. Read the badge on the Inbox tab. Two shapes:
   - **content-desc contains number**: `content-desc="Inbox, 4 unread"` — regex-extract the digit
   - **Small numeric TextView near tab bounds**: text=`"4"` at bounds roughly (648-864, 2100-2220) — bottom-right of the Inbox tab area
3. If neither found → count is 0

### `get_my_stats()` — MEDIUM complexity

1. `open_my_profile()`
2. From the a11y dump, extract:
   - **Handle**: first `@xxx`
   - **Display name**: clickable text= node immediately above the handle in the y-axis (typically `text="my god"` style, has chevron ▼ for account switcher)
   - **Following / Followers / Likes**: three numeric text= nodes above the labels `Following`, `Followers`, `Likes`. Parse `1.2K` → 1200, `3M` → 3_000_000.
   - **Drafts**: optional, appears as `text="Drafts: N"` in the drafts-tab preview

### `list_accounts()` — MEDIUM complexity

**The account-switcher opens by tapping the profile-header display-name area** (the `text="my god"` clickable, not the handle). No stable id — use bounds y ∈ (380, 480) and x-center 540 as fallback.

1. `open_my_profile()`
2. Tap the display-name (opens bottom drawer)
3. Wait for `text="Switch account"` to appear (drawer-open landmark)
4. Enumerate rows: text= nodes in y ∈ (900, 2100) that aren't "Switch account" / "Add account". Each row is one logged-in handle. `selected="true"` marks the currently-active account.
5. Close drawer via BACK

Empirical row spacing: ~176px per row. Row-y = 1086 (first) + 176 × N.

### `switch_account(handle)` — MEDIUM complexity

1. `open_my_profile()`
2. Tap display-name (opens switcher)
3. Wait for "Switch account" landmark
4. Locate the target `handle` in the drawer rows
5. If not present → error: "@{handle} not logged in on this device"
6. If already `selected=true` → no-op success (close drawer)
7. Tap the row (x-center=540, y=row-center) — TT switches accounts, drawer closes automatically, profile re-renders with new handle
8. Verify by re-checking that `@{handle}` now appears as active handle

### `upload_video(video_path, caption, hashtags, inject_tts, action_mode)` — HIGH complexity

The full flow — see `helpers.py:prepare_video_with_tts / push_and_scan_video` and `skill.yaml:upload_video` for the deterministic sequence. Key semantic beats:

1. **Pre-hook**: if `inject_tts`, overlay TTS voiceover on the video BEFORE the ADB flow starts
2. **Media prep**: push video to `/sdcard/DCIM/upload.mp4`, trigger media scan, capture `_id` from MediaStore
3. **Launch via share intent**: `am start -a android.intent.action.SEND -p com.zhiliaoapp.musically -t video/mp4 --es android.intent.extra.STREAM content://media/external/video/media/{media_id}` — this jumps directly to TT's post-page with the video pre-loaded
4. **Caption + TTS**: tap Aa (caption editor), type caption, optionally enable Text-to-speech, tap Done
5. **Next** → hashtag/metadata screen
6. **Append hashtags** to description field (`#tag1 #tag2 ...`)
7. **Ad-authorization** (conditional): if "More options" visible, this account tier requires disclosure — tap through Ad authorization → Content disclosure → Brand toggle → Authorize → Save. Skip if not visible.
8. **Post or Draft**: tap "Post" (immediate publish) or "Drafts" (save without publishing) at the bottom
9. **Success**: post path shows "Posted"; draft path shows video in Drafts folder with caption preserved

The upload flow is the "hardest hard-skill" reference example. It exercises: `launch_intent`, `pre_hooks`, `wait_for_text`, `if_visible` conditional branching, `retry` wrapper on flaky sub-taps, multiple `python_action:` targets, and composite `any_of/all_of` validators.

---

## Popup handling (critical)

TT throws many popups mid-flow:
- FB/Contacts access → "Don't allow"
- Notifications enable → "Not now"
- TikTok Shop relevance → "Select" (or similar dismiss)
- Draft resume overlay → "Save draft" if you want to keep, else navigate around
- Rate the app → "Not now"
- Various promo overlays with no visible dismiss button → press BACK

The skill's `popup_detectors:` array in `skill.yaml` catches all these — engine auto-dismisses before every step. For popups NOT in the catalog: engine's fallback (BACK → screenshot → `UnknownPopupError`) captures them for you to add.

---

## Adapting to a different device or TT version

If your fingerprint doesn't match (`hardware != *` in skill.yaml, or `app_version < 44.0.0`), the engine falls back to Tier 2 Adapt:

1. Loads this SOFT.md as context
2. Loads the current skill's hard-skill as an example
3. LLM re-mines the flow on your device
4. Adjusts the numeric bounds / coord fallbacks in `helpers.py`
5. Emits a new skill.yaml for your fingerprint

Key things LLM should re-verify on adapt:
- Bottom-nav y-coordinate (varies with device screen height)
- Profile-header display-name tap area (no stable id — fallback coords change)
- Account-switcher row spacing
- Popup catalog completeness (new TT versions add new popups)

---

## What this skill does NOT do (intentional exclusions)

- ❌ Send DMs to strangers
- ❌ Mass-crawl hashtags or user pages
- ❌ Auto-like or auto-comment on other users' content
- ❌ Scrape follower lists of other users (privacy + ToS)
- ❌ Automate the sign-up flow (requires a HITL captcha; belongs in a soft-skill variant)
- ❌ Delete the currently-active account (destructive; needs explicit HITL confirmation)

## Login state

Open your signed-in profile with the Profile menu visible before running an account action. The read-only `logged_in` probe checks that positive selector on the current screen. A different screen, language or UI version can return missing/unknown even while a session exists; the runner then stops with `needs_state` rather than guessing. This skill has no automatic login provider. auto-login runner: beta.
