"""Unit tests for the H.264 stream proxy's reachability logic (no hardware).

The robustness of the stream hinges on _candidate_urls picking the right device
endpoints in the right order and never throwing, and on _h264_port deriving the
device stream port from the MJPEG port. These are pure/mockable, so they run in
CI without a phone.
"""
import pytest

from gitd.routers import h264_stream as h


def test_h264_port_default(monkeypatch):
    monkeypatch.setattr(h, "_host_device_config_for_udid", lambda udid: {})
    assert h._h264_port("any") == 9200  # 9100 (default mjpeg) + 100


def test_h264_port_from_custom_mjpeg_port(monkeypatch):
    monkeypatch.setattr(h, "_host_device_config_for_udid", lambda udid: {"mjpeg_server_port": 9500})
    assert h._h264_port("any") == 9600


def test_h264_port_bad_value_falls_back(monkeypatch):
    monkeypatch.setattr(h, "_host_device_config_for_udid", lambda udid: {"mjpeg_server_port": "nope"})
    assert h._h264_port("any") == 9200


def test_candidate_urls_prefers_tunnel_address(monkeypatch):
    monkeypatch.setattr(
        h, "remote_xpc_tunnel_status",
        lambda udid: {"registry": {"address": "fd23:a45d:8f2d::1"}},
    )
    urls = h._candidate_urls("udid", 9200)
    # Tunnel IPv6 route first (most reliable on iOS 17+), bracketed.
    assert urls[0] == "ws://[fd23:a45d:8f2d::1]:9200/"
    # localhost fallbacks still present.
    assert "ws://localhost:9200/" in urls
    assert "ws://127.0.0.1:9200/" in urls
    # No duplicates.
    assert len(urls) == len(set(urls))


def test_candidate_urls_without_tunnel(monkeypatch):
    monkeypatch.setattr(h, "remote_xpc_tunnel_status", lambda udid: {})
    urls = h._candidate_urls("udid", 9200)
    assert urls  # never empty
    assert all(("localhost" in u) or ("127.0.0.1" in u) for u in urls)


def test_candidate_urls_never_throws(monkeypatch):
    def boom(_udid):
        raise RuntimeError("tunnel registry down")

    monkeypatch.setattr(h, "remote_xpc_tunnel_status", boom)
    # Robustness: a tunnel-status failure must NOT crash the relay setup.
    urls = h._candidate_urls("udid", 9200)
    assert urls  # falls back to localhost candidates


def test_candidate_urls_ipv4_address_not_bracketed(monkeypatch):
    monkeypatch.setattr(
        h, "remote_xpc_tunnel_status",
        lambda udid: {"registry": {"address": "10.0.0.5"}},
    )
    urls = h._candidate_urls("udid", 9200)
    assert urls[0] == "ws://10.0.0.5:9200/"
