# Control NZ Tides on Android with an AI agent — read tide times

Browse bundled port tables without GPS, network access or changing the phone’s time zone.

## Try asking

“In NZ Tides, show Auckland’s first three listed tide events with height, high/low, date, time and the printed time zone. Briefly compare their heights. Do not use location or change settings.”

## Toolkit

| Action | Purpose |
| --- | --- |
| `open` | Launch the app and read its default Auckland table. Existing foreground table is preserved. |
| `read_tides` | No parameters. Read the native estimate and first three listed events. From Samsung HOME, safely open default Auckland first; other foreign apps are refused. |
| `open_ports` | Open Choose Port and return exposed bundled names. |
| `scroll_ports(direction)` | Move through the open picker; use returned names to choose. |
| `select_port(port)` | Tap an exact visible bundled name, then prove the new table belongs to it. |

Start with `open` or call parameter-free `read_tides` from Samsung HOME for default Auckland. To choose another port, use `open_ports`, optionally `scroll_ports`, then `select_port(port)`. Do not pass a port to `read_tides`.

## Behavior change in 1.1.0

The first filmed AFTER used an unsupported port parameter, then called read from HOME and fell back to launching by hand. It is retained privately as an honest failed skill-assisted take. `read_tides` now deliberately supports cold reads only from the proven Samsung HOME; it still fails on any other foreign foreground app. All actions are re-recorded after this change.

## Limits and known failures

Tested on NZ Tides 25, Samsung SM-A156B, Android 16, English, 1080×2340. Canonical city switch: Auckland to Gisborne. Bundled Auckland data covers 2024-12-31 through 2027-12-31. Tables expire: the first listed event must be in the past and the second in the future at read time, otherwise the action fails. No stale or missing data is invented. The native text widget exposes rows beyond the viewport; only its first three complete event rows are returned. The ASCII chart is not interpreted.

The app prints this phone’s zone (tested GMT+01:00), which is not Auckland local time. Every event preserves its explicit printed offset, date and high/low label; no time-zone conversion or system zone change is performed. The current height/rate are the app’s interpolated estimates at refresh, not a continuously refreshed measurement. App metadata says tables derive from LINZ predictions and transcription errors are possible; these copied values are not independently verified and are not for navigation or situations where life or property is at risk.

The APK declares neither location nor network permission. No GPS, current position, accounts, settings, external links, files, downloads, alarms, widgets or posting. `select_port` requires an exact currently visible bundled row. Cancel/About/menu labels cannot be selected as ports. Foreground ownership and table identity fail closed. Signed runs and comparison clips are maintainer evidence, not independent verification.
