# Control Android Settings — adaptation notes

Package: `com.android.settings`. Scope: Android 16 Samsung, en-US. Never adapt these actions by opening About phone, Wi-Fi lists, or storage app inventories: these pages can reveal personal identifiers even if a later parser drops those fields.

- `get_device_info`: read exactly `ro.product.model`, `ro.build.version.release`, `ro.build.display.id`; return `device_info.model`, `android_version`, `build_number`. Never enumerate all properties.
- `get_battery_status`: filter native `dumpsys battery` on the device to numeric `level`, `scale`, `status`. Return `battery.level_percent` and `charging`; reject missing/unknown status or impossible levels.
- `get_storage_usage`: filter `df -k /data` on the device to total/used/available numbers. Return `storage.total_kib`, `used_kib`, `free_kib`; never enumerate app directories or other volumes.
- `get_wifi_status`: filter native `cmd wifi status` on the device into `wifi.enabled` and `connected` booleans. COMPLETED means associated; explicit inactive/disconnected/transitional states mean not connected. A disabled radio is disconnected. Missing/conflicting enabled or connected state is an error. Never return raw command output or network identifiers, and never open Internet settings as fallback.
- `set_dark_theme(enabled)`: close Settings, go Home, open `android.settings.DISPLAY_SETTINGS`, wait for visible `Display`. Query `cmd uimode night`; only explicit yes/no can be changed. Set the requested fixed mode and read it back. Auto/custom/unreadable states fail without changing the schedule. Success requires the returned mode and independent native readback to match. Restore the original mode when making a temporary demonstration.

The four reads need no Settings UI landmark. End validators require exactly the allowed result keys, valid types/ranges and internally consistent aggregates. Do not weaken missing native state into success or reintroduce private UI paths for compatibility.
