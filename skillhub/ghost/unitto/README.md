# Control Unitto on Android with an AI agent — convert length units

Convert physical lengths in Unitto, read the displayed result, choose units, swap them, enter a value or clear it. Offline; no currency or personal tools.

Try asking: **Convert 26.2 miles to kilometers in Unitto and report the displayed result.**

## Toolkit

| Action | Use |
|---|---|
| open_converter | Open the offline Unitto length converter |
| set_units | Select the source and target length units |
| set_value | Enter a nonnegative decimal and read the displayed result |
| read_state | Read current units and input/output displays |
| swap_units | Swap the current source and target length units |
| clear_value | Clear both converter values to zero |
| convert_length | Open, set both length units and convert a value |

## Tested scope

Samsung SM-A156B Android 16, English. Package com.sadellie.unitto, app *. Official F-Droid signed-index SHA and APK signatures checked outside the repository. Maintainer-signed self-runs bind recorded outcomes to these files; they are not independent verification.

## Known failure modes

During a clean launch recording, unit selection failed because a stale accessibility hierarchy exposed the previous screen. Reads now use native dumps filtered to Unitto's package, and selection waits for the requested unit on the correct side before proceeding. If that state never appears, the action fails instead of reporting a conversion.

A filmed agent tried lowercase names and symbols (`mile`, `mi`, `km`), which the helper does not accept. Parameters now expose the existing canonical names as enums so callers can discover the exact choices; unsupported spelling is rejected before UI input.

Tested Unitto Titanium yellow, version code 76. Its versionName is nonnumeric: the manifest fingerprint uses app_version *, while the entry helper explicitly rejects any versionCode other than 76. English length units only: Millimeter, Centimeter, Meter, Kilometer, Inch, Yard, Mile. Nonnegative plain decimal input only; no expressions, currency, mass, temperature, feet (Unitto uses a composite feet-and-inches editor), dates, time zones or body metrics. The output is the UI value rounded to three decimal places, checked against exact SI length definitions within half the last displayed decimal. Missing/foreign UI or unreadable decimals fail loudly. Local self-runs are not independently verified.
