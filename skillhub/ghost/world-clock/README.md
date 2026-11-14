# Control Zham on Android with an AI agent — compare world time zones

Compare named cities and time zones offline without location permission, accounts or alarms.

Try asking: "In Zham, add Europe/Berlin and list the visible cities with their IANA time zones and current times. Use only the city clocks; do not change settings or use alarms."

## Toolkit

| Action | Result |
|---|---|
| open | Cold-open the live city clock list |
| read_clocks | Complete visible cities, IANA zone identifiers and displayed times |
| add_city(zone) | Filter exact Area/City identifier, select it and verify the visible new row |
| open_converter | Open the app's current selected-instant comparison snapshot |
| read_conversion | Reference city/date and visible city times at that selected instant |
| reset_now | Reset the app comparison snapshot to the current instant |
| back_to_clocks | Return from conversion to the live clocks |

## Limits

Tested on offline Zham 1.1.2, Samsung SM-A156B, Android 16, 1080×2340 at 450 dpi, English. No OS clock, alarms, timers, location, accounts, widgets, settings, deletion, reorder or arbitrary-date/time editing. Only complete visible city rows are returned; the tested six-city layout includes Berlin plus the five app defaults. Adding many cities can exceed the visible capacity and fails rather than inventing hidden rows. Conversion is an app snapshot, not necessarily the current time until reset_now. Its date belongs to the reference city; other cities can be on different dates, which this version does not expose. Public city selection is local app state, not a device-location reading. Maintainer self-runs are not independent verification.

## Known failure modes

Unknown or unsupported IANA zone, changed native controls, partial rows, missing reference date, a foreign focused window or stale clock values fails closed. Portal snapshots avoid idle waits on live seconds; native focused-window package/owner is checked both before and after every tree read. This retains native ownership proof even though Portal's XML omits package attributes. Live returned clock times are checked against the phone's own UTC epoch with IANA zone rules and a 20-second read tolerance, including midnight rollover. Converter snapshots are compared exactly against a fresh app read. No system clock setting is written.
