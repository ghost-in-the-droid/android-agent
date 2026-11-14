"""Offline Android fixture backend. It never calls adb or other processes.

A fixture directory contains device.json, fingerprint metadata, XML frame file
names, and optional operation-triggered transitions. Unsupported operations fail
explicitly instead of falling back to a real device.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from gitd.bots.common.adb import Device


class FakeDevice:
    is_fake = True
    # Reuse only Device's pure XML helpers, without inheriting its I/O methods.
    bounds_center = Device.bounds_center
    find_bounds = Device.find_bounds
    nodes = Device.nodes
    node_text = Device.node_text
    node_content_desc = Device.node_content_desc
    node_rid = Device.node_rid
    node_bounds = Device.node_bounds
    node_center = Device.node_center
    find_nodes = Device.find_nodes

    def __init__(self, serial: str):
        if not serial.startswith('fake:') or not serial[5:]:
            raise ValueError('Fake device ref must be fake:<fixture-directory>')
        self.serial = serial
        self.root = Path(serial[5:]).resolve()
        profile = json.loads((self.root / 'device.json').read_text())
        from gitd.skills.engine.evidence import validate_fingerprint
        self.fingerprint = validate_fingerprint(profile['fingerprint'])
        if self.fingerprint['os'] != 'android':
            raise ValueError('FakeDevice fixture backend supports Android only')
        self.frames = []
        for name in profile.get('frames', []):
            source = (self.root / name).resolve()
            if not source.is_relative_to(self.root):
                raise ValueError('Fake XML frame must be inside the fixture directory')
            xml = source.read_text()
            ET.fromstring(xml)
            self.frames.append(xml)
        if not self.frames:
            raise ValueError('Fake device fixture requires at least one XML frame')
        self.transitions = profile.get('transitions', [])
        for transition in self.transitions:
            if not isinstance(transition.get('on'), str) or not isinstance(transition.get('frame'), int) or not 0 <= transition['frame'] < len(self.frames):
                raise ValueError('Invalid fake device transition')
        self.frame = 0
        self.transition = 0
        self.operations = []

    def _operation(self, name, *args):
        self.operations.append((name, args))
        if self.transition < len(self.transitions):
            transition = self.transitions[self.transition]
            if name == transition['on']:
                self.frame = transition['frame']
                self.transition += 1

    def dump_xml(self, *args, **kwargs):
        self._operation('dump_xml')
        return self.frames[self.frame]

    def tap(self, x, y, delay=0, **kwargs):
        self._operation('tap', x, y)

    def press_enter(self, delay=0):
        self._operation('press_enter')

    def back(self, delay=0):
        self._operation('back')

    def home(self, delay=0):
        self._operation('home')

    def type_unicode(self, text):
        self._operation('type_text', text)

    def dismiss_popups(self, xml=None, popups=None):
        self._operation('dismiss_popups')
        return False

    def get_app_version(self, package):
        return self.fingerprint['app_version'] if package == self.fingerprint['app_package'] else 'unknown'

    def adb(self, *args, **kwargs):
        arguments = tuple(str(value) for value in args)
        if arguments[:3] == ('shell', 'input', 'text'):
            self._operation('type_text', *arguments[3:])
        elif arguments[:3] == ('shell', 'input', 'tap'):
            self._operation('tap', *arguments[3:])
        elif arguments[:3] == ('shell', 'input', 'swipe'):
            self._operation('swipe', *arguments[3:])
        elif arguments[:3] == ('shell', 'input', 'keyevent'):
            key = arguments[3] if len(arguments) > 3 else ''
            operation = {'66': 'press_enter', 'KEYCODE_ENTER': 'press_enter', '4': 'back', 'KEYCODE_BACK': 'back', '3': 'home', 'KEYCODE_HOME': 'home'}.get(key)
            if operation is None:
                raise RuntimeError(f'FakeDevice cannot replay key {key}')
            self._operation(operation)
        elif arguments[:3] in {('shell', 'am', 'start'), ('shell', 'am', 'force-stop')} or arguments[:2] == ('shell', 'monkey'):
            self._operation('launch_app', *arguments[2:])
        elif arguments[:3] == ('shell', 'dumpsys', 'window'):
            return self.fingerprint['app_package']
        elif arguments[:3] == ('shell', 'dumpsys', 'package'):
            return 'versionName=' + self.get_app_version(arguments[3])
        elif arguments[:2] == ('shell', 'getprop'):
            return {'ro.build.version.release': self.fingerprint['os_version'],
                    'ro.product.manufacturer': 'Fixture', 'ro.product.model': self.fingerprint['hardware']}.get(arguments[2], '')
        else:
            raise RuntimeError(f'FakeDevice cannot replay adb operation {arguments!r}')
        return ''

    def adb_soft(self, *args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=self.adb(*args, **kwargs), stderr='')
