"""Typed questions and durable caller handoffs."""

from __future__ import annotations

import json
import time

from . import hitl, privacy
from .errors import AskInvalidAnswerError, AskTimeoutError, SkillError


class NeedsInput(SkillError):
    def __init__(self, spec, attachments):
        super().__init__("Caller answer required")
        self.spec, self.attachments = spec, attachments


def validate_answer(value, schema):
    kind = schema["type"]
    valid = (
        kind == "str"
        and isinstance(value, str)
        or kind == "int"
        and type(value) is int
        or kind == "enum"
        and value in schema["values"]
        or kind == "json"
    )
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise AskInvalidAnswerError("Answer does not match ask schema", payload={"schema": schema})
    return value


def fallback(spec):
    value = spec.get("fallback", "fail")
    if isinstance(value, dict) and "value" in value:
        return validate_answer(value["value"], spec["schema"])
    raise AskTimeoutError("Ask did not receive an answer", payload={"who": spec["who"]})


def record(ctx, spec, answered_by, started):
    item = {k: spec[k] for k in ("who", "prompt", "schema")}
    item.update(answered_by=answered_by, duration_ms=(time.monotonic() - started) * 1000)
    ctx.result.setdefault("asks", []).append(item)
    ctx.extras["_ask_trace"] = item
    ctx.extras["_trace_note"] = "ask: " + answered_by


def attachments(spec, ctx, device):
    if privacy.sensitive():
        return {}
    out = {}
    for part in spec.get("attach", []):
        if part == "a11y":
            out["a11y"] = device.dump_xml().encode("utf-8")[:20480].decode("utf-8", errors="ignore")
        elif part == "screenshot":
            import base64
            import io

            from PIL import Image

            from gitd.services.agent_tools import get_screenshot_b64

            encoded = get_screenshot_b64(ctx.device_serial)
            if not encoded:
                raise AskInvalidAnswerError("Screenshot attachment unavailable")
            png = io.BytesIO()
            Image.open(io.BytesIO(base64.b64decode(encoded))).save(png, format="PNG")
            out["screenshot"] = base64.b64encode(png.getvalue()).decode("ascii")
        elif isinstance(part, dict):
            out["params"] = {k: ctx.params[k] for k in part["params"]}
    return out


def ask(step, ctx, device):
    spec = privacy.redact(step["ask"])
    if privacy.sensitive() and spec["who"] == "sub_agent":
        raise AskInvalidAnswerError("Sub-agent asks are disabled for secret-bearing actions")
    ctx.extras.pop("_ask_trace", None)
    started = time.monotonic()
    answered_by = spec["who"]
    try:
        if ctx.extras.get("_dry_run"):
            answered_by = "dry_run"
            if isinstance(spec.get("fallback"), dict):
                value = fallback(spec)
            else:
                value = {"str": "", "int": 0, "json": None, "enum": (spec["schema"].get("values") or [None])[0]}[
                    spec["schema"]["type"]
                ]
        else:
            attached = attachments(spec, ctx, device)
            if spec["who"] == "parent_agent":
                record(ctx, spec, "pending", started)
                raise NeedsInput(spec, attached)
            if spec["who"] == "sub_agent":
                from .ask_agent import ask_agent

                value = ask_agent.answer(
                    spec["prompt"],
                    attached,
                    spec["schema"],
                    ctx.device_serial,
                    timeout_s=spec.get("timeout_s", 0),
                    max_turns=3,
                )
                if value is NO_ANSWER:
                    answered_by, value = "fallback", fallback(spec)
            else:
                ch = hitl.channel_for(ctx)
                if ch is None:
                    answered_by, value = "fallback", fallback(spec)
                else:
                    ch.set_state("awaiting_human", {"ask": spec, "attachments": attached})
                    ch.notify("ask", spec["prompt"])
                    while True:
                        value = ch.read_answer()
                        if value is not NO_ANSWER:
                            break
                        if ch.read_signal() == "abort":
                            raise AskTimeoutError("Human aborted ask")
                        if spec.get("timeout_s", 0) and time.monotonic() - started >= spec["timeout_s"]:
                            answered_by, value = "fallback", fallback(spec)
                            break
                        time.sleep(0.05)
                    ch.set_state("running", None)
        ctx.extras[spec["store_as"]] = validate_answer(value, spec["schema"])
    finally:
        if (
            not isinstance(ctx.extras.get("_ask_trace"), dict)
            or ctx.extras["_ask_trace"].get("answered_by") != "pending"
        ):
            record(ctx, spec, answered_by, started)


NO_ANSWER = object()
