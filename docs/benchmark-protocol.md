# AndroidWorld benchmark records

Ghost's replay benchmark runs a declared task and seed through an AndroidWorld
bridge, then records the skill result separately from the evaluator's result.
The bridge owns initialization, evaluation and teardown. Deterministic replay
uses no model calls; before/with-skill agent arms do consume model tokens.

A benchmark card is a summary, not proof of independent verification. Read the
per-episode outcome, model, seed, timing, token counts, task and run identifiers;
keep failures, capped episodes and void results labelled. Historical paired
comparisons use the same declared tasks and seeds across arms. A model-free replay
success and an agent success are different observations.

The current CLI implementation is `gitd/skills/engine/bench.py`; the bridge protocol
is implemented in `tools/bench/aw_bridge.py`. Registry scoring is defined by
`skillhub/scoring/v1.json` and `tools/build_registry.py`. Signed evidence acceptance
also requires the current version/content digest, permitted identity and valid
signature. Do not infer scoring rules from the presence of a benchmark card alone.

Historical signed artifacts can retain references to private capture logs or an
internal protocol version. Those provenance strings are not public download
links. Original artifacts remain unchanged so their signatures can be verified.
New benchmark summaries point here for the public explanation; task lists and
historical measurement contracts remain versioned with their original records.

Demo clips are presentation material rather than independent evidence. The public
`skillhub/demo-catalog.json` marks capture specifications unavailable when they are
internal-only, rather than advertising a path removed by public-release stripping.
