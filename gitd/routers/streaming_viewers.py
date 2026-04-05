"""Streaming viewer routes: WebRTC viewer HTML pages."""

import hashlib
import json
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from gitd.models.base import get_db

router = APIRouter(tags=["streaming"])


def _stable_ws_port(serial: str) -> int:
    return 19000 + int(hashlib.md5(serial.encode()).hexdigest()[:3], 16) % 1000


# ── WebRTC viewer pages ────────────────────────────────────────────────────


@router.get("/api/phone/webrtc-multi", summary="Multi-Device WebRTC Viewer Page")
def webrtc_multi_viewer(request: Request, db: Session = Depends(get_db)):
    """Multi-device WebRTC viewer."""
    devices = request.query_params.getlist("device")
    if not devices:
        raise HTTPException(status_code=400, detail="No devices specified")

    from gitd.bots.common.adb import Device as AdbDevice

    device_configs = []
    for serial in devices:
        dev = AdbDevice(serial)
        dev._ensure_portal_forward()
        local_ws = _stable_ws_port(serial)
        try:
            subprocess.run(
                ["adb", "-s", serial, "forward", f"tcp:{local_ws}", "tcp:8081"], capture_output=True, timeout=3
            )
        except Exception:
            pass
        label = serial[:8]
        try:
            row = db.execute(
                text("SELECT nickname FROM phones WHERE serial = :serial"),
                {"serial": serial},
            ).first()
            if row and row[0]:
                label = row[0]
        except Exception:
            pass
        device_configs.append({"serial": serial, "label": label, "wsPort": local_ws})

    configs_json = json.dumps(device_configs)
    cols = min(len(devices), 3)
    # Return a minimal HTML page referencing the configs
    html = f"""<!DOCTYPE html>
<html><head><title>Multi-Device WebRTC Stream</title>
<style>
  body {{ background:#0f172a; color:#e2e8f0; font-family:monospace; margin:0; padding:12px; }}
  .grid {{ display:grid; grid-template-columns:repeat({cols}, 1fr); gap:8px; }}
  .cell {{ background:#111827; border:1px solid #1e2438; border-radius:8px; overflow:hidden; }}
  .cell-header {{ padding:6px 10px; display:flex; align-items:center; gap:8px; background:#0d1018; }}
  .name {{ font-size:12px; font-weight:600; }}
  video {{ width:100%; background:#000; }}
</style></head><body>
<div class="grid" id="grid"></div>
<script>
const DEVICES = {configs_json};
document.getElementById('grid').innerHTML = DEVICES.map(d =>
  '<div class="cell"><div class="cell-header"><span class="name">' + d.label + '</span></div>' +
  '<video id="video-' + d.serial + '" autoplay playsinline muted></video></div>'
).join('');
</script></body></html>"""
    return HTMLResponse(content=html)


@router.get("/api/phone/webrtc-viewer", summary="Single-Device WebRTC Viewer Page")
def webrtc_viewer(device: str = "", db: Session = Depends(get_db)):
    """Standalone WebRTC viewer page."""
    label = device[:8]
    try:
        row = db.execute(
            text("SELECT nickname FROM phones WHERE serial = :serial"),
            {"serial": device},
        ).first()
        if row and row[0]:
            label = row[0]
    except Exception:
        pass

    html = f"""<!DOCTYPE html>
<html><head><title>Phone Stream - {label}</title>
<style>
  body {{ background:#0f172a; color:#e2e8f0; font-family:monospace; margin:0; padding:20px; }}
  video {{ max-width:100%; max-height:85vh; border:1px solid #334155; border-radius:8px; background:#000; }}
  .toolbar {{ display:flex; gap:12px; align-items:center; margin-bottom:12px; }}
  button {{ background:#334155; color:#e2e8f0; border:1px solid #475569; padding:6px 16px;
           border-radius:4px; cursor:pointer; font-size:13px; }}
  .status {{ font-size:12px; color:#64748b; }}
</style></head><body>
<div class="toolbar">
  <button onclick="location.reload()">Reload</button>
  <span class="status">Device: {device} ({label})</span>
</div>
<video id="video" autoplay playsinline muted></video>
<script>
const DEVICE = "{device}";
// WebRTC viewer JS would go here - simplified for now
</script></body></html>"""
    return HTMLResponse(content=html)
