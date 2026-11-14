"""Shared, read-only helpers for Android accessibility XML snapshots.

``parse(xml)`` retains document order and positive-area, nonnegative bounds.
Text/description entities stay encoded, matching the engine's read-step contract;
callers that need decoded display text should explicitly use ``html.unescape``.
These helpers neither dump a device nor tap it. Selectors are exact matches.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

_ATTR_FOR = {'id': 'id', 'desc': 'desc', 'text': 'text', 'cls': 'cls', 'package': 'package'}


def parse(xml: str) -> list[dict]:
    """Read on-screen node attributes from a Portal/uiautomator XML snapshot."""
    out = []
    for match in re.finditer(r'<node\s+([^>]*)>', xml):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', match.group(1)))
        bounds = attrs.get('bounds', '')
        if not re.fullmatch(r'\[-?\d+,-?\d+\]\[-?\d+,-?\d+\]', bounds):
            continue
        x1, y1, x2, y2 = map(int, re.findall(r'-?\d+', bounds))
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            continue
        out.append({
            'text': attrs.get('text', ''), 'desc': attrs.get('content-desc', ''),
            'id': attrs.get('resource-id', ''), 'cls': attrs.get('class', ''),
            'package': attrs.get('package', ''), 'bounds': (x1, y1, x2, y2),
            'checked': attrs.get('checked') == 'true',
        })
    return out


def by(nodes: Iterable[Mapping[str, Any]], locator: str, value: str) -> list[dict]:
    """Return all exact matches in input order; unknown locators match nothing."""
    attr = _ATTR_FOR.get(locator)
    if attr is None:
        return []
    return [dict(node) for node in nodes if node.get(attr) == value]


def centre(node: Mapping[str, Any]) -> tuple[int, int]:
    """Integer centre of a parsed node's bounds; does not interact with a device."""
    x1, y1, x2, y2 = node['bounds']
    return (x1 + x2) // 2, (y1 + y2) // 2
