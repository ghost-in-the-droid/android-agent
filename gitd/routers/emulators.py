"""
Emulator management API — FastAPI Router.

All emulator lifecycle operations: list, create, delete, start, stop,
setup, install APK, snapshots, system images, pool management.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gitd.services.emulator_service import (
    EmulatorConfig,
    get_manager,
    get_pool,
)

router = APIRouter(prefix="/api/emulators", tags=["emulators"])
pool_router = APIRouter(prefix="/api/emulator-pool", tags=["emulators"])


# ── Request models ──────────────────────────────────────────────────────────


class CreateAVDRequest(BaseModel):
    name: str
    api_level: int = 35
    target: str = "google_apis_playstore"
    arch: str = ""
    device_profile: str = "medium_phone"
    ram_mb: int = 2048
    disk_mb: int = 6144
    resolution: str = "1080x2400"
    dpi: int = 420
    gpu: str = "auto"
    cores: int = 2
    headless: bool = False
    snapshot: bool = True


class StartRequest(BaseModel):
    headless: bool = False
    gpu: str = "auto"
    cold_boot: bool = False
    extra_args: Optional[list[str]] = None


class StopBySerialRequest(BaseModel):
    serial: str


class ApkRequest(BaseModel):
    apk_path: str


class SnapshotRequest(BaseModel):
    snapshot_name: str = "automation_ready"


class ImageInstallRequest(BaseModel):
    api_level: int
    target: str = "google_apis_playstore"
    arch: str = ""


class PoolScaleUpRequest(BaseModel):
    count: int = 1
    config: Optional[dict] = None


class PoolScaleDownRequest(BaseModel):
    count: Optional[int] = None


# ── Helpers ─────────────────────────────────────────────────────────────────


def _find_running_serial(name: str) -> str:
    """Find the serial for a running emulator by AVD name. Raises 404 if not running."""
    mgr = get_manager()
    for info in mgr.list_running():
        if info["name"] == name:
            return info["serial"]
    raise HTTPException(status_code=404, detail=f'Emulator "{name}" is not running')


# ── Prerequisites ───────────────────────────────────────────────────────────


@router.get("/prerequisites", summary="Check SDK Prerequisites")
def prerequisites():
    """Check SDK tool availability and hardware acceleration."""
    mgr = get_manager()
    return mgr.check_prerequisites()


# ── AVD CRUD ────────────────────────────────────────────────────────────────


@router.get("", summary="List All AVDs")
def list_avds():
    """List all AVDs with running status annotation."""
    mgr = get_manager()
    return mgr.list_avds()


@router.post("", summary="Create AVD", status_code=201)
def create_avd(req: CreateAVDRequest):
    """Create a new Android Virtual Device."""
    config = EmulatorConfig(
        name=req.name,
        api_level=req.api_level,
        target=req.target,
        arch=req.arch,
        device_profile=req.device_profile,
        ram_mb=req.ram_mb,
        disk_mb=req.disk_mb,
        resolution=req.resolution,
        dpi=req.dpi,
        gpu=req.gpu,
        cores=req.cores,
        headless=req.headless,
        snapshot=req.snapshot,
    )
    mgr = get_manager()
    result = mgr.create(config)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Create failed"))
    return result


@router.delete("/{name}", summary="Delete AVD")
def delete_avd(name: str):
    """Delete an AVD and all its data."""
    mgr = get_manager()
    result = mgr.delete(name)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result


# ── Lifecycle ───────────────────────────────────────────────────────────────


@router.post("/{name}/start", summary="Start Emulator")
def start_emulator(name: str, req: StartRequest = StartRequest()):
    """Boot an emulator by AVD name."""
    mgr = get_manager()
    result = mgr.start(
        name,
        headless=req.headless,
        gpu=req.gpu,
        cold_boot=req.cold_boot,
        extra_args=req.extra_args,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Start failed"))
    return result


@router.post("/{name}/stop", summary="Stop Emulator by Name")
def stop_emulator(name: str):
    """Stop a running emulator by AVD name."""
    serial = _find_running_serial(name)
    mgr = get_manager()
    return mgr.stop(serial)


@router.post("/stop-by-serial", summary="Stop Emulator by Serial")
def stop_by_serial(req: StopBySerialRequest):
    """Stop a running emulator by ADB serial."""
    mgr = get_manager()
    return mgr.stop(req.serial)


@router.get("/running", summary="List Running Emulators")
def list_running():
    """List running emulators with serials and AVD names."""
    mgr = get_manager()
    return mgr.list_running()


@router.get("/{name}/boot-status", summary="Check Boot Status")
def boot_status(name: str):
    """Check if a named emulator has finished booting."""
    serial = _find_running_serial(name)
    mgr = get_manager()
    return mgr.get_boot_status(serial)


# ── Setup & Apps ────────────────────────────────────────────────────────────


@router.post("/{name}/setup", summary="Setup for Automation")
def setup_emulator(name: str):
    """Disable animations, set max timeout, configure for automation."""
    serial = _find_running_serial(name)
    mgr = get_manager()
    return mgr.setup_for_automation(serial)


@router.post("/{name}/install-apk", summary="Install APK")
def install_apk(name: str, req: ApkRequest):
    """Install an APK file on a running emulator."""
    serial = _find_running_serial(name)
    mgr = get_manager()
    return mgr.install_apk(serial, req.apk_path)


# ── Snapshots ───────────────────────────────────────────────────────────────


@router.post("/{name}/snapshot/save", summary="Save Snapshot")
def snapshot_save(name: str, req: SnapshotRequest = SnapshotRequest()):
    """Save emulator state to a named snapshot."""
    serial = _find_running_serial(name)
    mgr = get_manager()
    return mgr.snapshot_save(serial, req.snapshot_name)


@router.post("/{name}/snapshot/load", summary="Load Snapshot")
def snapshot_load(name: str, req: SnapshotRequest = SnapshotRequest()):
    """Restore emulator state from a named snapshot."""
    serial = _find_running_serial(name)
    mgr = get_manager()
    return mgr.snapshot_load(serial, req.snapshot_name)


@router.get("/{name}/snapshots", summary="List Snapshots")
def list_snapshots(name: str):
    """List available snapshots for a running emulator."""
    serial = _find_running_serial(name)
    mgr = get_manager()
    return mgr.list_snapshots(serial)


# ── System Images ───────────────────────────────────────────────────────────


@router.get("/system-images", summary="List System Images")
def list_system_images():
    """List installed Android system images."""
    mgr = get_manager()
    return mgr.list_system_images()


@router.post("/system-images/install", summary="Install System Image")
def install_system_image(req: ImageInstallRequest):
    """Download and install a system image via sdkmanager."""
    mgr = get_manager()
    result = mgr.install_system_image(
        api_level=req.api_level,
        target=req.target,
        arch=req.arch or "",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Install failed"))
    return result


# ── Emulator Pool ───────────────────────────────────────────────────────────


@pool_router.get("/status", summary="Pool Status")
def pool_status():
    """Get pool status: active, idle, busy counts + resource usage."""
    pool = get_pool()
    return pool.status()


@pool_router.post("/scale-up", summary="Scale Up Pool")
def pool_scale_up(req: PoolScaleUpRequest):
    """Start N emulators in the pool."""
    cfg_data = req.config or {}
    config = EmulatorConfig(
        name="_template",
        api_level=cfg_data.get("api_level", 35),
        target=cfg_data.get("target", "google_apis_playstore"),
        ram_mb=cfg_data.get("ram_mb", 2048),
        disk_mb=cfg_data.get("disk_mb", 4096),
        gpu=cfg_data.get("gpu", "swiftshader_indirect"),
        cores=cfg_data.get("cores", 2),
        headless=True,
    )
    pool = get_pool()
    result = pool.scale_up(req.count, config)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Scale up failed"))
    return result


@pool_router.post("/scale-down", summary="Scale Down Pool")
def pool_scale_down(req: PoolScaleDownRequest = PoolScaleDownRequest()):
    """Stop N idle emulators from the pool."""
    pool = get_pool()
    return pool.scale_down(req.count)


@pool_router.post("/stop-all", summary="Stop All Pool Emulators")
def pool_stop_all():
    """Stop every emulator managed by the pool."""
    pool = get_pool()
    return pool.stop_all()


@pool_router.get("/resources", summary="System Resources")
def pool_resources():
    """Get system resource usage (CPU, RAM, disk)."""
    pool = get_pool()
    return pool.resource_usage()
