"""Durable, single-use parent-agent continuation tokens."""

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path

from .ask import fallback, validate_answer


def token_path(token):
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Invalid resume token")
    return Path.home() / ".ghost" / "runs" / (token + ".json")


def persist(skill, action, ctx, trace, pending):
    token = uuid.uuid4().hex
    path = token_path(token)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = {
        "skill_dir": str(skill.skill_dir.resolve()),
        "action": action,
        "yaml_sha256": hashlib.sha256((skill.skill_dir / "skill.yaml").read_bytes()).hexdigest(),
        "params": ctx.params,
        "device_serial": ctx.device_serial,
        "extras": {k: v for k, v in ctx.extras.items() if not k.startswith("_") or k in ("_run_id", "_checkpoints")},
        "result": ctx.result,
        "trace": [t.as_dict() for t in trace],
        "state_attempts": sorted(ctx.extras.get("_state_attempts", [])),
        "next_step": ctx.step_index + 1,
        "spec": pending.spec,
        "created_at": time.time(),
    }
    from . import privacy

    secret_names = {p.name for p in skill.action(action).params if p.secret}
    state = privacy.redact(state)
    state["params"] = {k: v for k, v in state["params"].items() if k not in secret_names}
    state["required_secrets"] = sorted(secret_names)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(state, out)
    return token


def resume_action(token, answer, *, secrets=None):
    from .loader import load_skill
    from .runner import run_action

    path = token_path(token)
    state = json.loads(path.read_text())
    secrets = secrets or {}
    if set(secrets) != set(state.get("required_secrets", [])):
        raise ValueError("Resume requires exactly the original secret params supplied again at runtime")
    state["params"].update(secrets)
    spec = state["spec"]
    elapsed = time.time() - state["created_at"]
    who = "parent_agent"
    if spec.get("timeout_s", 0) and elapsed >= spec["timeout_s"]:
        answer, who = fallback(spec), "fallback"
    value = validate_answer(answer, spec["schema"])
    state["extras"][spec["store_as"]] = value
    item = state["result"]["asks"][-1]
    item.update(answered_by=who, duration_ms=elapsed * 1000)
    state["trace"][-1].update(ask=item, note="ask: " + who, error=None)
    skill = load_skill(state["skill_dir"])
    if hashlib.sha256((skill.skill_dir / "skill.yaml").read_bytes()).hexdigest() != state["yaml_sha256"]:
        raise ValueError("Skill changed since the ask pause")
    # Claim before continuing so the token cannot replay already executed steps.
    claimed = path.with_suffix(".claimed")
    path.rename(claimed)
    try:
        return run_action(skill, state["action"], state["params"], state["device_serial"], _resume_state=state)
    finally:
        claimed.unlink()
