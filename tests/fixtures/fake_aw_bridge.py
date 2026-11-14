#!/usr/bin/env python3
"""Stand-in for tools/bench/aw_bridge.py: same JSON-lines protocol, no AndroidWorld, no emulator.

Env: FAKE_AW_PARAMS (JSON dict returned by init), FAKE_AW_SCORES (JSON list of floats, one per init in
order; default all 1.0), FAKE_AW_TASKS (comma list for hello). Writes a log of ops to FAKE_AW_LOG.
"""
import json
import os
import sys

params = json.loads(os.environ.get('FAKE_AW_PARAMS') or '{}')
scores = json.loads(os.environ.get('FAKE_AW_SCORES') or '[]')
tasks = [t for t in (os.environ.get('FAKE_AW_TASKS') or 'FakeTask').split(',') if t]
log_path = os.environ.get('FAKE_AW_LOG')
inits = 0
current = None
for line in sys.stdin:
    req = json.loads(line)
    op = req.get('op')
    if log_path:
        with open(log_path, 'a') as log:
            log.write(json.dumps(req) + '\n')
    if op == 'hello':
        reply = {'ok': True, 'serial': 'fake-5554', 'tasks': tasks, 'upstream': 'fake'}
    elif op == 'init':
        if req.get('task') not in tasks:
            reply = {'ok': False, 'error': f"KeyError: unknown task {req.get('task')!r}"}
        else:
            current = req['task']
            reply = {'ok': True, 'task': current, 'goal': f'do {current}', 'instance_seed': 1000 + req.get('seed', 0),
                     'seed': req.get('seed'), 'complexity': 1, 'params': params}
            inits += 1
    elif op == 'score':
        if current is None:
            reply = {'ok': False, 'error': 'RuntimeError: no task initialised'}
        else:
            score = scores[inits - 1] if inits - 1 < len(scores) else 1.0
            reply = {'ok': True, 'is_successful': float(score)}
    elif op == 'teardown':
        current = None
        reply = {'ok': True}
    elif op == 'reset':
        reply = {'ok': True}
    elif op == 'quit':
        print(json.dumps({'ok': True}), flush=True)
        break
    else:
        reply = {'ok': False, 'error': f'KeyError: unknown op {op!r}'}
    print(json.dumps(reply), flush=True)
