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
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gitd.bots.common.device import get_device, is_ios_ref
from gitd.bots.common.ios import (
    _host_device_config_for_udid,
    remote_xpc_tunnel_status,
    strip_ios_prefix,
)

try:  # core-dev owns is_remote_ref (Ghost-side @host parsing); use it once it lands.
    from gitd.bots.common.device import is_remote_ref as _is_remote_ref
except ImportError:  # safe interim signal: only remote refs carry "@" (Android serials never do)

    def _is_remote_ref(ref: str) -> bool:
        return "@" in (ref or "")


def _env_force_localhost() -> bool:
    """Optional global override on top of the per-device signal (mixed hosts should
    prefer the per-device param; this is an escape hatch for all-remote deployments)."""
    return os.getenv("IOS_STREAM_FORCE_LOCALHOST", "").strip().lower() in ("1", "true", "yes")


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


def _candidate_urls(udid: str, port: int, force_localhost: bool = False) -> list[str]:
    urls = [f"ws://localhost:{port}/", f"ws://127.0.0.1:{port}/"]
    # Remote-drive (Linux Ghost -> SSH -> Mac -> iPhone, docs/ios/REMOTE_DRIVE.md):
    # the RemoteXPC tunnel IPv6 (fdxx::) is only routable ON the Mac, so a remote
    # caller must use the SSH-forwarded localhost port and MUST NOT probe the tunnel
    # address. force_localhost is passed PER-DEVICE (is_remote_ref(ref)) — not a
    # process-global — so a mixed host (a local iPhone physically on the Mac + a
    # remote one, both streaming) still lets the LOCAL device use its tunnel-IPv6
    # candidate while the remote one stays on localhost.
    if not force_localhost:
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


# Guard WDA launches: at most one in flight per device, and not more often than
# the cooldown — otherwise a reconnect storm spawns a pile of xcodebuild launches
# that jam the device and fight the dashboard's own session.
_session_locks: dict[str, asyncio.Lock] = {}
_last_ensure: dict[str, float] = {}
ENSURE_COOLDOWN = 30.0


async def _ensure_session(device: str) -> None:
    def _ens() -> None:
        try:
            get_device(device)._ensure_session()
        except Exception:
            pass

    await asyncio.to_thread(_ens)


async def _ensure_session_guarded(device: str, udid: str) -> None:
    """Launch WDA only if nothing else is launching it and it wasn't launched in
    the last ENSURE_COOLDOWN seconds. Concurrent callers wait for the in-flight
    launch instead of starting their own."""
    loop = asyncio.get_event_loop()
    lock = _session_locks.setdefault(udid, asyncio.Lock())
    if lock.locked():
        async with lock:  # someone is launching — just wait for it
            return
    async with lock:
        if loop.time() - _last_ensure.get(udid, 0.0) < ENSURE_COOLDOWN:
            return  # launched recently; don't relaunch
        _last_ensure[udid] = loop.time()
        await _ensure_session(device)


async def _connect_device(udid: str, port: int, force_localhost: bool = False):
    """Try each reachability strategy; return (ws, url) or (None, error)."""
    import websockets

    last_err = ""
    # _candidate_urls does a blocking tunnel-registry HTTP lookup; run it off the
    # event loop so it can't stall the WS handshake / other streams.
    candidates = await asyncio.to_thread(_candidate_urls, udid, port, force_localhost)
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
    # Remote refs (<name>@<host>) reach us over the SSH forward, where the tunnel
    # IPv6 isn't routable — force the localhost candidate for THIS device only.
    force_localhost = _is_remote_ref(device) or _env_force_localhost()
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
            # Try the device stream FIRST — if a session already exists (e.g. the
            # dashboard's), :9200 is up and we connect immediately with no launch.
            dev_ws, info = await _connect_device(udid, port, force_localhost)
            if dev_ws is None:
                # Not reachable — WDA probably isn't running. Launch it (guarded so
                # reconnect storms can't pile up xcodebuild), then retry once.
                with contextlib.suppress(Exception):
                    await client.send_json({"status": "starting WDA session"})
                await _ensure_session_guarded(device, udid)
                dev_ws, info = await _connect_device(udid, port, force_localhost)

            if dev_ws is None:
                # Still down — back off and retry (guard's cooldown prevents relaunch).
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
