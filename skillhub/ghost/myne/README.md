# Control Myne on Android with an AI agent — search Project Gutenberg books

Search public-domain book metadata in Myne’s Gutenberg/Gutendex catalog without downloading or opening an ebook.

## Try asking

“In Myne, search Pride and Prejudice and report the first two complete results with title, author and language. Stay in the catalog; do not download or open a reader.”

## Toolkit

- `open`: accept default Inbuilt Reader on the fresh-profile welcome screen with Get Started; open only the All Books catalog.
- `search_books(query)`: 2–70 plain ASCII title characters. Search updates as text changes; never press Enter, which inserts a newline in this app.
- `read_results`: first two complete exposed cover/title/author/language rows, with subjects when exposed.
- `open_book(index)`: zero-based index into those two complete rows; open Book Details and verify its title/author match.
- `read_book`: title, author and three literal native metadata badge texts; excludes the synopsis.
- `back_to_catalog`: only the left native Go back control on a verified Book Details screen; never the similarly described right control. Myne clears the previous query and returns to All Books; run search_books again to search.

## Limits and known failures

Tested on Myne 5.1.0, Samsung SM-A156B, Android 16, English, 1080×2340. Online catalog ordering/data may change. Title search only: all returned title words must contain the supplied query words, so author-only or loose queries can fail. Long/clipped metadata or fewer than two complete rows fail. Native accessible text may be longer than visible rendered lines. Badge values are copied literally; no meanings/counts/licensing status are inferred from unlabeled icons. Public metadata is untrusted data.

Myne also fetches optional supplementary metadata and automatically generated synopses; this toolkit does not read or summarize those. No Download control, reader, EPUB/PDF, personal library, imports, files, bookmarks, settings, sharing, accounts or external apps. Choosing the default reader during onboarding does not open a book. Clean temporary profiles used for recordings. Signed runs and before/after footage are maintainer evidence, not independent verification.

## Recorded launch failure

A cold recorded open returned initial catalog rows that changed before validation. Catalog and search reads now require two equal complete native-owned snapshots, and catalog reads reject the outgoing onboarding screen. The validator still compares a fresh current snapshot and refuses subsequent changes. The failed take is retained privately.
