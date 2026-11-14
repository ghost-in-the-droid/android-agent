# Control Birdipedia on Android with an AI agent — browse bird names

Search the offline bird catalog and read common/scientific names without opening eBird or using location.

Try asking: **In Birdipedia, filter robin and list the first two complete common and scientific names. Briefly compare their names; stay in the catalog and do not open bird cards, links, settings or share anything.**

## Toolkit

| Action | Role | Parameters | Returned data | Side effects |
| --- | --- | --- | --- | --- |
| open | Entry | none | Query, two complete birds, taxonomic groups | Opens temporary app UI |
| filter_birds | Primitive | query, 1–40 ASCII letters/spaces/hyphens | Native query and two complete birds | Temporary UI filter |
| clear_filter | Primitive | none | Unfiltered first two birds | Clears UI filter |
| scroll_results | Primitive | none | Two complete rows after a proven scroll | Scroll position |
| read_results | Read state | none | Common/scientific names and exposed group labels | None; opens catalog only from HOME |

## Limits

Only two fully exposed native name pairs are returned; partial rows are excluded. Taxonomic order/group headings are copied, not inferred. Bird cards open external eBird pages, so this toolkit never taps one. No photos, sound, conservation-status inference, GPS, settings or personal data. Sources may change taxonomy; this is the app's bundled display, not independent species identification. The APK declares INTERNET for optional features; this toolkit contains no network calls and reads the bundled catalog only.

## Known failure modes

Missing query/toolbar evidence, fewer than two complete results, foreign foreground, unsupported query text or a scroll that does not change the first rows fail loudly. Empty/no-match queries are outside this toolkit's bounded result contract. A fresh open resets the activity; use read_results to preserve an existing filter. The first unshipped draft scroll was obscured by the keyboard and failed; its four passes and one failure are archived with that obsolete digest. Query actions now hide the IME only when input-method state proves it is shown, then recheck app focus before scrolling. Current evidence binds to the corrected files.

## Tested scope

Samsung SM-A156B, Android16,1080x2340,450dpi; Birdipedia1.1.3, English UI. Maintainer-run actual device evidence, not independent verification. Default official signing identity, three clean-profile cycles per action after final files.
