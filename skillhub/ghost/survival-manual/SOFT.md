# survival-manual - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `org.ligi.survivalmanual` (Survival Manual, GPL-3.0-or-later, version 500 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- A navigation drawer with about 30 chapters and a page of large text blocks; the toolbar (menu, search, settings, print) hides on scroll and returns on a small drag down.

## Actions

### `open_manual()`

Force-stops, relaunches and closes the first-run chapter drawer by choosing Introduction.

### `list_chapters()`

Opens the drawer, scrolls it to the top and walks it down to the last chapter.

### `open_chapter(name)`

Opens the drawer, scrolls to the chapter and taps it, then reads the visible page text (up to 1800 characters).

### `read_page()`

Collects the page text nodes (up to 1800 characters).

### `scroll_page(pages)`

Swipes up the page and reads again; the toolbar hides while scrolling.

## Adapting

Text per call is capped at 1800 characters, so read long chapters with scroll_page. Images are not in the text. The in-app search is a find-in-page and is not driven. The chapter title is only visible while the toolbar shows, so read_page after a scroll may return an empty chapter field.
