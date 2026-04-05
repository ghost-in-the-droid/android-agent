# Android Emulator Support — Feature Summary

## What It Does

Full emulator lifecycle management from the dashboard and API. Create, start, stop, and delete Android emulators (AVDs), run all existing features on emulators identically to physical phones, and scale to 20+ concurrent headless emulators for parallel skill generation and testing via the EmulatorPool.

## Current State

**Working:**
- EmulatorManager service — full AVD lifecycle (list, start, stop, delete, setup, snapshots)
- 21 REST API endpoints via Flask Blueprint (`/api/emulators/*`, `/api/emulator-pool/*`)
- Vue 3 + TypeScript dashboard tab (Emulators sub-tab + Pool sub-tab)
- System image discovery (scans SDK directory)
- Prerequisites check (SDK, KVM, cmdline-tools detection)
- Automatic setup for automation (disable animations, max screen timeout, stay awake)
- EmulatorPool orchestrator (scale up/down, resource monitoring, job tracking)
- Headless mode with swiftshader_indirect GPU fallback
- Cold boot option (skip snapshot, fixes ADB offline issues)
- Handles ADB "offline" state (shows as "booting" in UI)
- 5-second polling for live status updates in dashboard

**Requires cmdline-tools for:**
- Creating new AVDs (`avdmanager create avd`)
- Installing system images (`sdkmanager --install`)
- Without cmdline-tools: start/stop/list/delete still works for existing AVDs

**Not yet tested/verified:**
- Pool scale-up with create (needs cmdline-tools)
- Emulator + WebRTC streaming
- Skill Hub workflows on emulators
- Auto Skill Creator on emulators
- Scheduler job assignment to emulators

## Architecture

### Backend

```
gitd/
├── services/
│   └── emulator_service.py    # EmulatorManager + EmulatorPool (726 LoC)
└── routers/
    └── emulators.py           # Flask Blueprint, 21 routes (282 LoC)
```

**EmulatorManager** wraps Android SDK tools:
- `EMULATOR_BIN` → `~/Android/Sdk/emulator/emulator`
- `ADB_BIN` → system `adb` or SDK's `platform-tools/adb`
- `AVDMANAGER` / `SDKMANAGER` → `~/Android/Sdk/cmdline-tools/latest/bin/`
- AVD configs read from `~/.android/avd/*.ini` + `*.avd/config.ini`

**EmulatorPool** manages parallel emulators:
- Thread-safe serial→status tracking (idle/busy)
- System resource monitoring via psutil (CPU, RAM, disk)
- Scale up creates + starts N headless emulators
- Scale down stops idle emulators
- Job assignment via mark_busy/mark_idle

**Singletons:** `get_manager()` and `get_pool()` — lazy-initialized, shared across the Flask app.

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/emulators` | GET | List all AVDs (with running status) |
| `/api/emulators` | POST | Create new AVD |
| `/api/emulators/<name>` | DELETE | Delete AVD |
| `/api/emulators/<name>/start` | POST | Start emulator (headless, gpu, cold_boot) |
| `/api/emulators/<name>/stop` | POST | Stop emulator |
| `/api/emulators/<name>/boot-status` | GET | Check boot progress |
| `/api/emulators/<name>/setup` | POST | Run automation setup |
| `/api/emulators/<name>/install-apk` | POST | Install APK |
| `/api/emulators/<name>/snapshot/save` | POST | Save snapshot |
| `/api/emulators/<name>/snapshot/load` | POST | Load snapshot |
| `/api/emulators/<name>/snapshots` | GET | List snapshots |
| `/api/emulators/running` | GET | List running emulators |
| `/api/emulators/prerequisites` | GET | Check SDK availability |
| `/api/emulators/stop-by-serial` | POST | Stop by serial |
| `/api/emulators/system-images` | GET | List installed images |
| `/api/emulators/system-images/install` | POST | Download new image |
| `/api/emulator-pool/status` | GET | Pool status + resources |
| `/api/emulator-pool/scale-up` | POST | Start N emulators |
| `/api/emulator-pool/scale-down` | POST | Stop idle emulators |
| `/api/emulator-pool/stop-all` | POST | Stop all pool emulators |
| `/api/emulator-pool/resources` | GET | CPU/RAM/disk usage |

### Frontend

```
frontend/src/
├── stores/emulators.ts                        # Pinia store (238 LoC)
└── components/emulator/
    ├── EmulatorTab.vue                        # Main tab container (226 LoC)
    ├── EmulatorList.vue                       # AVD table with actions (116 LoC)
    ├── CreateEmulatorForm.vue                 # Expandable creation form (172 LoC)
    └── EmulatorPoolPanel.vue                  # Pool management + resource bars (144 LoC)
```

**Dashboard tab** (Emulators) has two sub-tabs:
- **Emulators** — AVD list with start/stop/setup/delete, creation form, system image selector
- **Pool** — active/idle/busy counts, resource usage bars (RAM/CPU/disk), scale up/down controls

## Key Design Decisions

1. **Emulators = phones** — both are ADB serials. `Device(serial)` works unchanged. `is_emulator(serial)` checks `emulator-` prefix when emulator-specific behavior is needed.
2. **Flask Blueprint** — zero coupling to server.py (4-line registration). Can be moved to FastAPI router later.
3. **Async boot** — `start()` returns immediately with `status: 'booting'`. Boot + setup runs in a daemon thread. Dashboard polls for status.
4. **Graceful degradation** — works without cmdline-tools (can't create, but can start/stop/list existing AVDs). Shows warning in UI.
5. **Headless defaults** — headless mode automatically uses `swiftshader_indirect` GPU (host GPU needs a display).
6. **Cold boot option** — skips snapshot loading to fix ADB offline issues with newer API levels.

## Prerequisites

```bash
# Required (already present)
~/Android/Sdk/emulator/emulator    # Emulator binary
adb                                 # ADB in PATH
/dev/kvm                           # KVM acceleration

# Optional (for creating new AVDs)
sdkmanager --install "cmdline-tools;latest"

# Install a system image
sdkmanager --install "system-images;android-35;google_apis_playstore;x86_64"
```

## Test

```bash
# API test (server must be running)
curl -s http://localhost:5055/api/emulators | python3 -m json.tool
curl -s http://localhost:5055/api/emulators/prerequisites | python3 -m json.tool
curl -s http://localhost:5055/api/emulator-pool/resources | python3 -m json.tool

# Start emulator
curl -X POST http://localhost:5055/api/emulators/Medium_Phone_API_36.1/start \
  -H "Content-Type: application/json" \
  -d '{"headless": true, "cold_boot": true}'

# Dashboard: open http://localhost:5173 → 🖥️ Emulators tab
```
