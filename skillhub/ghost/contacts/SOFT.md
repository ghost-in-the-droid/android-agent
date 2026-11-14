# contacts - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another contacts app or version.

**Package**: `com.google.android.contacts` (Google Contacts)
**Historical device check**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Contacts 4.8.17, en-US, no Google account (contacts live in the local "Device" account).
**Skill class**: HARD. No login, no checkpoints.
**App compatibility**: Contacts >=4.1.17. All four actions passed device-state checks on the loaned API 33 image with Contacts 4.1.17.505591926 on 2026-10-23 (Europe/Berlin); maintainer-run, not independent, deterministic replay with no model. The authored OS fingerprint remains Android >=14; the run artifacts record the actual Android 13 device.

## Layout reference

- Contact list: search pill `id/open_search_bar`, rows `id/cliv_name_textview` (text = display name), header `id/attribution_header` (`Device • N contacts`), FAB `Create contact`.
- Search view: opens over the list; its subtree is rooted at `id/open_search_view` with `id/open_search_view_edit_text`. The list underneath stays in the tree, so results are read only inside the search view subtree.
- Contact page: `id/large_title` (name); each phone row's content-desc is `Call <Type> <number>`, each email row's is `Email <Type> <address>`.

## First-run popups

1. "Contacts works best with a Google Account" sign-in screen: tap `Skip` (detector).
2. "Allow Contacts to send you notifications?" system dialog: tap `Don’t allow` (detector). Ghost Portal cannot read this dialog, so reads fall back to uiautomator and are slow until it is gone.
3. "Now you can find Settings and Help & feedback here" tooltip: only visible as `id/og_tooltip_scrim_view`; tap an empty area.

Each action force-stops Contacts first so it starts on the list, not on a stale search or contact page.

## Actions

### `create_contact(name, phone, email)`

Only `name` is required; `phone` and `email` default to empty. Fire `android.intent.action.INSERT` with MIME `vnd.android.cursor.dir/contact` and extras `name`, `phone`, `email`. The quick editor opens prefilled; tap `id/save_button`. Success: the name appears in the list or as the contact page title, and a fresh ContactsProvider query confirms the name and every requested phone/email on the same contact ID. Phone formatting is normalized; email comparison ignores case. Running it twice creates a duplicate; check with `search_contacts` first.

### `search_contacts(query)`

Tap the search pill, explicitly focus its edit field, type the query, and read `id/cliv_name_textview` rows only inside the search subtree (Portal and XML paths). Filter stale rows using query matches from ContactsProvider (name substring or normalized phone fragment). Returns distinct `contacts: [names]`. The validator independently rereads provider matches and visible search rows; an empty result passes only if the provider has no matches.

### `get_contact_details(query)`

Search, open the first match, read name, phones and emails from the contact page. Returns `contact: {name, phones: [{type, number}], emails: [{type, address}]}`. The validator rereads the contact page and ContactsProvider. The returned name must match the query, and the full returned phone/email sets must equal the provider sets. Conflicting same-name records fail because the page does not expose the selected contact ID. `Call <number>` without a type is supported and returns an empty type string.

### `list_contacts()`

Read the list rows for at most 10 scans, stopping when no new names appear after a nonempty result. Duplicate display names collapse into one entry. Returns `contacts`, `count` and the account header. The validator independently queries ContactsProvider for all display names and checks set equality and the reported count; a truncated or falsely empty collection fails.

## Failure modes

- With a Google account signed in, the list shows several account sections; names still come from `id/cliv_name_textview`.
- Other locales change `Call`/`Email` prefixes in row descriptions.

- `get_contact_details` fails if no result matches or if the UI omits a stored number/email. Provider queries require shell access to ContactsProvider; denied or malformed responses fail validation rather than being treated as empty. Duplicate names with conflicting phone/email sets fail rather than allowing an empty same-name record to excuse omitted numbers.
- List collection is capped at 10 scans and deduplicates names, so it is not a complete count of distinct contact records.
