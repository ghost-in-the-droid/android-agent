"""
Base classes for the Skill framework.

Action  — single atomic UI operation (tap, type, navigate) with pre/post conditions
Workflow — composed sequence of Actions with retry and error handling
Skill   — loads skill.yaml, registers actions + workflows for an app
"""
from __future__ import annotations

import time
import logging
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gitd.bots.common.adb import Device

log = logging.getLogger(__name__)


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class ActionResult:
    success: bool
    data: dict = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0

    def __bool__(self):
        return self.success


# ── Element locator ───────────────────────────────────────────────────────────

@dataclass
class Element:
    """UI element with fallback locator chain."""
    name: str
    # Locator chain — tried in order until one matches
    content_desc: str | None = None
    text: str | None = None
    resource_id: str | None = None
    class_name: str | None = None
    # Fallback absolute coords (last resort)
    x: int | None = None
    y: int | None = None

    def find(self, device: Device, xml: str | None = None) -> tuple[int, int] | None:
        """Find element in current UI. Returns (cx, cy) or None."""
        if xml is None:
            xml = device.dump_xml()
        # Try each locator in priority order
        for key, attr in [
            (self.content_desc, 'content-desc'),
            (self.text, 'text'),
            (self.resource_id, 'resource-id'),
        ]:
            if key:
                bounds = device.find_bounds(xml, **{attr.replace('-', '_'): key})
                if bounds:
                    return device.bounds_center(bounds)
        # Fallback to class name
        if self.class_name:
            bounds = device.find_bounds(xml, resource_id=self.class_name)
            if bounds:
                return device.bounds_center(bounds)
        # Last resort: fixed coords
        if self.x is not None and self.y is not None:
            return (self.x, self.y)
        return None

    @classmethod
    def from_dict(cls, name: str, d: dict) -> Element:
        return cls(
            name=name,
            content_desc=d.get('content_desc'),
            text=d.get('text'),
            resource_id=d.get('resource_id'),
            class_name=d.get('class_name'),
            x=d.get('x'),
            y=d.get('y'),
        )


# ── Action ────────────────────────────────────────────────────────────────────

class Action(ABC):
    """Single atomic UI operation with pre/post conditions."""

    name: str = 'unnamed_action'
    description: str = ''
    max_retries: int = 2
    retry_delay: float = 1.0

    def __init__(self, device: Device, elements: dict[str, Element] | None = None):
        self.device = device
        self.elements = elements or {}

    def precondition(self) -> bool:
        """Check if the action can run. Override to add checks."""
        return True

    @abstractmethod
    def execute(self) -> ActionResult:
        """Run the action. Must return ActionResult."""
        ...

    def postcondition(self) -> bool:
        """Verify the action succeeded. Override to add checks."""
        return True

    def rollback(self):
        """Undo the action if postcondition fails. Override if needed."""
        pass

    def run(self) -> ActionResult:
        """Execute with pre/post checks and retry logic."""
        t0 = time.time()

        if not self.precondition():
            return ActionResult(success=False, error=f'{self.name}: precondition failed',
                                duration_ms=(time.time() - t0) * 1000)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self.execute()
                if result and self.postcondition():
                    result.duration_ms = (time.time() - t0) * 1000
                    return result
                if not result:
                    last_error = result.error or f'{self.name}: execute returned failure'
                else:
                    last_error = f'{self.name}: postcondition failed'
                    self.rollback()
            except Exception as e:
                last_error = f'{self.name}: {e}'
                log.warning(f'Action {self.name} attempt {attempt} failed: {e}')

            if attempt < self.max_retries:
                time.sleep(self.retry_delay)

        return ActionResult(success=False, error=last_error,
                            duration_ms=(time.time() - t0) * 1000)

    def find_element(self, name: str, xml: str | None = None) -> tuple[int, int] | None:
        """Convenience: find a named element from this action's element registry."""
        el = self.elements.get(name)
        return el.find(self.device, xml) if el else None


# ── Engine config ─────────────────────────────────────────────────────────────


@dataclass
class EngineConfig:
    """Tunable parameters for the skill execution engine.

    Set at class level (Workflow.engine = EngineConfig(...)), at instance level
    (wf.engine.back_count = 10), or per-run via _run_skill.py CLI flags.
    """
    back_count: int = 10              # how many Back presses during reset phase
    back_delay: float = 0.3           # delay between back presses (seconds)
    home_settle: float = 1.0          # sleep after Home press
    launch_settle: float = 2.0        # sleep after app launch
    step_settle: float = 0.0          # extra sleep after each step (on top of action's own)
    popup_chain_max: int = 3          # max chained popup dismissals per check
    auto_launch: bool = True          # run the startup sequence (wake, home, launch)
    skip_popup_detect: bool = False   # disable all popup detection between steps


# Default engine config — change this to affect all workflows globally
DEFAULT_ENGINE = EngineConfig()


# ── Workflow ──────────────────────────────────────────────────────────────────

class Workflow:
    """Composed sequence of Actions with the standard execution engine lifecycle:

    0) Wake screen
    1) Back-spam to reset to home
    2) Home button
    3) Launch app
    4) Popup detect
    5) Step 1 → popup detect
    6) Step 2 → popup detect
    ...
    N) Step N → popup detect
    """

    name: str = 'unnamed_workflow'
    description: str = ''
    app_package: str = ''             # set by Skill.get_workflow() from metadata
    engine: EngineConfig | None = None  # per-class override; falls back to DEFAULT_ENGINE

    def __init__(self, device: Device, elements: dict[str, Element] | None = None):
        self.device = device
        self.elements = elements or {}
        self.results: list[ActionResult] = []
        self._popup_detectors: list[dict] | None = None   # set by Skill.get_workflow()
        # Instance-level engine config — copy from class or global default
        if self.engine is None:
            self.engine = EngineConfig(**vars(DEFAULT_ENGINE))

    def steps(self) -> list[Action]:
        """Return the ordered list of Action instances. Override this."""
        return []

    # ── Execution engine ──────────────────────────────────────────────

    def _wake_and_reset(self):
        """Phase 0-2: Wake screen, back-spam to home, press Home."""
        cfg = self.engine
        dev = self.device
        log.info(f'[{self.name}] Waking screen, back ×{cfg.back_count}')
        dev.adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
        time.sleep(0.5)
        for _ in range(cfg.back_count):
            dev.back(delay=cfg.back_delay)
        time.sleep(0.5)
        dev.adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
        time.sleep(cfg.home_settle)

    def _launch_app(self):
        """Phase 3: Launch the target app."""
        if not self.app_package:
            return
        dev = self.device
        log.info(f'[{self.name}] Launching {self.app_package}')
        dev.adb('shell', 'monkey', '-p', self.app_package,
                '-c', 'android.intent.category.LAUNCHER', '1')
        time.sleep(self.engine.launch_settle)

    def _dismiss_popups(self, step_name: str = '') -> bool:
        """Phase 4+: Run popup detectors. Returns True if something was dismissed."""
        if self.engine.skip_popup_detect:
            return False
        xml = self.device.dump_xml()
        if not xml:
            return False
        dismissed = self.device.dismiss_popups(xml, popups=self._popup_detectors)
        if dismissed:
            log.info(f'[{self.name}] Popup dismissed after {step_name or "startup"}')
            time.sleep(0.5)
            for _ in range(self.engine.popup_chain_max - 1):
                xml = self.device.dump_xml()
                if not self.device.dismiss_popups(xml, popups=self._popup_detectors):
                    break
                time.sleep(0.5)
        return dismissed

    def run(self) -> ActionResult:
        """Execute the full lifecycle: startup → [step → popup detect] → done."""
        t0 = time.time()
        self.results = []
        cfg = self.engine

        # Startup sequence
        if cfg.auto_launch:
            self._wake_and_reset()
            self._launch_app()
            self._dismiss_popups()

        # Execute steps with popup detection between each
        for action in self.steps():
            log.info(f'[{self.name}] Running: {action.name}')
            result = action.run()
            self.results.append(result)
            if not result:
                log.error(f'[{self.name}] Failed at: {action.name} — {result.error}')
                return ActionResult(
                    success=False,
                    error=f'Workflow {self.name} failed at step {action.name}: {result.error}',
                    data={'completed_steps': len(self.results) - 1,
                          'failed_step': action.name},
                    duration_ms=(time.time() - t0) * 1000,
                )
            # Popup detection after each step
            self._dismiss_popups(action.name)
            if cfg.step_settle > 0:
                time.sleep(cfg.step_settle)

        return ActionResult(
            success=True,
            data={'completed_steps': len(self.results)},
            duration_ms=(time.time() - t0) * 1000,
        )


# ── Recorded skill support ────────────────────────────────────────────────────


class RecordedStepAction(Action):
    """Wraps a single JSON step from a recorded skill as a proper Action."""

    max_retries = 1
    retry_delay = 0.5

    def __init__(self, device: Device, step: dict, step_index: int):
        super().__init__(device)
        self._step = step
        self.name = f'step_{step_index + 1}_{step.get("action", "unknown")}'
        self.description = step.get('description', step.get('action', ''))

    def execute(self) -> ActionResult:
        step = self._step
        action = step.get('action', '')

        if action in ('launch', 'open_app'):
            pkg = step.get('package', '')
            if pkg:
                self.device.adb('shell', 'am', 'start', '-a', 'android.intent.action.MAIN',
                                '-c', 'android.intent.category.LAUNCHER', pkg)
        elif action == 'tap' and step.get('element_idx') is not None:
            import re
            import xml.etree.ElementTree as ET
            xml_str = self.device.dump_xml()
            if xml_str:
                root = ET.fromstring(xml_str)
                idx_counter = [0]
                target = [None]

                def _find(node):
                    text = node.get('text', '') or ''
                    desc = node.get('content-desc', '') or ''
                    rid = node.get('resource-id', '') or ''
                    clickable = node.get('clickable', '') == 'true'
                    if text or desc or rid or clickable:
                        idx_counter[0] += 1
                        if idx_counter[0] == step['element_idx']:
                            bounds = node.get('bounds', '')
                            m = re.findall(r'\[(\d+),(\d+)\]', bounds)
                            if len(m) == 2:
                                target[0] = ((int(m[0][0]) + int(m[1][0])) // 2,
                                             (int(m[0][1]) + int(m[1][1])) // 2)
                            return
                    for child in node:
                        if target[0]:
                            return
                        _find(child)

                for child in root:
                    if target[0]:
                        break
                    _find(child)
                if target[0]:
                    self.device.tap(target[0][0], target[0][1])
                else:
                    return ActionResult(success=False, error=f'element_idx {step["element_idx"]} not found')
        elif action == 'tap' and step.get('x') and step.get('y'):
            self.device.tap(step['x'], step['y'])
        elif action == 'type' and step.get('text'):
            text = step['text']
            if all(ord(c) < 128 for c in text):
                self.device.adb('shell', 'input', 'text', text.replace(' ', '%s'))
            else:
                self.device.type_unicode(text)
        elif action == 'back':
            self.device.back()
        elif action == 'home':
            self.device.adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
        elif action == 'swipe':
            self.device.swipe(step.get('x1', 0), step.get('y1', 0),
                              step.get('x2', 0), step.get('y2', 0))
        elif action == 'wait':
            time.sleep(step.get('seconds', 2))
        elif action == 'key':
            key = step.get('key', '')
            if key:
                if not key.startswith('KEYCODE_'):
                    key = 'KEYCODE_' + key
                self.device.adb('shell', 'input', 'keyevent', key)
        else:
            log.warning(f'Unknown recorded action: {action}')

        time.sleep(1.0)  # settle time between steps
        return ActionResult(success=True, data={'action': action})


class RecordedWorkflow(Workflow):
    """Wraps a recorded.json step list as a proper Workflow that runs through the engine."""

    name = 'recorded'
    description = 'Replay recorded steps'

    def __init__(self, device: Device, recorded_steps: list[dict], params: dict | None = None):
        super().__init__(device)
        self._raw_steps = recorded_steps
        self._params = params or {}

    def steps(self) -> list[Action]:
        actions = []
        for i, step in enumerate(self._raw_steps):
            # Resolve parameter placeholders
            resolved = dict(step)
            for field in ('text', 'package', 'description', 'goal'):
                if isinstance(resolved.get(field), str):
                    for k, v in self._params.items():
                        resolved[field] = resolved[field].replace(f'{{{k}}}', str(v))
            actions.append(RecordedStepAction(self.device, resolved, i))
        return actions


# ── Skill ─────────────────────────────────────────────────────────────────────

class Skill:
    """Loads skill.yaml, registers actions + workflows for an app."""

    def __init__(self, skill_dir: str | Path):
        self.skill_dir = Path(skill_dir)
        self.metadata: dict = {}
        self.elements: dict[str, Element] = {}
        self.popup_detectors: list[dict] = []
        self._actions: dict[str, type[Action]] = {}
        self._workflows: dict[str, type[Workflow]] = {}

        self._load_metadata()
        self._load_elements()

    def _load_metadata(self):
        path = self.skill_dir / 'skill.yaml'
        if path.exists():
            self.metadata = yaml.safe_load(path.read_text()) or {}
            self.popup_detectors = self.metadata.get('popup_detectors', [])
            log.info(f'Loaded skill: {self.metadata.get("name", self.skill_dir.name)}'
                     f' ({len(self.popup_detectors)} popup detectors)')

    def _load_elements(self):
        path = self.skill_dir / 'elements.yaml'
        if path.exists():
            raw = yaml.safe_load(path.read_text()) or {}
            for name, locators in raw.items():
                self.elements[name] = Element.from_dict(name, locators)
            log.info(f'Loaded {len(self.elements)} elements for {self.name}')

    @property
    def name(self) -> str:
        return self.metadata.get('name', self.skill_dir.name)

    @property
    def app_package(self) -> str:
        return self.metadata.get('app_package', '')

    @property
    def version(self) -> str:
        return self.metadata.get('version', '0.0.0')

    def register_action(self, action_cls: type[Action]):
        self._actions[action_cls.name] = action_cls

    def register_workflow(self, workflow_cls: type[Workflow]):
        self._workflows[workflow_cls.name] = workflow_cls

    def get_action(self, name: str, device: Device = None, **kwargs) -> Action | None:
        cls = self._actions.get(name)
        if not cls:
            return None
        if not device:
            return cls
        action = cls(device, self.elements, **kwargs)
        action._popup_detectors = self.popup_detectors or None
        return action

    def get_workflow(self, name: str, device: Device = None, **kwargs) -> Workflow | None:
        cls = self._workflows.get(name)
        if not cls:
            return None
        if not device:
            return cls
        wf = cls(device, self.elements, **kwargs)
        wf._popup_detectors = self.popup_detectors or None
        wf.app_package = self.metadata.get('app_package', '') or ''
        return wf

    def list_actions(self) -> list[str]:
        return list(self._actions.keys())

    def list_workflows(self) -> list[str]:
        return list(self._workflows.keys())
