# prevo - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on and how success is recognised, so an agent can adapt it to another app of this kind or another version.

**Package**: `uk.co.busydoingnothing.prevo` (PReVo, GPL-2.0-only, version 27 from the official F-Droid repository, sha256-verified)
**Verified**: 2026-11-02 on a real Samsung phone, Android 13, 720x1600 @ 300 dpi, en-GB. Offline, no account.
**Skill class**: HARD. No login, no checkpoints.

## Layout reference

- A language picker on first launch, a search screen with a query field and a result list, and an entry screen with the Esperanto headword (for example kat/o) followed by one section per language with its translations. The Serĉi button returns to search.

## Actions

### `open_dictionary(language)`

Force-stops, relaunches and taps the language row if the picker shows.

### `search(term)`

Types the term and reads the result list.

### `open_entry(term, language)`

Types the term, taps the matching row and scrolls to the wanted language section.

### `get_entry(language)`

Scrolls the entry to the wanted section.

### `back_to_search()`

Taps the Serĉi button.

## Adapting

The dictionary language (default angla, English) is chosen once and kept; other names such as germana or franca work for open_dictionary on first launch and for the language param when reading entries. Entries with many derived words are long, so the skill scrolls until the wanted language section is found.
