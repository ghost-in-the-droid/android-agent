# Opt-in run telemetry

Telemetry defaults to off. `ghost telemetry on` enables it and rotates a random UUIDv4 installation ID. `ghost telemetry off` disables it and removes that ID. `ghost telemetry status` reports the effective preference. `DO_NOT_TRACK=1` overrides consent. Only `ghost skill run --record` sends an event, after writing local signed evidence, and only with both consent and `GHOST_TELEMETRY_ENDPOINT` configured. Live tests and verification do not send events.

`GHOST_TELEMETRY_DEBUG=1` prints the event instead of sending. The endpoint must use HTTPS; HTTP is accepted only for local tests on 127.0.0.1. Redirects are disabled. Delivery has a two-second timeout, no retry, and cannot fail a completed run. No endpoint is bundled or enabled by default.

The public payload field list is exhaustive:

| Field | Accepted values |
| --- | --- |
| schema_version | Integer 1 |
| skill | A skill ID in the worker's reviewed TELEMETRY_CATALOG |
| app_version | A concrete version enumerated for that skill in TELEMETRY_CATALOG |
| outcome | passed, failed |
| os | android, ios |
| backend | device, fake |
| install_id | Canonical lowercase UUIDv4, random and rotatable |

Skill and app version are catalog enums, not arbitrary strings. The UUID is the only constrained identifier rather than a category. No action names, parameters, results, error messages, hardware strings, XML, screenshots, serials, login names, addresses, or client timestamps are sent. Unknown keys and values, including IP strings, are rejected. The worker adds a UTC receipt timestamp and retains no request headers or IP addresses in application storage. Network infrastructure necessarily receives a source IP; deployment owners must separately disable infrastructure request logging rather than claim the network never sees it.

The staged Cloudflare Worker in `infra/telemetry-worker/` requires an R2 EVENTS binding and TELEMETRY_CATALOG JSON mapping skill IDs to allowed concrete app versions. Its default empty catalog rejects all events. Replace the placeholder bucket and commented route only for an authorized deployment. No deployment or login was performed. Run the offline worker tests with `node infra/telemetry-worker/test.mjs`.

R2 has no atomic append operation. Each accepted event is a unique immutable `events/YYYY-MM-DD/<random-uuid>.jsonl` object containing one JSON line. This is a logical append-only log, avoiding shared-object overwrite races. Export those object bodies locally and concatenate them for aggregation. Installation IDs never appear in object names.

Run `python3 tools/aggregate_telemetry.py events.jsonl --catalog catalog.json` to produce a mapping from skill IDs to `{passed,total,passed_90d,total_90d}`, suitable as each registry entry's `quality.runs` input. Invalid rows fail the batch with their line number. Fake-device events are excluded from public reliability counts. The output omits installation IDs. It does not authenticate self-reported events, deduplicate runs, or automatically modify the registry. Keep app-version partitions when presenting reliability, and publish rates only at 20 or more runs. Aggregation can be run on a version-filtered export to preserve those partitions.

Telemetry feeds the displayed reliability figures only. It never contributes quality points or tier changes; those come solely from signed `runs/` and `verifications/` artifacts (see `skillhub/scoring/v1.json`).
