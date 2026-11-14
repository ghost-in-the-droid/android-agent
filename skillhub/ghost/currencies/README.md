# Control Currencies on Android with an AI agent — convert currencies

Read displayed currency conversions with their rate date and provider, without accounts or payments.

Try asking: "In Currencies, convert 125.50 GBP to JPY. Report the displayed result, rate, and rate date/provider. Do not change data providers or use arithmetic operators."

## Toolkit

| Action | Result |
|---|---|
| open | Cold-open the conversion keypad and read its current rate metadata |
| select_source(currency) | Filter the native picker by exact ISO code and verify the selected source |
| select_target(currency) | Select and verify the exact target code |
| set_amount(amount) | Long-delete the old input, enter a plain decimal using native numeric keys, verify readback |
| swap | Reverse both selected currency codes and read the conversion |
| read_state | Source, target, input/output amounts, displayed rate, date and provider |

## Limits

Tested on Currencies 1.23.0, Samsung SM-A156B, Android 16, 1080×2340 at 450 dpi, English. Conversion mode only: no payments, accounts, arithmetic operators, history, date changes, data-provider settings, fees or financial advice. Currency availability depends on the app's current provider. Rates can be cached or rounded; the toolkit copies displayed values and the literal date/provider and never claims a live market rate or executable transaction quote. Inputs are nonnegative plain decimals with at most nine integer digits and two decimal places. English numeric formatting and prefix currency symbols only. Maintainer self-runs are not independent verification.

## Known failure modes

A missing currency, unknown dialog, stale/unavailable rate metadata, calculator expression, unsupported numeric formatting or foreign focused window fails closed. A picker result must have the exact requested ISO code, and selection is read back from the main screen. Long-delete must demonstrably clear to zero before any new numeric keys are entered. Keypad bounds are native controls captured on the pinned phone; each tap independently checks foreground ownership. Complete native hierarchy reads preserve package ownership and add replay latency. The resulting conversion and metadata must equal a fresh native read.
