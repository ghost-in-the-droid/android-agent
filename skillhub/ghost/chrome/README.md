# Control Chrome on Android with an AI agent — browse public web pages

Open public pages, search, create private tabs, read the current page and count matches. No account is required.

| Action | Behavior | Parameters |
|---|---|---|
| `open_url` | Open HTTP(S), verify exact displayed host; optional private tab | `url`, optional `incognito=false` |
| `search_web` | Search in the current tab using the default engine | `query` |
| `open_incognito_tab` | Enter a new private tab directly | none |
| `get_page_info` | Address-bar text, native WebView title and private marker | none |
| `find_in_page` | Read match count and close Find | `text` |

## Private entry in 1.0.2

`open_incognito_tab` uses Chrome's exported Incognito launcher without first resuming a normal tab. `open_url(incognito=true)` enters a new private tab, types the URL into the native address editor and verifies host plus Chrome-owned private evidence. An already visible tab model is preserved by read/search subroutines. For existing callers, `open_url` still defaults to normal-tab behavior. Callers that need privacy must request `incognito=true` and keep all subsequent actions in that private tab.

Blank private tabs use Chrome-owned `location_bar_incognito_badge`, `new_tab_incognito_icon` or `new_tab_incognito_title`. Chrome146 hides these on loaded pages; there the helper briefly opens the current-model native tab grid, requires `tab_switcher_view_holder` plus Chrome-owned `search_box_text` exactly “Search your Incognito tabs”, then returns to the same URL. It never switches tab models. A web page claiming to be private is insufficient. Unknown private state fails closed. URL validation confirms the displayed host, rather than the complete requested path; it rejects lookalike host suffixes. Displayed URLs may omit the scheme or `www.`.

## Use

```bash
ghost skill run ghost/chrome open_url --param url=https://example.org --param incognito=true --device YOUR_DEVICE
ghost skill run ghost/chrome find_in_page --param text=documentation --device YOUR_DEVICE
```

## Verification and limits

Current physical verification is limited to Chrome 146.0.7680.119 on Samsung SM-A156B, Android 16, 1080×2340 at 450 dpi, en-US, using anonymous private tabs and public pages. No normal profile/account data is inspected or cleared. Three current self-runs per action are required after final file edits. Signed artifacts are canonical maintainer self-runs, not independent verification; stale/noncanonical artifacts are removed.

Historical emulator runs used Android 14/Chrome 113. One historical `find_in_page` run timed out before the Find bar rendered; later attempts passed. That history does not establish current-version or cross-device coverage. Other OEM/OS/browser versions remain unverified.

First-run account creation and sync are declined. Google cookie consent is rejected when its known controls appear. Network errors, changed selectors, CAPTCHAs or unrecognised consent pages may fail; there is no bypass. Find depends on native `i/N` status. Private capture may be OS-protected; changing a capture flag is demo setup outside this skill and must be restored afterward. Demo-created private tabs must be closed without affecting existing tabs.

License: MIT.

The first current re-verification failed rather than accepting a loaded private page without a visible private badge. The native grid readback above addresses that observed Chrome146 difference; a protected screenshot alone is not accepted as mode proof.
