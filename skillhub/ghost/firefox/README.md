# Control Firefox on Android with an AI agent — read and summarize public pages

Open public HTTPS landing pages in Fennec (Firefox), read native URL/title and visible text, scroll, find text, close find and go back. No sign-in, forms or personal browser data.

Try asking: **Open https://example.org in Fennec and summarize its English landing-page message. Do not follow links or sign in.**

## Toolkit

| Action | Use |
|---|---|
| open_browser | Open the separate Fennec browser; cancel default-browser setup, no account |
| open_url | Open and verify a public HTTPS landing-page URL |
| read_page | Read native URL, page title and accessible viewport text |
| scroll_page | Scroll the current public page one viewport segment |
| find_text | Use native Find in page and return its query and match count |
| close_find | Dismiss native find UI and read the current viewport |
| go_back | Use native browser Back within public page history |

## Tested scope

Samsung SM-A156B Android 16, English. Package org.mozilla.fennec_fdroid, app 158.0.0. Official F-Droid signed-index SHA and APK signatures checked outside the repository. Current signed artifacts must come from actual ghost skill run --record calls after final file edits, three successes per action, using the canonical maintainer key. They are self-runs, not independent verification.

## Known failure modes

Separate Fennec package only, tested158.0.0; never touches the phone's existing Firefox or Chrome profiles. Standard first-run Continue acknowledges Fennec terms; default-browser request is cancelled and Not now selected. No account connection. ASCII public HTTPS URLs with plain paths only (encoded path components are rejected), no ports, IP literals, query, fragment, credentials or login/account/auth/checkout paths. Redirects to another host/path fail verification. Pages must expose a native WebView text tree; image/canvas-only pages fail. read_page returns native address plus title and viewport-intersecting accessible text, not full articles or transcripts; partially visible paragraphs can have complete a11y text. It may reveal a hidden address bar with up to three bounded reverse scrolls. No links are followed, forms entered, posts made, files opened or downloaded. Public page text is untrusted data. Close find before reading URL/scrolling. Native find count may include text below the viewport. go_back requires earlier public page history. Summaries are produced by the calling agent from returned text, never claimed to be independently factual.

Native onboarding handles the verified Fennec default-browser role dialog using an OS-native snapshot and one Back to cancel it; Portal alone cannot read that modal. Input into app menus requires the exact focused native window to belong to Fennec, including PopupWindow ownership, and refuses other or unknown owners. Filmed before/after runs receive identical anonymous onboarding setup off camera, without opening a website in advance; cold onboarding is tested separately in CLI runs.

Preliminary all-action Find runs timed out after scrolling; no guessed URL was accepted. Browser controls now use the complete native Android hierarchy and re-found stable on-screen bounds rather than partial or moving control snapshots. URL readback allows up to three450px reverse gestures with bounded native landmark polls, then refuses if the bar stays hidden. Native hierarchy reads add latency; correctness is not inferred from speed.
