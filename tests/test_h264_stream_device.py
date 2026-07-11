"""Device-backed verification of the GhostAgent H.264 stream (no browser needed).

Connects to the backend H.264 proxy (which relays the patched WDA's stream) and
parses the raw Annex-B bytes to prove the native encoder produces a *decodable*
stream: at least one SPS (NAL type 7) and one IDR keyframe (NAL type 5) must
arrive. This validates the whole native encode → WebSocket → proxy path without
WebCodecs.

Gated on a real iOS device + a running stack (backend + patched WDA + a live
session so the stream server is up). Skips otherwise, so CI stays green.
Requires the WDA rebuilt with FBH264StreamServer (see docs/ios/FLEET.md).
"""
import os

import pytest


def _ios_target() -> str:
    device = os.getenv("DEVICE", "")
    if device.startswith("ios:"):
        return device
    udid = os.getenv("IOS_DEVICE_UDID", "")
    return f"ios:{udid}" if udid else ""


pytestmark = pytest.mark.skipif(
    not _ios_target() or os.getenv("GHOST_H264_E2E") != "1",
    reason="H.264 device E2E disabled (set IOS_DEVICE_UDID + GHOST_H264_E2E=1 with the stack + patched WDA up)",
)

BACKEND = os.getenv("GHOST_BACKEND", "http://127.0.0.1:5055")


def _nal_types(annexb: bytes) -> list[int]:
    """Return the NAL unit types found in an Annex-B buffer."""
    types: list[int] = []
    i = 0
    n = len(annexb)
    while i + 3 < n:
        if annexb[i] == 0 and annexb[i + 1] == 0 and (
            annexb[i + 2] == 1 or (annexb[i + 2] == 0 and i + 3 < n and annexb[i + 3] == 1)
        ):
            start = i + 3 if annexb[i + 2] == 1 else i + 4
            if start < n:
                types.append(annexb[start] & 0x1F)
            i = start
        else:
            i += 1
    return types


def test_h264_stream_emits_decodable_keyframe():
    import asyncio

    import websockets

    device = _ios_target()
    ws_base = BACKEND.replace("http", "ws", 1)
    url = f"{ws_base}/api/phone/h264/{device}"

    async def run() -> list[int]:
        seen: list[int] = []
        async with websockets.connect(url, max_size=None, open_timeout=15) as ws:
            deadline = asyncio.get_event_loop().time() + 25
            while asyncio.get_event_loop().time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10)
                except asyncio.TimeoutError:
                    break
                if isinstance(msg, (bytes, bytearray)):
                    seen.extend(_nal_types(bytes(msg)))
                    # SPS (7) + IDR (5) means a decoder can start.
                    if 7 in seen and 5 in seen:
                        break
        return seen

    nal_types = asyncio.run(run())
    assert 7 in nal_types, f"no SPS (NAL 7) in stream; got NAL types {sorted(set(nal_types))}"
    assert 5 in nal_types, f"no IDR keyframe (NAL 5) in stream; got NAL types {sorted(set(nal_types))}"
