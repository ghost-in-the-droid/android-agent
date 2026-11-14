"""One foreground parser shared by policy and system-popup detection."""
import subprocess

import pytest

from gitd.bots.common.adb import Device
from gitd.bots.common import package_policy
from gitd.skills.engine import os_popups


@pytest.mark.parametrize('window,activity,expected', [
    ('mCurrentFocus=Window{a u0 com.example/.Main}', '', 'com.example'),
    ('mCurrentFocus=null', 'topResumedActivity=ActivityRecord{b u0 com.fallback/.Main t1}', 'com.fallback'),
    ('mCurrentFocus=null', 'mResumedActivity: ActivityRecord{b u0 com.old/.Main t1}', 'com.old'),
    ('mCurrentFocus=Window{a u0 android/PermissionDialog}', '', 'android'),
    ('mCurrentFocus=Window{a u0 ImmersiveModeConfirmation}', '', 'android'),
    ('mCurrentFocus=null', 'topResumedActivity=null', ''),
    ('unrelated com.example/.Main', '', ''),
])
def test_foreground_owner(window, activity, expected, monkeypatch):
    calls = []
    def run(self, args, timeout):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, window if 'window' in args else activity, '')
    monkeypatch.setattr(Device, '_run_unchecked', run)
    assert Device('mock').foreground_package() == expected
    assert len(calls) == (1 if expected in {'com.example', 'android'} else 2)


def test_nonzero_window_falls_back_without_trusting_failed_output(monkeypatch):
    def run(self, args, timeout):
        return subprocess.CompletedProcess(args, 1 if 'window' in args else 0,
                                           'mCurrentFocus=Window{a u0 wrong/.Main}' if 'window' in args else '', '')
    monkeypatch.setattr(Device, '_run_unchecked', run)
    assert Device('mock').foreground_package() == ''


def test_both_consumers_use_device_method(monkeypatch):
    monkeypatch.setattr(Device, 'foreground_package', lambda self: 'com.android.permissioncontroller')
    assert package_policy._foreground('mock') == 'com.android.permissioncontroller'
    assert os_popups._system_dialog_focused('mock')


def test_popup_probe_failure_does_not_sweep(monkeypatch):
    def fail(self):
        raise TimeoutError('probe failed')
    monkeypatch.setattr(Device, 'foreground_package', fail)
    assert not os_popups._system_dialog_focused('mock')
