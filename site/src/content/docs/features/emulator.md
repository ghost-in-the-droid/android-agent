---
title: "🖥️ Emulator Support"
description: Docker+KVM Android emulators — create, start, stop, and scale headless instances via the dashboard or API.
---

Full Android emulator lifecycle management via Docker containers with KVM hardware acceleration. Create, start, stop, and delete emulators from the dashboard or REST API, and scale to multiple concurrent headless instances for testing.

## Architecture

### Docker+KVM backend

Ghost uses [`budtmo/docker-android`](https://github.com/budtmo/docker-android) containers instead of the Android SDK emulator. Each container runs a full Android 11 emulator, exposes ADB on port 5555, and is hardware-accelerated via KVM.

```
Ghost backend
    |
    v
Docker daemon  →  budtmo/docker-android container
    |              Android 11 (API 30)
    |              ADB server :5555
    |
    v
adb connect localhost:<host_port>
    |
    v
Device(serial)  — same API as a physical phone
```

**Why Docker instead of SDK AVDs:**
- No Android SDK required — just Docker + KVM
- Works on any Linux machine with `/dev/kvm`
- Emulators are isolated, reproducible, and easy to reset
- No SDK version management headaches

### EmulatorPool

Manages multiple containers for parallel testing:

- Thread-safe serial-to-status tracking (idle/busy)
- System resource monitoring (CPU, RAM, disk)
- Scale up: spin N containers at once
- Scale down: stop idle containers
- Job assignment via mark_busy/mark_idle

## Prerequisites

```bash
# Check
docker info          # Docker daemon running
ls /dev/kvm          # KVM available (Linux)
adb version          # ADB in PATH

# Pull the image (6.9 GB, one-time)
docker pull budtmo/docker-android:emulator_11.0

# Verify via Ghost
curl http://localhost:5055/api/emulators/prerequisites
```

The prerequisites endpoint returns:

```json
{
  "backend": "docker",
  "docker_available": true,
  "kvm_available": true,
  "adb_binary": true,
  "hw_accel": true,
  "hw_accel_type": "KVM",
  "image": "budtmo/docker-android:emulator_11.0"
}
```

## Quick Start

### Via dashboard

Open the **Emulators** tab → click **Create** → enter a name → the container starts and connects via ADB automatically.

### Via API

```bash
# Create + start
curl -X POST http://localhost:5055/api/emulators \
  -H "Content-Type: application/json" \
  -d '{"name": "test-emu", "api_level": 30}'

# Poll boot status
curl http://localhost:5055/api/emulators/test-emu/boot-status
# {"serial": "localhost:5555", "booted": true}

# Use it — same as a physical phone
curl http://localhost:5055/api/phone/devices

# Stop + delete
curl -X POST http://localhost:5055/api/emulators/test-emu/stop
curl -X DELETE http://localhost:5055/api/emulators/test-emu
```

### Manual Docker (no Ghost backend)

```yaml
# docker-compose.emulators.yml — ships with the repo
services:
  emu-1:
    image: budtmo/docker-android:emulator_11.0
    devices:
      - /dev/kvm:/dev/kvm
    ports:
      - "5555:5555"
```

```bash
docker compose -f docker-compose.emulators.yml up -d
adb connect localhost:5555
```

## Emulators = Phones

Both emulators and physical phones are ADB serials. `Device("localhost:5555")` works identically to `Device("L9AIB7603188953")`. All 38 MCP tools, all skills, all agent workflows run unchanged on emulators.

## API Reference

### Emulator Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/emulators` | List all containers with status |
| POST | `/api/emulators` | Create + start a new container |
| DELETE | `/api/emulators/<name>` | Stop + remove container |
| POST | `/api/emulators/<name>/stop` | Stop container |
| GET | `/api/emulators/<name>/boot-status` | `{serial, booted}` |
| GET | `/api/emulators/running` | Running containers reachable via ADB |
| GET | `/api/emulators/prerequisites` | Docker + KVM availability check |
| GET | `/api/emulators/system-images` | Available Docker images |
| POST | `/api/emulators/system-images/install` | Pull a Docker image |

### Pool Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/emulator-pool/status` | Active / idle / busy counts |
| GET | `/api/emulator-pool/resources` | CPU / RAM / disk usage |
| POST | `/api/emulator-pool/scale-up` | Start N containers |
| POST | `/api/emulator-pool/scale-down` | Stop idle containers |
| POST | `/api/emulator-pool/stop-all` | Stop all pool containers |

## Files

| File | Purpose |
|------|---------|
| `gitd/services/emulator_service.py` | EmulatorManager + EmulatorPool |
| `gitd/services/_emulator_helpers.py` | Docker client, discovery, config dataclass |
| `gitd/services/_emulator_pool.py` | Pool lifecycle |
| `gitd/routers/emulators.py` | REST API routes |
| `docker-compose.emulators.yml` | Manual multi-emulator compose file |

## Snapshots

Snapshots are not supported in Docker mode — containers start fresh each time. For persistent state, commit a custom Docker image from a running container:

```bash
docker commit <container_id> my-emulator-state:v1
```

## Related

- [ADB Device](/features/adb-device/) — Device class works identically with emulators
- [Scheduler](/features/scheduler/) — assign automated jobs to emulators
- [Ghost Bench](/features/benchmarks/) — run benchmark suites across emulator pools
