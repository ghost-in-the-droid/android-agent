"""Invocation-local secret handling for the declarative beta runner.

This is an engine output boundary, not a sandbox for arbitrary Python helpers.
Secret-bearing invocations therefore refuse helpers, shell steps and visual capture.
"""

import html
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import quote

from .errors import ParamError

_secrets = ContextVar("skill_secrets", default=None)


def sensitive():
    return _secrets.get() is not None


def redact(value):
    if isinstance(value, str):
        variants = {
            form
            for secret in (_secrets.get() or ())
            for form in (secret, repr(secret)[1:-1], json.dumps(secret)[1:-1], html.escape(secret), quote(secret))
            if form
        }
        for secret in sorted(variants, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {redact(k): redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


@contextmanager
def secret_scope(values, enabled):
    inherited = _secrets.get()
    token = _secrets.set(
        tuple(set(inherited or ()) | {str(v) for v in values if v not in (None, "")})
        if enabled or inherited is not None
        else None
    )
    try:
        yield
    finally:
        _secrets.reset(token)


# A factory runs before *every* logging handler, including caller-installed ones.
# ContextVar isolation leaves concurrent ordinary runs' logging intact.
_record_factory = logging.getLogRecordFactory()


def _private_record(*args, **kwargs):
    record = _record_factory(*args, **kwargs)
    if sensitive():
        record.msg, record.args = "Secret-bearing skill: diagnostic details withheld", ()
        record.exc_info = record.exc_text = record.stack_info = None
    return record


logging.setLogRecordFactory(_private_record)


def dump_xml(device):
    """Sensitive UI stays in memory; never fall back to a file on /sdcard."""
    if not sensitive() or getattr(device, "is_fake", False):
        return device.dump_xml()
    portal = getattr(device, "dump_portal_xml", None)
    xml = portal() if callable(portal) else None
    if not xml:
        raise ParamError("Secret-bearing actions require the in-memory Portal UI reader")
    return xml


def guard_step(step):
    if not sensitive():
        return
    if step.get("action") == "read_text" and step.get("parse"):
        raise ParamError("Secret-bearing actions cannot transform UI text into numbers")
    structural = {"if_visible", "retry", "subroutine", "checkpoint", "ask", "pre_hooks", "for_each"}
    atomic = {
        "tap",
        "tap_element",
        "type_text",
        "long_press",
        "swipe",
        "press_key",
        "launch_app",
        "open_url",
        "sleep",
        "wait_for_text",
        "wait_for_element",
        "read_text",
        "tap_nth",
    }
    if "python_action" in step or "run_skill" in step or not (set(step) & structural or step.get("action") in atomic):
        raise ParamError("Secret-bearing actions support declarative UI steps and HITL only; capture/helpers disabled")


def guard_validator(spec):
    if not sensitive():
        return
    if isinstance(spec, list):
        for sub in spec:
            guard_validator(sub)
    elif isinstance(spec, dict):
        for key in ("all_of", "any_of", "not"):
            if key in spec:
                return guard_validator(spec[key])
        if spec.get("kind") not in {"text_visible", "element_present", "url_contains"}:
            raise ParamError("Secret-bearing actions require an in-memory selector validator")
    else:
        raise ParamError("Secret-bearing action has an invalid validator")
