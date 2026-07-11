"""GhostAgent H.264 screen-stream proxy.

The patched WebDriverAgent runs an H.264-over-WebSocket server on the device
(mjpegServerPort + 100, e.g. :9200). Appium only forwards the single MJPEG port,
so the device stream port is not reachable at localhost. This router is a
hardened relay: the browser (or a fleet master) connects to a same-origin
WebSocket here, and the backend connects to the device stream over whichever
strategy works, with reconnect/backoff. One device connection can fan out to
many viewers.

Reachability strategies, in order (first that connects wins, remembered):
  1. localhost:<port>            — if a forward happens to exist
  2. [tunnel-ipv6-address]:<port> — the RemoteXPC tunnel route from the registry
  3. 127.0.0.1:<port>            — explicit loopback

Frontend decodes the Annex-B H.264 with WebCodecs. See docs/ios/FLEET.md.
"""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gitd.bots.common.device import get_device, is_ios_ref
from gitd.bots.common.ios import (
    _host_device_config_for_udid,
    remote_xpc_tunnel_status,
    strip_ios_prefix,
)

router = APIRouter(tags=["streaming"])

MJPEG_DEFAULT_PORT = 9100
H264_PORT_OFFSET = 100
CONNECT_TIMEOUT = 5.0
RECONNECT_BACKOFF_MIN = 0.5
RECONNECT_BACKOFF_MAX = 5.0


def _h264_port(udid: str) -> int:
    host = _host_device_config_for_udid(udid)
    try:
        base = int(host.get("mjpeg_server_port") or MJPEG_DEFAULT_PORT)
    except (TypeError, ValueError):
        base = MJPEG_DEFAULT_PORT
    return base + H264_PORT_OFFSET


def _candidate_urls(udid: str, port: int) -> list[str]:
    urls = [f"ws://localhost:{port}/", f"ws://127.0.0.1:{port}/"]
    try:
        tunnel = remote_xpc_tunnel_status(udid)
        addr = str((tunnel.get("registry") or {}).get("address") or "")
        if addr:
            host = f"[{addr}]" if ":" in addr and not addr.startswith("[") else addr
            urls.insert(0, f"ws://{host}:{port}/")  # tunnel route first — most reliable on iOS 17+
    except Exception:
        pass
    # de-dup, keep order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def _ensure_session(device: str) -> bool:
    """Ensure a WDA session is up — this launches WDA on the device, which starts
    the on-device H.264 server. Without it, the device :9200 port is closed and
    the relay just spins. Runs the (blocking) session setup off the event loop."""
    def _ens() -> bool:
        try:
            get_device(device)._ensure_session()
            return True
        except Exception:
            return False
    return await asyncio.to_thread(_ens)


async def _connect_device(udid: str, port: int):
    """Try each reachability strategy; return (ws, url) or (None, error)."""
    import websockets

    last_err = ""
    # _candidate_urls does a blocking tunnel-registry HTTP lookup; run it off the
    # event loop so it can't stall the WS handshake / other streams.
    candidates = await asyncio.to_thread(_candidate_urls, udid, port)
    for url in candidates:
        try:
            ws = await asyncio.wait_for(
                websockets.connect(url, max_size=None, open_timeout=CONNECT_TIMEOUT),
                timeout=CONNECT_TIMEOUT,
            )
            return ws, url
        except Exception as e:  # noqa: BLE001 — try the next strategy
            last_err = f"{url}: {e}"
    return None, last_err


@router.websocket("/api/phone/h264/{device}")
async def h264_stream(client: WebSocket, device: str):
    await client.accept()
    if not is_ios_ref(device):
        await client.send_json({"error": "h264 stream is iOS-only"})
        await client.close()
        return

    udid = strip_ios_prefix(device)
    port = _h264_port(udid)
    backoff = RECONNECT_BACKOFF_MIN
    stop = False

    async def pump_client_control():
        # Detect the browser going away; also drains any client messages.
        nonlocal stop
        try:
            while True:
                await client.receive_text()
        except Exception:
            stop = True

    control_task = asyncio.create_task(pump_client_control())

    try:
        while not stop:
            # Ensure WDA is running (starts the on-device H.264 server). Without a
            # session, :9200 is closed and we'd spin forever with "connecting".
            with contextlib.suppress(Exception):
                await client.send_json({"status": "starting WDA session"})
            await _ensure_session(device)

            dev_ws, info = await _connect_device(udid, port)
            if dev_ws is None:
                # Tell the client we're retrying (so the UI shows "reconnecting", not frozen).
                with contextlib.suppress(Exception):
                    await client.send_json({"status": "connecting", "detail": info})
                await asyncio.sleep(backoff)
                backoff = min(RECONNECT_BACKOFF_MAX, backoff * 2)
                continue

            backoff = RECONNECT_BACKOFF_MIN
            with contextlib.suppress(Exception):
                await client.send_json({"status": "connected", "via": info})
            try:
                async for frame in dev_ws:
                    if stop:
                        break
                    if isinstance(frame, (bytes, bytearray)):
                        await client.send_bytes(frame)
            except Exception:
                # device stream dropped — loop reconnects
                pass
            finally:
                with contextlib.suppress(Exception):
                    await dev_ws.close()
            if not stop:
                with contextlib.suppress(Exception):
                    await client.send_json({"status": "reconnecting"})
                await asyncio.sleep(backoff)
    except WebSocketDisconnect:
        pass
    finally:
        stop = True
        control_task.cancel()
        with contextlib.suppress(Exception):
            await control_task
        with contextlib.suppress(Exception):
            await client.close()
