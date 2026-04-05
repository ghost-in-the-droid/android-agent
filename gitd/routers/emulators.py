"""
Emulator management API — Flask Blueprint.

All emulator lifecycle operations: list, create, delete, start, stop,
setup, install APK, snapshots, system images, pool management.
"""

from flask import Blueprint, jsonify, request

from gitd.services.emulator_service import (
    EmulatorConfig,
    get_manager,
    get_pool,
)

bp = Blueprint("emulators", __name__, url_prefix="/api/emulators")
pool_bp = Blueprint("emulator_pool", __name__, url_prefix="/api/emulator-pool")


# ── Prerequisites ────────────────────────────────────────────────────────────


@bp.route("/prerequisites", methods=["GET"])
def prerequisites():
    """Check SDK tool availability."""
    mgr = get_manager()
    return jsonify(mgr.check_prerequisites())


# ── AVD CRUD ─────────────────────────────────────────────────────────────────


@bp.route("", methods=["GET"])
def list_avds():
    """List all AVDs (created + running status)."""
    mgr = get_manager()
    return jsonify(mgr.list_avds())


@bp.route("", methods=["POST"])
def create_avd():
    """Create a new AVD.
    Body: {name, api_level?, target?, device_profile?, ram_mb?, disk_mb?,
           resolution?, dpi?, gpu?, cores?, headless?, snapshot?}
    """
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400

    config = EmulatorConfig(
        name=name,
        api_level=data.get("api_level", 35),
        target=data.get("target", "google_apis_playstore"),
        arch=data.get("arch", "x86_64"),
        device_profile=data.get("device_profile", "medium_phone"),
        ram_mb=data.get("ram_mb", 2048),
        disk_mb=data.get("disk_mb", 6144),
        resolution=data.get("resolution", "1080x2400"),
        dpi=data.get("dpi", 420),
        gpu=data.get("gpu", "auto"),
        cores=data.get("cores", 2),
        headless=data.get("headless", False),
        snapshot=data.get("snapshot", True),
    )
    mgr = get_manager()
    result = mgr.create(config)
    status_code = 201 if result.get("ok") else 400
    return jsonify(result), status_code


@bp.route("/<name>", methods=["DELETE"])
def delete_avd(name):
    """Delete an AVD."""
    mgr = get_manager()
    result = mgr.delete(name)
    status_code = 200 if result.get("ok") else 404
    return jsonify(result), status_code


# ── Lifecycle ────────────────────────────────────────────────────────────────


@bp.route("/<name>/start", methods=["POST"])
def start_emulator(name):
    """Start an emulator.
    Body: {headless?: bool, gpu?: str, cold_boot?: bool, extra_args?: list}
    """
    data = request.json or {}
    mgr = get_manager()
    result = mgr.start(
        name,
        headless=data.get("headless", False),
        gpu=data.get("gpu", "auto"),
        cold_boot=data.get("cold_boot", False),
        extra_args=data.get("extra_args"),
    )
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


@bp.route("/<name>/stop", methods=["POST"])
def stop_emulator(name):
    """Stop an emulator by AVD name — finds its serial first."""
    mgr = get_manager()
    for info in mgr.list_running():
        if info["name"] == name:
            result = mgr.stop(info["serial"])
            return jsonify(result)
    return jsonify({"ok": False, "error": f'Emulator "{name}" is not running'}), 404


@bp.route("/stop-by-serial", methods=["POST"])
def stop_by_serial():
    """Stop an emulator by serial. Body: {serial}"""
    data = request.json or {}
    serial = data.get("serial")
    if not serial:
        return jsonify({"ok": False, "error": "serial is required"}), 400
    mgr = get_manager()
    result = mgr.stop(serial)
    return jsonify(result)


@bp.route("/running", methods=["GET"])
def list_running():
    """List running emulators with serials and AVD names."""
    mgr = get_manager()
    return jsonify(mgr.list_running())


@bp.route("/<name>/boot-status", methods=["GET"])
def boot_status(name):
    """Check if an emulator has booted. Finds serial by name."""
    mgr = get_manager()
    for info in mgr.list_running():
        if info["name"] == name:
            return jsonify(mgr.get_boot_status(info["serial"]))
    return jsonify({"booted": False, "error": f'Emulator "{name}" is not running'}), 404


# ── Setup & Apps ─────────────────────────────────────────────────────────────


@bp.route("/<name>/setup", methods=["POST"])
def setup_emulator(name):
    """Run automation setup (disable animations, max timeout, etc.)."""
    mgr = get_manager()
    for info in mgr.list_running():
        if info["name"] == name:
            result = mgr.setup_for_automation(info["serial"])
            return jsonify(result)
    return jsonify({"ok": False, "error": f'Emulator "{name}" is not running'}), 404


@bp.route("/<name>/install-apk", methods=["POST"])
def install_apk(name):
    """Install APK on emulator. Body: {apk_path}"""
    data = request.json or {}
    apk_path = data.get("apk_path")
    if not apk_path:
        return jsonify({"ok": False, "error": "apk_path is required"}), 400
    mgr = get_manager()
    for info in mgr.list_running():
        if info["name"] == name:
            result = mgr.install_apk(info["serial"], apk_path)
            return jsonify(result)
    return jsonify({"ok": False, "error": f'Emulator "{name}" is not running'}), 404


# ── Snapshots ────────────────────────────────────────────────────────────────


@bp.route("/<name>/snapshot/save", methods=["POST"])
def snapshot_save(name):
    """Save emulator snapshot. Body: {snapshot_name?: str}"""
    data = request.json or {}
    snap_name = data.get("snapshot_name", "automation_ready")
    mgr = get_manager()
    for info in mgr.list_running():
        if info["name"] == name:
            result = mgr.snapshot_save(info["serial"], snap_name)
            return jsonify(result)
    return jsonify({"ok": False, "error": f'Emulator "{name}" is not running'}), 404


@bp.route("/<name>/snapshot/load", methods=["POST"])
def snapshot_load(name):
    """Load emulator snapshot. Body: {snapshot_name?: str}"""
    data = request.json or {}
    snap_name = data.get("snapshot_name", "automation_ready")
    mgr = get_manager()
    for info in mgr.list_running():
        if info["name"] == name:
            result = mgr.snapshot_load(info["serial"], snap_name)
            return jsonify(result)
    return jsonify({"ok": False, "error": f'Emulator "{name}" is not running'}), 404


@bp.route("/<name>/snapshots", methods=["GET"])
def list_snapshots(name):
    """List snapshots for a running emulator."""
    mgr = get_manager()
    for info in mgr.list_running():
        if info["name"] == name:
            result = mgr.list_snapshots(info["serial"])
            return jsonify(result)
    return jsonify({"ok": False, "error": f'Emulator "{name}" is not running'}), 404


# ── System Images ────────────────────────────────────────────────────────────


@bp.route("/system-images", methods=["GET"])
def list_system_images():
    """List installed system images."""
    mgr = get_manager()
    return jsonify(mgr.list_system_images())


@bp.route("/system-images/install", methods=["POST"])
def install_system_image():
    """Download a new system image. Body: {api_level, target?, arch?}"""
    data = request.json or {}
    api_level = data.get("api_level")
    if not api_level:
        return jsonify({"ok": False, "error": "api_level is required"}), 400
    mgr = get_manager()
    result = mgr.install_system_image(
        api_level=int(api_level),
        target=data.get("target", "google_apis_playstore"),
        arch=data.get("arch", "x86_64"),
    )
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


# ── Emulator Pool ────────────────────────────────────────────────────────────


@pool_bp.route("/status", methods=["GET"])
def pool_status():
    """Pool status (active, idle, busy counts + resources)."""
    pool = get_pool()
    return jsonify(pool.status())


@pool_bp.route("/scale-up", methods=["POST"])
def pool_scale_up():
    """Start N emulators. Body: {count, config?: {api_level, ram_mb, ...}}"""
    data = request.json or {}
    count = data.get("count", 1)
    cfg_data = data.get("config", {})
    config = EmulatorConfig(
        name="_template",  # ignored — pool generates names
        api_level=cfg_data.get("api_level", 35),
        target=cfg_data.get("target", "google_apis_playstore"),
        ram_mb=cfg_data.get("ram_mb", 2048),
        disk_mb=cfg_data.get("disk_mb", 4096),
        gpu=cfg_data.get("gpu", "swiftshader_indirect"),
        cores=cfg_data.get("cores", 2),
        headless=True,
    )
    pool = get_pool()
    result = pool.scale_up(count, config)
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


@pool_bp.route("/scale-down", methods=["POST"])
def pool_scale_down():
    """Stop N idle emulators. Body: {count?: int} (null = all idle)"""
    data = request.json or {}
    count = data.get("count")
    pool = get_pool()
    result = pool.scale_down(count)
    return jsonify(result)


@pool_bp.route("/stop-all", methods=["POST"])
def pool_stop_all():
    """Stop all pool emulators."""
    pool = get_pool()
    result = pool.stop_all()
    return jsonify(result)


@pool_bp.route("/resources", methods=["GET"])
def pool_resources():
    """System resource usage (CPU, RAM, disk)."""
    pool = get_pool()
    return jsonify(pool.resource_usage())
