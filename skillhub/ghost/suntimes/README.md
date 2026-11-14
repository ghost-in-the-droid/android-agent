# Control Suntimes on Android with an AI agent — read sunrise and moon times

Read the native sun/moon table for Berlin or Hamburg without requesting the phone’s location.

## Try asking

“In Suntimes, show today’s sun and moon table for Berlin. Copy the date and time zone, actual sunrise and sunset, day length and moon phase. Briefly compare the daylight and night lengths. Do not use GPS, alarms, maps or widgets.”

## Toolkit

| Action | Purpose |
| --- | --- |
| `open` | Complete fresh onboarding, import bundled European places and select Berlin. Existing supported city/date is preserved. |
| `read_sun_moon` | Read exposed table values, including moonrise/moonset when present. |
| `search_city(city)` | Open the native Places picker and filter the bundled database. |
| `select_city(city)` | Select the exact previously searched Berlin/Hamburg row and confirm User Defined mode. |
| `next_day` | Tap the date once and prove it advanced by exactly one day. |

## Limits and known failures

Tested on Suntimes 0.17.5, Samsung SM-A156B, Android 16, English, 1080×2340. Scope is the bundled Berlin/Hamburg entries with displayed Europe/Berlin zone. Other places, arbitrary coordinates, dates in a picker and zone changes are outside this toolkit. `open` initializes a fresh temporary profile to Berlin; use search then select to switch to Hamburg. A missing moonrise/moonset is returned as absent, never invented. Dates/times and calculation warnings are copied from the app, not independently checked astronomical predictions. Native date and hierarchy checks add latency. Public city coordinates can appear in the native header/picker, but the toolkit omits them from returned data.

Before launch, notification and fine/coarse location runtime permissions are denied for this temporary app. Fine/coarse location app-ops must remain ignored for every action. No GPS/current/last-known location, map, alarm, timer, bedtime, notification-policy/DND access, battery exemption, widgets, imports from user files, export/share, settings or external links. Onboarding’s built-in European city import writes only this disposable app’s place database. No alarms are created and no system time-zone setting is changed. Native selected-city/mode/table checks fail closed. Maintainer signed runs and clips are not independent verification.
