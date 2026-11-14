"""Placeholder resolution: `{param_name}` and `{context.attr}` in yaml string values.

Called by the dispatcher before invoking each step handler — every string field in
the step dict is resolved through here. Non-string values pass through unchanged.

Supported syntax:
    "hello {name}"                  → "hello alice"     (from params["name"])
    "{context.media_id}"            → "42"              (from ctx.media_id)
    "{name | capitalize}"           → "Alice"           (pipe filter — v0: capitalize, lower, upper, strip)
    "{tags | join:,}"               → "a,b,c"           (join list)
    "escaped: {{literal}}"          → "escaped: {literal}"  (double-brace escape)

Missing placeholder → InterpolationError with hint listing available names.
"""

from __future__ import annotations

import re
from typing import Any

from gitd.skills.engine.context import RunContext
from gitd.skills.engine.errors import InterpolationError

# Match {name}, {name.attr}, {name.attr | filter}, {name.attr | filter:arg}
_PLACEHOLDER = re.compile(
    r"\{\{|"  # {{ escape (matched but preserved)
    r"\}\}|"  # }} escape
    r"\{"
    r"\s*([a-zA-Z_][a-zA-Z0-9_.]*)"  # 1: name or context.attr
    r"(?:\s*\|\s*([a-z_]+)"  # 2: filter name (optional)
    r"(?::([^}]*))?)?"  # 3: filter arg after ':'
    r"\s*\}"
)


def interpolate(value: Any, context: RunContext) -> Any:
    """Resolve placeholders in `value`. Recurses into dicts + lists.

    - str: interpolate placeholders (see grammar above)
    - dict: interpolate every value
    - list: interpolate every element
    - anything else: return as-is
    """
    if isinstance(value, str):
        return _interpolate_str(value, context)
    if isinstance(value, dict):
        return {k: interpolate(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, context) for v in value]
    return value


def _interpolate_str(s: str, ctx: RunContext) -> str:
    """Resolve one string's placeholders. Returns str; may be different type
    if the WHOLE string is a single {...} whose resolved value is non-str.
    """
    # Fast path: no braces at all
    if "{" not in s and "}" not in s:
        return s

    # Special case: string is exactly ONE placeholder → return the RAW value type
    m = _PLACEHOLDER.fullmatch(s)
    if m and m.group(1):  # single placeholder (not escape)
        return _resolve(m.group(1), m.group(2), m.group(3), ctx, s)

    # General case: string-substitution mode (always coerce to str)
    def repl(m):
        if m.group(0) == "{{":
            return "{"
        if m.group(0) == "}}":
            return "}"
        val = _resolve(m.group(1), m.group(2), m.group(3), ctx, s)
        return str(val)

    return _PLACEHOLDER.sub(repl, s)


def _resolve(name: str, filter_name: str | None, filter_arg: str | None, ctx: RunContext, source: str) -> Any:
    """Resolve `name` → value from ctx.params or ctx.<extras>, apply filter."""
    if name.startswith("context."):
        attr = name[len("context.") :]
        # Look in extras (media_id, etc.) or result
        if attr in ctx.extras:
            val = ctx.extras[attr]
        elif attr in ctx.result:
            val = ctx.result[attr]
        else:
            raise InterpolationError(
                f"Unresolved context.{attr!r} in {source!r}",
                hint=f"Available context attrs: {sorted(list(ctx.extras.keys()) + list(ctx.result.keys())) or '(none)'}. "
                f"Set via `context.{attr} = value` in an earlier python_action.",
            )
    else:
        if name not in ctx.params:
            raise InterpolationError(
                f"Unresolved parameter {name!r} in {source!r}",
                hint=f"Available params: {sorted(ctx.params.keys()) or '(none)'}. "
                f"Did you forget to declare it in the action's `params:` block?",
            )
        val = ctx.params[name]

    if filter_name:
        from . import privacy

        if privacy.sensitive() and privacy.redact(val) != val:
            raise InterpolationError("Secret values cannot be transformed by interpolation filters")
        val = _apply_filter(val, filter_name, filter_arg)
    return val


_FILTERS = {
    "capitalize": lambda v, _arg: str(v).capitalize(),
    "lower": lambda v, _arg: str(v).lower(),
    "upper": lambda v, _arg: str(v).upper(),
    "strip": lambda v, _arg: str(v).strip(),
    "len": lambda v, _arg: len(v),
    "join": lambda v, arg: (arg or "").join(str(x) for x in v),
    "int": lambda v, _arg: int(v),
    "str": lambda v, _arg: str(v),
}


def _apply_filter(val: Any, name: str, arg: str | None) -> Any:
    fn = _FILTERS.get(name)
    if not fn:
        raise InterpolationError(
            f"Unknown filter |{name}|",
            hint=f"Available filters: {sorted(_FILTERS.keys())}",
        )
    return fn(val, arg)
