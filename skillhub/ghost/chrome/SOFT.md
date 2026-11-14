# chrome - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another Chrome build or browser.

**Package**: `com.android.chrome` (Google Chrome)
**Current scope**: Chrome146 on Samsung SM-A156B, Android16, 1080x2340 at450dpi, en-US. Native landmarks below include historical Chrome113 compatibility; it is not new physical verification.
**Skill class**: HARD. No login, no checkpoints.

## Landmarks

- Toolbar: `id/url_bar` (EditText; shows the URL without scheme, e.g. `example.com`), `id/menu_button` (desc `More options`), `id/tab_switcher_button`.
- New Tab Page: the toolbar `url_bar` is still in the tree but with inverted bounds; the visible field is `id/search_box_text`. Tap whichever is really on screen (`helpers:focus_address_bar`).
- The page title is the `text` of the `android.webkit.WebView` node.
- Menu items by id: `id/new_incognito_tab_menu_id`, `id/find_in_page_id`. Find bar: `id/find_query`, `id/find_status` (`i/N`, desc `Result i of N`), `id/close_find_button`.
- Incognito tabs show `id/location_bar_incognito_badge` (desc `Incognito mode`).

## First run and popups

A fresh Chrome shows "Welcome to Chrome" with `Add account to device` and `Use without an account`; always take `Use without an account`. Next comes "Chrome notifications make things easier"; take `No thanks`. Google Search from an EU IP shows a cookie wall ("Bevor Sie zur Google Suche weitergehen" / "Before you continue to Google"); the buttons are below the fold, `Reject all` has the stable HTML id `W0wltc`. The skill always rejects.

## Actions

### `open_url(url, incognito=false)`

Default: targeted HTTP(S) VIEW intent. With incognito=true: enter the exported private launcher directly, focus a visible native address field, quote URL text for Android shell input, submit and wait for exact displayed host plus Chrome-owned private marker and WebView title. Only the host is confirmed; do not claim exact path validation. Lookalike host suffixes fail. Never resume a normal tab as part of private entry.

### `search_web(query)`

Focus the address field, type the query, press Enter (default search engine). Reject the cookie wall if it appears. Success: no cookie wall and the page title contains the query (Google titles are `<query> - Google Search`).

### `open_incognito_tab()`

Launch `com.android.chrome/org.chromium.chrome.browser.incognito.IncognitoTabLauncher` directly and wait for a Chrome-owned private marker; do not open a normal tab first. Success requires native private evidence, never page text.

### `get_page_info()`

Return `{url, title, incognito}` for the current tab.

### `find_in_page(text)`

Menu, `Find in page`, type the text, read `id/find_status` until it is stable (`i/N`), return `matches = N`, close the find bar. `0/0` means no match and is still a success.

## Failure modes

- Engines before 53e2ec1 ran a generic fallback that tapped small Cancel, Skip or Later buttons; it is off for this skill now because it declares its own popups.
- Voice search (`id/voice_search_button`) next to the NTP search box triggers a microphone permission prompt; the skill denies it.

## Current Chrome Incognito markers

Chrome146 on Samsung exposes new_tab_incognito_icon and new_tab_incognito_title on its private new-tab page. These replace the older location_bar_incognito_badge wait. Use only Chrome-owned resource IDs to confirm mode; ordinary page text is not evidence. Existing normal tabs and accounts must stay off-screen.

For loaded Chrome146 pages the badge is absent. Open only the current-model tab grid through native `com.android.chrome:id/tab_switcher_button`; require `tab_switcher_view_holder` and native `search_box_text` exactly `Search your Incognito tabs`. Read the mode without selecting another model or tab. Back returns to the same native address; require that readback before success. A webpage label or secure screenshot flag alone is insufficient.
