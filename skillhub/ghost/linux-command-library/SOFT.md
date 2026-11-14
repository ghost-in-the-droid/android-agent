# linux-command-library - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `com.inspiredandroid.linuxcommandbibliotheca` (Linux Command Library, Apache-2.0, version 175 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- Start: search field and category rows (One-liners, System control, Files & Folders, ...), tabs Basics, Tips, Commands.
- Search: `Commands (n)` and one row per result.
- Command page: header with Back, Search in page, Expand all, Add bookmark; accordion sections TLDR, SYNOPSIS, DESCRIPTION, PARAMETERS, INSTALL, CAVEATS, HISTORY, SEE ALSO.

## Actions

### `open_library()`

Force-stops and relaunches.

### `search_commands(query)`

Types the query into the search field (clearing the old one) and reads the result rows.

### `open_command(name)`

Taps the matching result row.

### `read_section(section)`

Scrolls to the header, expands it if collapsed and reads the text, scrolling for long sections.

### `get_state()`

Reads the search field, result rows or command header.

## Adapting

Categories, the Basics and Tips tabs, bookmarks and the AI tools are not driven. The sections list in the state only contains the headers visible on screen.
