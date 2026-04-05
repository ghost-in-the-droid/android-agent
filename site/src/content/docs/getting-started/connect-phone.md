---
title: "📱 Connect Your Phone"
description: Enable developer options, USB debugging, authorize ADB, and troubleshoot common connection issues.
---

Before Ghost in the Droid can automate your phone, you need to enable USB debugging and authorize your computer. This takes about 2 minutes.

## Step 1: Enable Developer Options

1. Open **Settings** on your Android phone
2. Scroll to **About Phone** (on Samsung: Settings > About Phone > Software Information)
3. Tap **Build Number** 7 times rapidly
4. You should see a toast message: "You are now a developer!"
5. Go back to **Settings** -- a new **Developer Options** menu should appear

## Step 2: Enable USB Debugging

1. Open **Settings > Developer Options**
2. Toggle **USB Debugging** to ON
3. Confirm any security prompts

## Step 3: Connect and Authorize

Plug your phone into your computer with a **data-capable USB cable** (not a charge-only cable).

```bash
adb devices
```

Expected output:

```
List of devices attached
YOUR_DEVICE_SERIAL    device
```

If you see `unauthorized` instead of `device`, check your phone screen -- there should be a popup asking **"Allow USB debugging?"**. Tap **Allow** and check **"Always allow from this computer"**.

## Step 4: Verify the Connection

```bash
# Check screen resolution
adb shell wm size
# Physical size: 1080x2340

# Verify UI hierarchy is readable
adb shell uiautomator dump /sdcard/tt.xml && adb exec-out cat /sdcard/tt.xml | head -c 200
# Should output XML content starting with <?xml

# Quick Python test
python3 -c "
from gitd.bots.common.adb import Device
dev = Device()
print('Connected to:', dev.serial)
xml = dev.dump_xml()
print(f'Screen has {len(dev.nodes(xml))} UI elements')
"
```

## Multiple Devices

If you have more than one phone connected, specify which device to use:

```bash
# List all connected devices
adb devices
# YOUR_DEVICE_SERIAL    device
# YOUR_DEVICE_SERIAL_2       device

# Target a specific device
export DEVICE=YOUR_DEVICE_SERIAL

# Or pass per-command
DEVICE=YOUR_DEVICE_SERIAL_2 python3 run.py
```

Without the `DEVICE` variable, ADB commands will fail with "more than one device/emulator" errors.

## Troubleshooting

### "no devices/emulators found"

1. **Check the USB cable.** Charge-only cables do not support data transfer. Try a different cable.
2. **Check USB mode.** Some phones default to "Charging only" -- change to "File transfer" (MTP) in the USB notification.
3. **Restart ADB:**
   ```bash
   adb kill-server && adb start-server && adb devices
   ```
4. **Try a different USB port.** Avoid USB hubs during initial setup.
5. **Linux udev rules.** You may need to add your user to the `plugdev` group:
   ```bash
   sudo usermod -aG plugdev $USER
   # Log out and back in
   ```

### "unauthorized"

Your phone is showing a USB debugging authorization prompt that you haven't accepted yet.

1. Check the phone screen for the popup
2. Tap **Allow**
3. Check **Always allow from this computer** to avoid this in the future
4. Run `adb devices` again

### "device offline"

```bash
adb kill-server && adb start-server
```

If still offline, unplug and replug the USB cable. Some phones need USB mode explicitly set to "File transfer".

### "uiautomator dump failed"

UIAutomator can fail when:

- **Screen is locked** -- wake it first: `adb shell input keyevent KEYCODE_WAKEUP`
- **App uses custom rendering** (Flutter, games) -- UIAutomator cannot see custom-drawn elements
- **Another UIAutomator instance is running** -- only one can run at a time
- **System under load** -- wait 2 seconds and retry

### Samsung-Specific Notes

Samsung phones return `<node ...>...</node>` instead of self-closing `<node ... />` tags. The Device class parser handles this automatically. If you see XML parsing errors on Samsung devices, ensure you are using the latest version of `adb.py`.

## Verified Devices

| Device | Serial | Screen | Status |
|--------|--------|--------|--------|
| Your Phone | YOUR_DEVICE_SERIAL | varies | Get serial from `adb devices` |

The system works with any Android 5.0+ device that supports USB debugging. Higher-end devices perform better due to faster XML dump times.

## Next Steps

- [Hello World](/getting-started/hello-world/) -- run your first automation
- [Phone Farm Guide](/guides/phone-farm/) -- set up multiple devices
