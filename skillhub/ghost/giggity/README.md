# Control Giggity on Android with an AI agent — browse conference programs

Read preconfigured public conferences, their exposed program labels and session details without reminders, bookmarks or personal calendars.

## Try asking

“In Giggity, list the first three complete preconfigured conference names with their displayed date ranges, then briefly compare those ranges. Stay in the catalog: do not add schedules, open links, set reminders, create shortcuts or change settings.”

## Toolkit

| Action | Purpose |
| --- | --- |
| `open` | Deny temporary-app notifications, open the public catalog and await its online update. |
| `read_catalog` | No parameters. Read three complete native conference/date rows; cold-open only from Samsung HOME. |
| `open_conference(name)` | Tap an exact exposed preconfigured name and verify its native program header. |
| `read_program` | Read displayed date/header and exposed native session labels; no duration or room association inferred from grid widths. |
| `open_session(title)` | Tap a unique exposed session in a non-overlapping native region and verify its detail title. |
| `read_session` | Read title, room, raw displayed time and a description preview up to400 characters. |
| `close_session` | One guarded Back only from proven detail with Remind me unchecked, then verify program. |

## Limits and known failures

Tested on Giggity3.0.3, Samsung SM-A156B, Android16, English,1080×2340. Canonical program: IETF127 San Francisco, Code Sprint. The preconfigured catalog automatically updates from its public online source; the initial bundled catalog can be older. Recorded open waits for the updated Later section. If no Later section/update is available or fewer than three full conference/date rows are exposed, fail closed. Current native ordering and date strings are returned, not a global ranking or an assurance that dates are final. Catalog can include past and future conferences; no phone location is used.

Program scope is exposed native session labels, not complete timetable reconstruction. Room/session associations and durations are not inferred from grid geometry. Session detail returns the app’s raw date/time string; it may use the phone’s zone and cross midnight, so no event-local conversion or end-date inference is performed. Description preview is marked truncated when longer than400 characters; public URLs are untrusted text and never followed. No claim of independent schedule accuracy or freshness.

Only the disposable app’s public schedule/cache is downloaded. No private calendar/file picker, arbitrary schedule URLs, Add, settings, alarms, Remind me, hidden/favourite sessions, sharing, shortcuts, widgets, external links, media, accounts, location or clipboard. Notification permission is denied before launch. Detail reads require the native Remind me checkbox explicitly unchecked; no checkbox tap exists. Ambiguous/overlapping session taps fail closed. Catalog entry resets only this temporary app’s view. Maintainer signed runs and clips are not independent verification.
