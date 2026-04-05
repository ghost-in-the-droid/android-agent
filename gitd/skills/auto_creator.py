"""
Phase 5: Auto Skill Creator — BFS app explorer that builds state graphs.

Usage:
    python3 -m gitd.skills.auto_creator \
        --package com.zhiliaoapp.musically \
        --device <your-serial> \
        --max-depth 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gitd.bots.common.adb import Device

log = logging.getLogger(__name__)


# ── State representation ─────────────────────────────────────────────────────

@dataclass
class AppState:
    """A snapshot of the app's UI state."""
    state_id: str                          # hash of xml structure
    screenshot_path: str = ""
    xml_path: str = ""
    elements: list[dict] = field(default_factory=list)
    transitions: dict[str, str] = field(default_factory=dict)  # element_key → next_state_id
    depth: int = 0
    activity: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── XML parsing ──────────────────────────────────────────────────────────────

def _parse_bounds(bounds_str: str) -> tuple[int, int, int, int] | None:
    """Parse '[x1,y1][x2,y2]' → (x1, y1, x2, y2)."""
    try:
        parts = bounds_str.replace("][", ",").strip("[]").split(",")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return None


def extract_interactive_elements(xml_str: str) -> list[dict]:
    """Extract clickable/scrollable/editable elements from UI XML dump.

    Handles both standard Android (clickable=true) and custom views (Portal XML)
    where clickable flags may be missing — falls back to heuristics.
    """
    elements = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return elements

    # Check if any node has clickable=true — if none, use heuristic mode
    has_any_clickable = any(
        n.get("clickable", "false") == "true" for n in root.iter()
    )

    idx = 0
    for node in root.iter():
        clickable = node.get("clickable", "false") == "true"
        scrollable = node.get("scrollable", "false") == "true"
        cls = node.get("class", "")
        editable = cls.endswith("EditText")

        # Heuristic mode: if no clickable flags, treat leaf nodes with
        # text/content-desc/resource-id as interactive
        if not has_any_clickable and not clickable:
            has_text = bool(node.get("text", "").strip())
            has_desc = bool(node.get("content-desc", "").strip())
            has_rid = bool(node.get("resource-id", "").strip())
            is_leaf = len(list(node)) == 0
            if is_leaf and (has_text or has_desc or has_rid):
                clickable = True

        if not (clickable or scrollable or editable):
            continue

        bounds = _parse_bounds(node.get("bounds", ""))
        if not bounds:
            continue

        x1, y1, x2, y2 = bounds
        # Skip tiny or offscreen elements
        w, h = x2 - x1, y2 - y1
        if w < 5 or h < 5 or x1 < 0 or y1 < 0:
            continue

        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        idx += 1

        elements.append({
            "idx": idx,
            "class": node.get("class", ""),
            "text": node.get("text", ""),
            "content_desc": node.get("content-desc", ""),
            "resource_id": node.get("resource-id", ""),
            "bounds": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "center": {"x": cx, "y": cy},
            "clickable": clickable,
            "scrollable": scrollable,
            "editable": editable,
        })

    return elements


def xml_structure_hash(xml_str: str) -> str:
    """Hash the structural skeleton of the XML (ignoring text content) for dedup."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return hashlib.md5(xml_str.encode()).hexdigest()[:12]

    def skeleton(node):
        """Recurse through tree, keeping class + resource-id but dropping text."""
        tag = node.get("class", node.tag)
        rid = node.get("resource-id", "")
        children = "".join(skeleton(c) for c in node)
        return f"<{tag} rid={rid}>{children}</{tag}>"

    skel = skeleton(root)
    return hashlib.md5(skel.encode()).hexdigest()[:12]


# ── Explorer ─────────────────────────────────────────────────────────────────

class AppExplorer:
    """BFS explorer that navigates through an app's UI states."""

    def __init__(self, dev: Device, package: str, output_dir: str, max_depth: int = 3,
                 max_states: int = 50, settle_time: float = 1.5):
        self.dev = dev
        self.package = package
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.max_states = max_states
        self.settle_time = settle_time

        self.states: dict[str, AppState] = {}
        self.queue: deque[tuple[str, int]] = deque()  # (state_id, depth)
        self._log_lines: list[str] = []  # recent log lines for progress.json

        # Create output dirs
        (self.output_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "xml").mkdir(parents=True, exist_ok=True)

    def _log_progress(self, msg: str):
        """Append a timestamped message to the progress log."""
        ts = time.strftime('%H:%M:%S')
        self._log_lines.append(f"[{ts}] {msg}")
        # Keep only last 30 lines
        if len(self._log_lines) > 30:
            self._log_lines = self._log_lines[-30:]

    def _write_progress(self, current_depth: int = 0):
        """Write progress.json for the dashboard to poll."""
        total_transitions = sum(len(s.transitions) for s in self.states.values())
        progress = {
            "states_found": len(self.states),
            "max_states": self.max_states,
            "transitions": total_transitions,
            "current_depth": current_depth,
            "log_tail": self._log_lines[-20:],
        }
        progress_path = self.output_dir / "progress.json"
        try:
            progress_path.write_text(json.dumps(progress))
        except Exception:
            pass

    def _get_activity(self) -> str:
        """Get current foreground activity."""
        try:
            out = subprocess.check_output(
                ["adb", "-s", self.dev.serial, "shell",
                 "dumpsys", "activity", "activities"],
                timeout=5, text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if "mResumedActivity" in line or "topResumedActivity" in line:
                    # Extract activity name
                    parts = line.split()
                    for p in parts:
                        if "/" in p and self.package in p:
                            return p.rstrip("}")
                    break
        except Exception:
            pass
        return "unknown"

    def _capture_state(self, depth: int) -> AppState | None:
        """Dump XML + screenshot, create AppState if new."""
        time.sleep(self.settle_time)

        xml_str = self.dev.dump_xml()
        if not xml_str or len(xml_str) < 50:
            log.warning("Empty XML dump, skipping")
            return None

        state_id = xml_structure_hash(xml_str)

        # Already visited?
        if state_id in self.states:
            return self.states[state_id]

        # Save XML
        xml_path = self.output_dir / "xml" / f"{state_id}.xml"
        xml_path.write_text(xml_str)

        # Screenshot
        ss_path = self.output_dir / "screenshots" / f"{state_id}.png"
        try:
            data = subprocess.check_output(
                ["adb", "-s", self.dev.serial, "exec-out", "screencap", "-p"],
                timeout=10
            )
            ss_path.write_bytes(data)
        except Exception as e:
            log.warning(f"Screenshot failed: {e}")

        elements = extract_interactive_elements(xml_str)
        activity = self._get_activity()

        state = AppState(
            state_id=state_id,
            screenshot_path=str(ss_path),
            xml_path=str(xml_path),
            elements=elements,
            depth=depth,
            activity=activity,
        )
        self.states[state_id] = state
        log.info(f"  New state {state_id} | depth={depth} | {len(elements)} elements | {activity}")
        clickable_count = sum(1 for e in elements if e.get("clickable"))
        self._log_progress(f"State {len(self.states)}: {activity or state_id} — {len(elements)} elements ({clickable_count} clickable)")
        self._write_progress(depth)
        return state

    def _element_key(self, elem: dict) -> str:
        """Create a unique key for an element (for transition tracking)."""
        rid = elem.get("resource_id", "")
        text = elem.get("text", "")
        desc = elem.get("content_desc", "")
        cx, cy = elem["center"]["x"], elem["center"]["y"]
        return f"{rid}|{text}|{desc}|{cx},{cy}"

    def explore(self) -> dict:
        """Run BFS exploration. Returns state graph as dict."""
        log.info(f"Starting BFS exploration of {self.package}")
        log.info(f"  Device: {self.dev.serial}")
        log.info(f"  Max depth: {self.max_depth}, Max states: {self.max_states}")
        log.info(f"  Output: {self.output_dir}")

        self._log_progress(f"Starting exploration of {self.package}")
        self._write_progress(0)

        # Launch app
        log.info("Launching app...")
        self._log_progress("Launching app...")
        subprocess.run(
            ["adb", "-s", self.dev.serial, "shell", "am", "force-stop", self.package],
            timeout=5, capture_output=True
        )
        time.sleep(0.5)
        subprocess.run(
            ["adb", "-s", self.dev.serial, "shell",
             "monkey", "-p", self.package, "-c", "android.intent.category.LAUNCHER", "1"],
            timeout=15, capture_output=True
        )
        time.sleep(8)  # Apps need time to load past splash/animations

        # Capture initial state
        initial = self._capture_state(depth=0)
        if not initial:
            log.error("Failed to capture initial state")
            return {"states": {}, "error": "Failed to capture initial state"}

        self.queue.append((initial.state_id, 0))

        # BFS loop
        while self.queue and len(self.states) < self.max_states:
            state_id, depth = self.queue.popleft()

            if depth >= self.max_depth:
                continue

            state = self.states[state_id]
            clickable = [e for e in state.elements if e.get("clickable")]

            log.info(f"Exploring state {state_id} (depth={depth}, {len(clickable)} clickable)")

            for elem in clickable[:10]:  # Limit clicks per state
                elem_key = self._element_key(elem)

                # Skip if already explored this transition
                if elem_key in state.transitions:
                    continue

                cx, cy = elem["center"]["x"], elem["center"]["y"]
                label = elem.get("text") or elem.get("content_desc") or elem.get("resource_id") or f"({cx},{cy})"
                log.info(f"  Tapping [{elem['idx']}] {label}")
                self._log_progress(f"Tapping element #{elem['idx']} \"{label}\"")
                self._write_progress(depth)

                # Tap the element
                self.dev.tap(cx, cy, delay=0)
                time.sleep(self.settle_time)

                # Capture new state
                new_state = self._capture_state(depth + 1)

                if new_state:
                    state.transitions[elem_key] = new_state.state_id

                    # If genuinely new, add to queue
                    if new_state.state_id != state_id and (new_state.state_id, depth + 1) not in [(s, d) for s, d in self.queue]:
                        self.queue.append((new_state.state_id, depth + 1))
                else:
                    state.transitions[elem_key] = "error"

                # Navigate back
                self.dev.back(delay=0)
                time.sleep(self.settle_time)

                # Verify we're back (check state hasn't drifted)
                back_state = self._capture_state(depth)
                if back_state and back_state.state_id != state_id:
                    log.warning(f"  Back didn't return to {state_id}, now at {back_state.state_id}")
                    # Try one more back
                    self.dev.back(delay=0)
                    time.sleep(self.settle_time)
                    retry = self._capture_state(depth)
                    if retry and retry.state_id != state_id:
                        log.warning(f"  Still lost after double-back. Stopping this state.")
                        break

                if len(self.states) >= self.max_states:
                    log.info(f"Max states ({self.max_states}) reached, stopping")
                    break

        # Build output
        graph = {
            "package": self.package,
            "device": self.dev.serial,
            "max_depth": self.max_depth,
            "total_states": len(self.states),
            "total_transitions": sum(len(s.transitions) for s in self.states.values()),
            "states": {sid: s.to_dict() for sid, s in self.states.items()},
        }

        # Save graph
        graph_path = self.output_dir / "state_graph.json"
        graph_path.write_text(json.dumps(graph, indent=2))
        log.info(f"Done! {len(self.states)} states, "
                 f"{sum(len(s.transitions) for s in self.states.values())} transitions")
        log.info(f"State graph saved to {graph_path}")
        self._log_progress(f"Done! {len(self.states)} states, "
                           f"{sum(len(s.transitions) for s in self.states.values())} transitions")
        self._write_progress(self.max_depth)
        # Clean up progress.json after writing final state_graph.json
        progress_path = self.output_dir / "progress.json"
        try:
            progress_path.unlink(missing_ok=True)
        except Exception:
            pass

        return graph


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auto Skill Creator — BFS app explorer")
    parser.add_argument("--package", required=True, help="App package name")
    parser.add_argument("--device", required=True, help="ADB device serial")
    parser.add_argument("--max-depth", type=int, default=3, help="Max BFS depth (default: 3)")
    parser.add_argument("--max-states", type=int, default=50, help="Max states to discover (default: 50)")
    parser.add_argument("--output", help="Output directory (default: data/app_explorer/<package>/)")
    parser.add_argument("--settle", type=float, default=1.5, help="Seconds to wait after actions (default: 1.5)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    output_dir = args.output or f"data/app_explorer/{args.package}"
    dev = Device(args.device)
    explorer = AppExplorer(
        dev=dev,
        package=args.package,
        output_dir=output_dir,
        max_depth=args.max_depth,
        max_states=args.max_states,
        settle_time=args.settle,
    )

    graph = explorer.explore()
    print(f"\nExploration complete:")
    print(f"  States: {graph.get('total_states', 0)}")
    print(f"  Transitions: {graph.get('total_transitions', 0)}")
    print(f"  Output: {output_dir}/state_graph.json")


if __name__ == "__main__":
    main()
