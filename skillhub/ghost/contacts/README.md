# contacts

Demo shows: `create_contact (name=Grace Hopper, phone=+1 555 0199)`

> Ghost in the Droid seed skill for Google Contacts (`com.google.android.contacts`). Works without a Google account, on local device contacts.

| Action | What it does | Params |
|---|---|---|
| `create_contact` | Create a local contact (insert form, then Save) | `name` (required), `phone`, `email` (optional, default empty) |
| `search_contacts` | Names matching a query | `query` |
| `get_contact_details` | Phones and emails of the first match | `query` |
| `list_contacts` | Unique names collected over at most 10 list scans | none |

## Install

```bash
pip install "ghost-in-the-droid>=1.6.0"   # 1.6.0 is not on PyPI yet: until it ships, git clone the repo and `pip install -e .`
ghost skill install ghost/contacts
```

## Use

```bash
ghost skill run ghost/contacts create_contact --param "name=Ada Lovelace" --param phone=+15551234567 --device emulator-5554
ghost skill run ghost/contacts get_contact_details --param query=Ada --device emulator-5554
```

From any MCP agent:

```python
run_skill(name="ghost/contacts", action="get_contact_details", params={"query": "Ada"})
# {"contact": {"name": "Ada Lovelace", "phones": [{"type": "Mobile", "number": "+1 555-123-4567"}], "emails": [...]}}
```

## Tested on

Android 14 emulator (google_apis x86_64, 1080x2400, 420 dpi), Contacts 4.8.17, en-US. Signed self-runs live in `runs/`.

## Notes

The first launch shows a Google sign-in screen and a notification prompt; the skill skips and denies them. `create_contact` does not deduplicate. The tested setup has no signed-in account; local contact creation changes device state. Account sync behavior on a signed-in device is outside that setup. License: MIT.

## Known failure modes and versions tested

### Versions tested

| App version | Android | Device | Skill version | Signed self-runs (pass/total) | Dates |
|---|---|---|---|---|---|
| 4.8.17.529259023 | 14 | Google/sdk_gphone64_x86_64 (emulator, 1080x2400, 420 dpi, en-US) | 1.0.0 | 12/12 | 2026-10-05 |

Untested so far: physical devices, other OEM skins, other screen sizes, other locales.

Historical self-run artifacts are retained in `runs/`, but the current registry rejects the pre-digest evidence as `unbound-helper`. These old counts do not establish current-version passing coverage; fresh digest-bound signed runs are pending.

### Recorded failures

None in the signed self-runs.

### Popups and first-run screens handled

- First-run Google sign-in prompt
- Notification permission prompt

### Other known failure modes

- With a Google account signed in, the list shows several account sections; names still come from `id/cliv_name_textview`.
- Other locales change `Call`/`Email` prefixes in row descriptions.

## Compatibility and validation

The manifest targets Android >=14, Contacts >=4.1.17, 1080x2400 at 420 dpi, en-US. `create_contact` checks the visible name and independently queries ContactsProvider for the saved name, phone and email on one contact ID. Search/details/list compare returned results against fresh provider rows; search and details also reread the UI. Empty search/list results pass only if no provider rows match. Denied provider access fails validation.

- `get_contact_details` fails if no result matches. Search supports normalized phone fragments as well as name substrings. Untyped phone descriptions retain the full number.
- List collection is capped at 10 scans and deduplicates names, so it is not a complete count of distinct contact records.
