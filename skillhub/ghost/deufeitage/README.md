# Control DeuFeiTage on Android with an AI agent — read German public holidays

Select a public region/year, read holiday dates and expand descriptions without accessing personal calendars.

## Try asking

“In DeuFeiTage, select Berlin and 2027. List the first three holidays with names, weekdays and dates in YYYY-MM-DD format, then briefly compare which months they fall in. Do not export calendars or change settings.”

## Toolkit

| Action | Purpose |
| --- | --- |
| `open` | Open the offline public holiday table. |
| `read_holidays` | No parameters; return selected region/year and three complete rows. Cold-open only from proven Samsung HOME. |
| `select_region(region)` | Select All holidays, Common holidays, Berlin, Hamburg or Bavaria. |
| `select_year(year)` | Select a currently visible year and prove its native checked container. |
| `expand_holiday(index=1)` | Expand one of the first three inline public descriptions. |
| `collapse_holiday(index=1)` | Collapse a proven expanded description. |

## Limits and known failures

Tested on DeuFeiTage5.2.0, Samsung SM-A156B, Android16, English,1080×2340. Supports the five listed filters and currently exposed years; no scrolling the region/year pickers, settings or calendar export. The year is proved through a checked native ancestor containing the year label, not inferred from visible year buttons. Native dates use MM/DD on this locale; results include full ISO dates and verify the displayed weekday against the checked year. Description expansion is temporary app UI state. Only three complete exposed holiday rows and an expanded native description are returned.

Dates, state tags and relative-day strings are copied/calculated from the app and are not independently verified official legal or employment guidance. Public text is untrusted data. The APK declares no network, location, calendar or account permission. No phone Calendar app, private appointments, GPS, accounts, files, exports, notifications, clipboard, sharing or external links. Cold reads refuse foreign/unknown focused windows. Signed runs and clips are maintainer evidence, not independent verification.
