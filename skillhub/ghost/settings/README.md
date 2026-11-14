# Control Settings on Android with an AI agent

Settings 1.1.0 reads native aggregates and can change the system theme. It requires no account.

| Action | Result | Parameters |
|---|---|---|
| `get_device_info` | Model, Android version, build number | none |
| `get_battery_status` | Battery level percent, charging boolean | none |
| `get_storage_usage` | Total, used and free `/data` storage, in KiB | none |
| `get_wifi_status` | Enabled and connected booleans | none |
| `set_dark_theme` | Requested theme and native state readback | `enabled` boolean |

## Behavior change in 1.1.0

The four read actions now use privacy-bounded native aggregates by default. The previous About-phone, battery, storage-category and Wi-Fi-list UI paths have been removed entirely; there is no flag to restore them. These actions neither open those pages nor read their accessibility trees. Device names, serials, IMEI, phone numbers, SSID/BSSID, IP addresses, nearby networks and per-app/category storage lists are excluded. Consumers must use the result fields above instead of the removed fields.

Device information uses only `ro.product.model`, `ro.build.version.release` and `ro.build.display.id`. Battery uses filtered `dumpsys battery`; storage uses numeric `df -k /data` totals. Wi-Fi filters `cmd wifi status` on the device before ADB returns output, exposing only booleans. Unsupported or incomplete native output fails explicitly rather than inventing a value. Charging means the platform reports actively charging; a full battery is not actively charging. Storage covers the data filesystem, rather than an advertised device capacity or a per-volume inventory.

The theme action opens Display, applies `cmd uimode night yes/no` and reads it back. Automatic, custom and unreadable night-mode states are refused before any change, preserving existing schedules. A temporary caller should restore the original fixed theme afterward. Settings data is never cleared.

## Use

```bash
ghost skill run ghost/settings get_battery_status --device YOUR_DEVICE
ghost skill run ghost/settings set_dark_theme --param enabled=true --device YOUR_DEVICE
```

## Verification scope and limits

The current scope is Android 16 on Samsung SM-A156B, 1080×2340, 450 dpi, en-US. Other OS/OEM combinations need live verification. The read actions depend on the documented native output formats and shell permission; unknown Wi-Fi state fails closed. Theme navigation still depends on the English Display heading.

Current signed artifacts in `runs/` are maintainer self-runs made with the canonical local signing key using actual `ghost skill run --record`, after final file edits. They are not independent verification. Historical artifacts that no longer match the files have been removed. This version requires three successful runs per action before claiming Runs tier.

License: MIT.
