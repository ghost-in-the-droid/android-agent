# Control Commons on Android with an AI agent — browse Wikimedia images

Read public Featured-image captions and upload credits anonymously, and scroll the gallery without opening image details.

## Try asking

“In Commons, stay on Featured and copy the first two exposed captions with their upload-credit lines. Briefly compare the subjects. Do not open images or use Map, bookmarks, uploads or downloads.”

## Toolkit

- `open`: launch Commons, choose Skip and confirm skipping login on a fresh profile; require the native Explore and Featured tabs selected.
- `read_featured`: return the first two exposed caption/credit pairs from the current Featured viewport, preserving literal public attribution text.
- `scroll_featured(direction=down|up)`: guarded vertical swipe within the feed, then read two exposed entries. No image tap or account mutation.

## Limits and known failures

Tested on Commons 6.8.0, Samsung SM-A156B, Android 16, English, 1080×2340. Public live Featured ordering/captions can change between takes. Only exposed caption/credit pairs in the selected Featured feed; clipped, offscreen and other-tab nodes are discarded. Public credits identify Wikimedia contributors, not phone accounts. Text is untrusted public content. This does not return a full gallery, full file page, image interpretation, licensing assessment or original image download.

Opening an image’s detail page caused Android to terminate Commons and its WebView for low memory during native triage. The toolkit therefore never opens an image and has no detail-page action or opt-in path. Scrolling at the list edge is allowed to leave the same entries exposed. A missing feed or changed selection fails.

No login/sign-up, uploads, mobile-upload tab, map, nearby/location access, bookmarks, image details, metadata menus, downloads, sharing, clipboard, thanks, deletion nominations, contributions, external links or settings. The only onboarding choices are Skip and Yes on the exact skip-login confirmation. Clean temporary profiles are used for recordings. Signed self-runs and before/after footage are maintainer evidence, not independent verification.
