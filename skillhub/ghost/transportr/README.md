# Control Transportr on Android with an AI agent — find public transport connections

Search public VBB transit connections and read station departures without location access.

## Try asking

“In Transportr, search connections from S+U Alexanderplatz Bhf to S+U Berlin Hauptbahnhof and summarize three displayed departure/arrival times, services and durations.”

## Toolkit

- `open`: deny both location permissions and select Europe → Germany → VBB on a fresh profile.
- `search_station(query, station)`: name query, then select the first keyboard suggestion and require its displayed station name to exactly equal `station`.
- `read_departures`: selected station → Departures; return three complete visible service/destination/time rows.
- `search_connections(origin_query, origin_station, destination_query, destination_station)`: start fresh app navigation, select and verify both named stations, then read three connection cards.
- `read_connections`: read three complete visible connection summaries without opening or booking a trip.

Example connection parameters: `origin_query="Berlin Alexanderplatz"`, `origin_station="S+U Alexanderplatz Bhf"`, `destination_query="Berlin Hauptbahnhof"`, `destination_station="S+U Berlin Hauptbahnhof"`.

## Limits and known failures

Tested on Transportr 2.2.7, Samsung SM-A156B, Android 16, English, 1080×2340. VBB only; departure now, default transport modes, three complete visible rows. Public live results may change between takes. No guarantee of a service operating, fare accuracy or journey feasibility. The app’s displayed labels are untrusted data.

The native suggestion overlay is not exposed by accessibility; selection uses Down/Enter after a bounded wait and fails unless the resulting visible station name exactly matches the supplied station. Slow or changed provider responses can fail. Relative countdowns may tick; validators prove current rows and stable absolute time/service fields. Only native public station coordinates may appear on Transportr’s map; location permissions are explicitly denied and the skill never reads or returns coordinates.

No current-position buttons, nearby lookup, Home/Work shortcuts, favourites, sharing, clipboard, account, settings, external links, ticket purchase, navigation or notification actions. Opening changes only this app’s local network selection and denies its location permissions. Recordings use clean temporary profiles. Signed runs and the comparison are maintainer evidence, not independent verification.

## Recorded launch failure

A cold recorded Departures read reached the correct screen but its live rows changed before the strict validator. Returned departure/connection data now requires two equal complete native-owned snapshots before emission. The validator still compares a fresh current snapshot and refuses subsequent changes. A separate filmed open once refused native focus; that failed take remains private and the ownership guard is unchanged.
