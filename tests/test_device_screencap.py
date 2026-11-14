"""Binary screenshot transport errors and package-policy boundaries."""
import subprocess

import pytest

from gitd.bots.common.adb import ADBError, Device
from gitd.bots.common import package_policy as policy

PNG = b'\x89PNG\r\n\x1a\n\x00\xff\r\n'


def test_screencap_preserves_binary_and_uses_device_transport(monkeypatch):
    monkeypatch.delenv('GHOST_DENY_PACKAGES', raising=False)
    calls = []
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, PNG, b'')
    monkeypatch.setattr(subprocess, 'run', run)
    assert Device('mock').screencap_png(timeout=7) == PNG
    assert calls == [(['adb', '-s', 'mock', 'exec-out', 'screencap', '-p'],
                      {'capture_output': True, 'text': False, 'timeout': 7})]


@pytest.mark.parametrize('error,code,message', [
    (FileNotFoundError(), 127, 'not found'),
    (subprocess.TimeoutExpired('adb', 3), -1, 'timed out'),
])
def test_screencap_transport_errors(monkeypatch, error, code, message):
    monkeypatch.delenv('GHOST_DENY_PACKAGES', raising=False)
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(ADBError, match=message) as exc:
        Device('mock').screencap_png()
    assert exc.value.returncode == code


@pytest.mark.parametrize('code,stdout,stderr,message', [
    (1, b'not PNG', b'permission denied\xff', 'permission denied'),
    (0, b'error: secure display', b'', 'did not return PNG'),
])
def test_screencap_rejects_failed_or_non_png_output(monkeypatch, code, stdout, stderr, message):
    monkeypatch.delenv('GHOST_DENY_PACKAGES', raising=False)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, code, stdout, stderr))
    with pytest.raises(ADBError, match=message):
        Device('mock').screencap_png()


def test_denied_foreground_blocks_capture_before_transport(monkeypatch):
    monkeypatch.setenv('GHOST_DENY_PACKAGES', 'com.example.private')
    monkeypatch.setattr(Device, 'foreground_package', lambda self: 'com.example.private')
    homes = []
    monkeypatch.setattr(policy, '_raw', lambda *a: homes.append(a) or subprocess.CompletedProcess(a, 0, '', ''))
    monkeypatch.setattr(Device, '_run', lambda *a, **k: pytest.fail('denied capture executed'))
    with pytest.raises(policy.PackagePolicyError, match='denied foreground'):
        Device('mock').screencap_png()
    assert len(homes) == 1


def test_capture_that_lands_in_denied_package_returns_no_bytes(monkeypatch):
    monkeypatch.setenv('GHOST_DENY_PACKAGES', 'com.example.private')
    owners = iter(['com.example.allowed', 'com.example.private'])
    monkeypatch.setattr(Device, 'foreground_package', lambda self: next(owners))
    monkeypatch.setattr(policy, '_raw', lambda *a: subprocess.CompletedProcess(a, 0, '', ''))
    monkeypatch.setattr(Device, '_run', lambda *a, **k: subprocess.CompletedProcess(a, 0, PNG, b''))
    with pytest.raises(policy.PackagePolicyError, match='denied foreground'):
        Device('mock').screencap_png()
