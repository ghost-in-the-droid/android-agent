---
title: "🖥️ Emulator Support"
description: EmulatorManager for AVD lifecycle, EmulatorPool for parallel headless emulators, and 21 REST API endpoints.
---

Full emulator lifecycle management from the dashboard and API. Create, start, stop, and delete Android emulators (AVDs), and scale to 20+ concurrent headless instances via the EmulatorPool.

## Architecture

### EmulatorManager

Wraps Android SDK tools for single-emulator lifecycle:

```
~/Android/Sdk/emulator/emulator       # Emulator binary
~/Android/Sdk/cmdline-tools/latest/    # avdmanager, sdkmanager
~/.android/avd/                        # AVD configs
```

Operations: list, start, stop, delete, setup (disable animations, max timeout, stay awake), install APK, save/load snapshots.

### EmulatorPool

Manages parallel headless emulators for testing and skill generation:

- Thread-safe serial-to-status tracking (idle/busy)
- System resource monitoring via psutil (CPU, RAM, disk)
- Scale up: create + start N headless emulators
- Scale down: stop idle emulators
- Job assignment via mark_busy/mark_idle

Both are lazy-initialized singletons accessed via `get_manager()` and `get_pool()`.

## Key Design: Emulators = Phones

Both emulators and physical phones are ADB serials. `Device(serial)` works unchanged. The function `is_emulator(serial)` checks the `emulator-` prefix when emulator-specific behavior is needed.

## Prerequisites

```bash
# Required
~/Android/Sdk/emulator/emulator    # Emulator binary
adb                                 # In PATH
/dev/kvm                           # KVM acceleration (Linux)

# Optional (for creating new AVDs)
sdkmanager --install "cmdline-tools;latest"

# Install a system image
sdkmanager --install "system-images;android-35;google_apis_playstore;x86_64"
```

Without `cmdline-tools`, you can still start/stop/list/delete existing AVDs but cannot create new ones.

## API Endpoints (21 routes)

### Emulator Management

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/emulators` | List all AVDs with running status |
| POST | `/api/emulators` | Create new AVD |
| DELETE | `/api/emulators/<name>` | Delete AVD |
| POST | `/api/emulators/<name>/start` | Start (headless, gpu, cold_boot options) |
| POST | `/api/emulators/<name>/stop` | Stop emulator |
| GET | `/api/emulators/<name>/boot-status` | Check boot progress |
| POST | `/api/emulators/<name>/setup` | Run automation setup |
| POST | `/api/emulators/<name>/install-apk` | Install APK |
| POST | `/api/emulators/<name>/snapshot/save` | Save snapshot |
| POST | `/api/emulators/<name>/snapshot/load` | Load snapshot |
| GET | `/api/emulators/<name>/snapshots` | List snapshots |
| GET | `/api/emulators/running` | List running emulators |
| GET | `/api/emulators/prerequisites` | Check SDK availability |
| POST | `/api/emulators/stop-by-serial` | Stop by serial |
| GET | `/api/emulators/system-images` | List installed images |
| POST | `/api/emulators/system-images/install` | Download new image |

### Pool Management

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/emulator-pool/status` | Pool status + resources |
| POST | `/api/emulator-pool/scale-up` | Start N emulators |
| POST | `/api/emulator-pool/scale-down` | Stop idle emulators |
| POST | `/api/emulator-pool/stop-all` | Stop all pool emulators |
| GET | `/api/emulator-pool/resources` | CPU/RAM/disk usage |

## Usage

### Start an Emulator

```bash
curl -X POST http://localhost:5055/api/emulators/Medium_Phone_API_36.1/start \
  -H "Content-Type: application/json" \
  -d '{"headless": true, "cold_boot": true}'
```

### Automation Setup

After starting, run setup to configure the emulator for automation:

```bash
curl -X POST http://localhost:5055/api/emulators/Medium_Phone_API_36.1/setup
```

This disables animations, sets maximum screen timeout, and enables stay-awake mode.

### Pool Scale-Up

```bash
# Start 3 headless emulators
curl -X POST http://localhost:5055/api/emulator-pool/scale-up \
  -H "Content-Type: application/json" \
  -d '{"count": 3}'

# Check resource usage
curl -s http://localhost:5055/api/emulator-pool/resources | python3 -m json.tool
```

## Dashboard

The **Emulators** tab has two sub-tabs:

- **Emulators** -- AVD list with start/stop/setup/delete buttons, creation form, system image selector
- **Pool** -- active/idle/busy counts, resource usage bars (RAM/CPU/disk), scale up/down controls

## Headless Mode

When starting headless (no display required), the emulator uses `swiftshader_indirect` GPU rendering automatically. Cold boot skips snapshot loading to avoid ADB offline issues.

```bash
# Async boot: returns immediately, boot runs in background
# Poll boot-status for progress
curl -s http://localhost:5055/api/emulators/Medium_Phone_API_36.1/boot-status
```

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `gitd/services/emulator_service.py` | 726 | EmulatorManager + EmulatorPool |
| `gitd/routers/emulators.py` | 282 | Flask Blueprint, 21 routes |

The Flask Blueprint is zero-coupled to `server.py` (4-line registration).

## Related

- [Phone Farm](/guides/phone-farm/) -- using emulators alongside physical phones
- [ADB Device](/features/adb-device/) -- Device class works identically with emulators
- [Scheduler](/features/scheduler/) -- assign jobs to emulators
