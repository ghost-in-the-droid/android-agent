"""Conservative import of Maestro YAML and structured Automate flow exports.

Native binary Automate .flo files are retained verbatim with a TODO placeholder.
No undocumented binary interpretation or source execution is attempted.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ImportedFlow:
    name: str
    app_package: str
    steps: list[dict]
    warnings: list[str]


def action_name(name: str) -> str:
    name = re.sub(r'[^a-z0-9_-]+', '_', str(name).lower()).strip('_-')
    if not name or not name[0].isalpha():
        name = 'flow_' + name
    return name[:64]


def _todo(node, reason: str) -> dict:
    return {'action': 'sleep', 'duration_s': 0,
            'note': 'TODO imported node: ' + reason,
            'import_unmapped': {'reason': reason, 'source': node}}


def _selector(value):
    if isinstance(value, str) and value:
        return {'text': value}
    if isinstance(value, dict) and len(value) == 1:
        key, target = next(iter(value.items()))
        if key in {'text', 'id'} and isinstance(target, str) and target:
            return {key: target}
    return None


def _coordinates(value):
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(',')]
    elif isinstance(value, list):
        parts = value
    else:
        return None
    if len(parts) != 2:
        return None
    try:
        return [int(part) for part in parts]
    except (ValueError, TypeError):
        return None


def _swipe(value):
    if not isinstance(value, dict) or set(value) - {'start', 'end', 'duration', 'duration_ms'}:
        return None
    start, end = _coordinates(value.get('start')), _coordinates(value.get('end'))
    if start is None or end is None:
        return None
    duration = value.get('duration_ms', value.get('duration', 300))
    if not isinstance(duration, (int, float)) or duration <= 0:
        return None
    return dict(action='swipe', x1=start[0], y1=start[1], x2=end[0], y2=end[1], duration_ms=int(duration))


def _maestro_step(node, app_package):
    if isinstance(node, str):
        command, value = node, None
    elif isinstance(node, dict) and len(node) == 1:
        command, value = next(iter(node.items()))
    else:
        return None
    if command == 'launchApp':
        if value is None:
            return {'action': 'launch_app', 'package': app_package}
        if isinstance(value, dict) and set(value) == {'appId'} and isinstance(value['appId'], str):
            return {'action': 'launch_app', 'package': value['appId']}
    elif command in {'tapOn', 'assertVisible'}:
        selector = _selector(value)
        if selector:
            if command == 'tapOn':
                return {'action': 'tap_element', **selector}
            return {'action': 'wait_for_text' if 'text' in selector else 'wait_for_element', **selector}
    elif command == 'inputText' and isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return {'action': 'type_text', 'text': str(value)}
    elif command == 'back' and value is None:
        return {'action': 'press_key', 'key': 'BACK'}
    elif command == 'swipe':
        return _swipe(value)
    return None


def parse_maestro(source: Path) -> list[ImportedFlow]:
    try:
        documents = list(yaml.safe_load_all(source.read_text(encoding='utf-8')))
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ValueError(f'Cannot parse Maestro YAML: {exc}') from exc
    if len(documents) != 2 or not isinstance(documents[0], dict) or not isinstance(documents[1], list):
        raise ValueError('Maestro flow must contain an appId header, then --- and a command list')
    config, commands = documents
    app_package = config.get('appId')
    if not isinstance(app_package, str) or not app_package.strip():
        raise ValueError('Maestro flow header requires appId')
    name = action_name(config.get('name') or source.stem)
    steps, warnings = [], []
    extra = {key: value for key, value in config.items() if key not in {'appId', 'name'}}
    if extra:
        reason = 'Maestro header options require manual translation'
        steps.append(_todo(extra, reason)); warnings.append(reason)
    for index, node in enumerate(commands):
        step = _maestro_step(node, app_package)
        if step is None:
            reason = f'Maestro command {index}: unsupported command or options'
            step = _todo(node, reason); warnings.append(reason)
        steps.append(step)
    if not steps:
        steps.append(_todo([], 'Empty Maestro command list')); warnings.append('Empty Maestro command list')
    return [ImportedFlow(name, app_package, steps, warnings)]


def _automate_step(block, app_package):
    if not isinstance(block, dict):
        return None
    # Only straight-line, explicit literal blocks can be replayed faithfully.
    if set(block) - {'id', 'type', 'args', 'next'}:
        return None
    kind = block.get('type')
    args = block.get('args', {})
    if not isinstance(args, dict):
        return None
    if kind == 'flow_begin' and not args:
        return {'action': 'sleep', 'duration_s': 0, 'note': 'Imported Automate flow beginning'}
    if kind == 'app_start' and set(args) <= {'package'}:
        package = args.get('package', app_package)
        if isinstance(package, str) and package:
            return {'action': 'launch_app', 'package': package}
    if kind == 'interact':
        selector = _selector(args)
        if selector:
            return {'action': 'tap_element', **selector}
    if kind == 'input_text' and set(args) == {'text'} and isinstance(args['text'], str):
        return {'action': 'type_text', 'text': args['text']}
    if kind == 'key_press' and set(args) == {'key'} and args['key'] == 'BACK':
        return {'action': 'press_key', 'key': 'BACK'}
    if kind == 'delay' and set(args) == {'seconds'} and isinstance(args['seconds'], (int, float)) and args['seconds'] >= 0:
        return {'action': 'sleep', 'duration_s': args['seconds']}
    if kind == 'swipe':
        return _swipe(args)
    if kind == 'assert_visible':
        selector = _selector(args)
        if selector:
            return {'action': 'wait_for_text' if 'text' in selector else 'wait_for_element', **selector}
    return None


def parse_automate(source: Path) -> list[ImportedFlow]:
    raw = source.read_bytes()
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError):
        reason = 'Native binary or unsupported Automate format; source preserved in imported-source.flo'
        return [ImportedFlow(action_name(source.stem), 'com.example.app', [_todo({'source_file': 'imported-source.flo'}, reason)], [reason])]
    if not isinstance(data, dict):
        raise ValueError('Structured Automate export must be an object with flows or blocks')
    flows = data.get('flows', [data])
    if not isinstance(flows, list) or not flows:
        raise ValueError('Automate export must contain at least one flow')
    result = []
    used_names = set()
    for flow_index, flow in enumerate(flows):
        if not isinstance(flow, dict) or not isinstance(flow.get('blocks'), list):
            raise ValueError('Each Automate flow requires a blocks list')
        app = flow.get('app_package') or 'com.example.app'
        if not isinstance(app, str):
            raise ValueError('Automate app_package must be text')
        name = action_name(flow.get('name') or f'{source.stem}_{flow_index + 1}')
        if name in used_names:
            raise ValueError(f'Duplicate Automate flow name: {name}')
        used_names.add(name)
        blocks = flow['blocks']; steps, warnings = [], []
        metadata = {key: value for key, value in flow.items() if key not in {'name', 'app_package', 'blocks'}}
        if 'flows' in data:
            metadata.update({key: value for key, value in data.items() if key != 'flows'})
        if metadata:
            reason = 'Automate export metadata requires manual review'
            steps.append(_todo(metadata, reason)); warnings.append(reason)
        for index, block in enumerate(blocks):
            step = _automate_step(block, app)
            # Preserve graph edges as TODOs unless they match the literal sequence.
            if isinstance(block, dict) and 'next' in block:
                following = blocks[index + 1].get('id') if index + 1 < len(blocks) and isinstance(blocks[index + 1], dict) else None
                if block['next'] != following:
                    step = None
            if step is None:
                reason = f'Automate block {index}: unsupported block, options, or non-linear edge'
                step = _todo(block, reason); warnings.append(reason)
            steps.append(step)
        if not steps:
            steps.append(_todo([], 'Empty Automate block list')); warnings.append('Empty Automate block list')
        if 'app_package' not in flow:
            warnings.append('Automate app_package missing; replace com.example.app fingerprint')
        result.append(ImportedFlow(name, app, steps, warnings))
    return result


def render_skill(raw: dict) -> str:
    """Emit real YAML comments beside every untranslated source node."""
    text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith('import_unmapped:'):
            lines.append(' ' * (len(line) - len(line.lstrip())) + '# TODO: translate this source node before replaying the skill.')
        lines.append(line)
    return '\n'.join(lines) + '\n'
