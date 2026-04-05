# TikTok

> TikTok automation skill -- upload, crawl, and publish.

![Validate](https://github.com/C-K-Loan/android-agent-skills/actions/workflows/build-index.yml/badge.svg)

## Install

```bash
android-agent skill install tiktok
```

## Actions

| Action | Description |
|--------|-------------|
| `open_app` | Launch TikTok and wait for home screen |
| `navigate_to_profile` | Navigate to the Profile tab |
| `tap_search` | Tap the search icon to open search |
| `type_and_search` | Type a query and execute search |
| `dismiss_popup` | Detect and dismiss TikTok-specific popups |

## Workflows

| Workflow | Description | Steps |
|----------|-------------|-------|
| `upload_video` | Upload a video with caption and hashtags | open_app, upload_flow |
| `crawl_users` | Search users tab, scrape profiles | open_app, tap_search, type_and_search, scrape_loop |
| `publish_draft` | Find and publish a saved draft | open_app, navigate_to_profile, open_drafts, publish |

## Popup Detectors

This skill handles 10 TikTok-specific popups including draft resume overlays, contact access requests, notification prompts, and security checkups.

## Tested On

| Device | Android | Status |
|--------|---------|--------|
| Various devices | 12+ | Pass |

## License

MIT
