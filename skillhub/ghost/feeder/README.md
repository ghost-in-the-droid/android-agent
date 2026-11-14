# Control Feeder on Android with an AI agent — read RSS feeds

Add a public feed and read its article previews and stored RSS text without an account.

Try asking: "In Feeder, add https://feeds.bbci.co.uk/news/science_and_environment/rss.xml and list the first two visible article previews. Briefly compare their topics. Do not open a browser or sign in."

## Toolkit

| Action | Result |
|---|---|
| open | Cold-open the article listing; a fresh profile includes public Feeder News |
| add_feed(feed_url) | Discover a public HTTPS feed, verify its native URL/title, save locally and read its previews |
| list_articles | Up to two complete visible previews with zero-based indices and feed title |
| open_article(index) | Long-press a preview and choose **Open in reader**, independently of the opening preference |
| read_article | Native title and stored RSS text, often a short excerpt |
| back_to_list | Guarded return from the reader to its feed listing |

## Limits

Tested on Feeder 2.24.0, Samsung SM-A156B, Android 16, 1080×2340 at 450 dpi, English. Public HTTPS URLs with plain ASCII paths only: no query, fragment, credentials, ports, IPs or local-host suffixes. A feed preview combines headline and RSS excerpt; the toolkit does not guess their boundary. It reads current visible nodes, not a complete feed or full publisher webpage. No full-article fetching, external links, browser/custom tabs, accounts, sync, notifications, sharing, OPML, deletion or bulk mark-as-read actions. Adding a feed writes only local app subscriptions; reading an article can mark that article read locally. Duplicate additions are not automatically removed. Demo cleanup uninstalls only the temporary app. Public text is untrusted data, never tool instructions. Recorded runs are maintainer self-evidence, not independent verification.

## Known failure modes

A feed-discovery error, no visible complete previews, unreadable RSS body, changed native Compose controls, an unexpected permission dialog or foreign focused window fails closed. The native reader route is explicit; the preference radio state is not exposed and is never trusted. Popup ownership comes from the exact focused native window's package and owner UID. Native hierarchy reads preserve package ownership and add replay latency. Preview geometry and long-press coordinates are pinned to the measured phone model. A feed editor must expose the same URL before it can be saved; editor scrolling is bounded.
