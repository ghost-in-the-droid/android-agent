"""Streaming viewer routes: WebRTC viewer HTML pages."""

import hashlib
import html as html_lib
import json
import subprocess
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from gitd.bots.common.device import is_ios_ref
from gitd.models.base import get_db

router = APIRouter(tags=["streaming"])


def _stable_ws_port(serial: str) -> int:
    return 19000 + int(hashlib.md5(serial.encode()).hexdigest()[:3], 16) % 1000


def _stream_url(serial: str, *, fps: int = 10, mode: str = "mjpeg") -> str:
    query = urllib.parse.urlencode({"device": serial, "fps": fps, "mode": mode})
    return f"/api/phone/stream?{query}"


def _device_label(db: Session, serial: str) -> str:
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
    return label


def _viewer_config(serial: str, db: Session, *, setup_android: bool = True) -> dict:
    label = _device_label(db, serial)
    if is_ios_ref(serial):
        return {
            "serial": serial,
            "label": label,
            "platform": "ios",
            "mode": "wda-mjpeg",
            "streamUrl": _stream_url(serial, mode="wda-mjpeg"),
            "wsPort": None,
            "portalSupported": False,
        }

    from gitd.bots.common.adb import Device as AdbDevice

    local_ws = _stable_ws_port(serial)
    if setup_android:
        dev = AdbDevice(serial)
        dev._ensure_portal_forward()
        try:
            subprocess.run(
                ["adb", "-s", serial, "forward", f"tcp:{local_ws}", "tcp:8081"], capture_output=True, timeout=3
            )
        except Exception:
            pass
    return {
        "serial": serial,
        "label": label,
        "platform": "android",
        "mode": "portal-webrtc",
        "streamUrl": "",
        "wsPort": local_ws,
        "portalSupported": True,
    }


# ── WebRTC viewer pages ────────────────────────────────────────────────────


@router.get("/api/phone/webrtc-multi", summary="Multi-Device WebRTC Viewer Page")
def webrtc_multi_viewer(request: Request, db: Session = Depends(get_db)):
    """Multi-device WebRTC viewer."""
    devices = request.query_params.getlist("device")
    if not devices:
        raise HTTPException(status_code=400, detail="No devices specified")

    device_configs = [_viewer_config(serial, db) for serial in devices]

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
  .platform {{ font-size:10px; color:#94a3b8; margin-left:auto; }}
  video, img {{ width:100%; background:#000; display:block; }}
</style></head><body>
<div class="grid" id="grid"></div>
<script>
const DEVICES = {configs_json};
document.getElementById('grid').innerHTML = DEVICES.map(d =>
  '<div class="cell"><div class="cell-header"><span class="name">' + d.label + '</span>' +
  '<span class="platform">' + d.platform + ' · ' + d.mode + '</span></div>' +
  (d.platform === 'ios'
    ? '<img id="stream-' + d.serial + '" src="' + d.streamUrl + '" alt="' + d.label + ' stream" />'
    : '<video id="video-' + d.serial + '" autoplay playsinline muted></video>') +
  '</div>'
).join('');
</script></body></html>"""
    return HTMLResponse(content=html)


@router.get("/api/phone/webrtc-viewer", summary="Single-Device WebRTC Viewer Page")
def webrtc_viewer(device: str = "", db: Session = Depends(get_db)):
    """Standalone WebRTC viewer page."""
    cfg = _viewer_config(device, db, setup_android=False)
    label = cfg["label"]
    title_label = html_lib.escape(label)
    escaped_device = html_lib.escape(device)
    stream_url = html_lib.escape(str(cfg.get("streamUrl") or ""))
    platform = html_lib.escape(str(cfg["platform"]))
    mode = html_lib.escape(str(cfg["mode"]))
    media = (
        f'<img id="stream" src="{stream_url}" alt="{title_label} stream" />'
        if cfg["platform"] == "ios"
        else '<video id="video" autoplay playsinline muted></video>'
    )

    html = f"""<!DOCTYPE html>
<html><head><title>Phone Stream - {title_label}</title>
<style>
  body {{ background:#0f172a; color:#e2e8f0; font-family:monospace; margin:0; padding:20px; }}
  video, img {{ max-width:100%; max-height:85vh; border:1px solid #334155; border-radius:8px; background:#000; display:block; }}
  .toolbar {{ display:flex; gap:12px; align-items:center; margin-bottom:12px; }}
  button {{ background:#334155; color:#e2e8f0; border:1px solid #475569; padding:6px 16px;
           border-radius:4px; cursor:pointer; font-size:13px; }}
  .status {{ font-size:12px; color:#64748b; }}
  .pill {{ padding:2px 6px; border:1px solid #334155; border-radius:999px; color:#94a3b8; font-size:11px; }}
</style></head><body>
<div class="toolbar">
  <button onclick="location.reload()">Reload</button>
  <span class="status">Device: {escaped_device} ({title_label})</span>
  <span class="pill">{platform}</span>
  <span class="pill">{mode}</span>
</div>
{media}
<script>
const DEVICE = {json.dumps(device)};
const VIEWER_CONFIG = {json.dumps(cfg)};
// WebRTC viewer JS would go here - simplified for now
</script></body></html>"""
    return HTMLResponse(content=html)
