# Control Thermocouples on Android with an AI agent

Copy the app's offline reference data for thermocouple types, including positive/negative metals and temperature ranges.

Try asking: **Use device phone-b-demo. In Thermocouples, read Type K then Type E. For each, copy the positive metal, negative metal and temperature range in Celsius, then compare their displayed maximum temperatures. Stay in Details; do not use Search, Conversions, Info or external links.**

## Toolkit

| Action | Role | Parameters | Returned data | Side effects |
| --- | --- | --- | --- | --- |
| open | Entry | none | Default type's native reference record | Opens/reset activity |
| select_type | Primitive | type: B/E/J/K/N | Selected type, both metals and printed range | Reference tab only |
| list_types | Primitive | none | Fully exposed supported tabs/current type | None |
| compare_types | Primitive | left/right: two distinct supported types | Two independently read native records | Leaves right type selected |
| read_details | Read state | none | Type, positive metal, negative metal, printed Celsius range and bounds | None; opens only from HOME |

## Limits

Only five fully exposed type tabs are supported; horizontal scrolling and other types are outside this version. Colours are images, so no wire-colour claims are returned. Search, Conversions and Info are excluded. This copies the installed app's reference table; it does not identify an unknown sensor, configure hardware or independently verify standards. The compare action returns records without inventing recommendations. No accounts, network calls, sensors or user files.

## Known failure modes

Foreign foreground, missing Details ownership, an unexposed type, duplicate/missing native fields, malformed/inverted temperature range, same-type comparison or failed title readback stops the action. No blind BACK, approximate selection or fallback values. read_details preserves a current Details tab; open resets the activity. All evidence is maintainer-run, not independent verification.

## Tested scope

Thermocouples4.0.3, English UI, Samsung SM-A156B, Android16,1080x2340,450dpi. Three clean-profile cycles per action after final files, default official signing identity.
