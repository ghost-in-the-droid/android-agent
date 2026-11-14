"""Fossify Calculator helpers: the unit converter action and the end-state validators.

calculate, read_result and get_history are YAML-only (for_each + read_text) since v1.0.2.

python_action signature: (device, params, context) -> dict
validator signature:     (device, context) -> bool
The app evaluates immediately, left to right (no operator precedence):
"84-2*6" is (84-2)*6 = 492. `expected_value` mirrors that.
"""

from __future__ import annotations

import operator
import re
import time
from html import unescape

_ID = "org.fossify.math:id/"
_KEYS = {
    "+": "btn_plus",
    "-": "btn_minus",
    "*": "btn_multiply",
    "x": "btn_multiply",
    "×": "btn_multiply",
    "/": "btn_divide",
    "÷": "btn_divide",
    "^": "btn_power",
    "%": "btn_percent",
    ".": "btn_decimal",
    "=": "btn_equals",
    "C": "btn_clear",
    "±": "btn_plus_minus",
}
_KEYS.update({str(d): f"btn_{d}" for d in range(10)})
_TOKEN = re.compile(r"\s*(\d+(?:\.\d+)?|[-+*/x×÷^])\s*")


def visible_nodes(device) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, bounds, checked."""
    out: list[dict] = []
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    if tree:
        stack = list(tree) if isinstance(tree, list) else [tree]
        while stack:
            n = stack.pop()
            b = n.get("boundsInScreen") or {}
            box = (b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0))
            if box[2] > box[0] and box[3] > box[1] and box[0] >= 0:
                out.append(
                    {
                        "text": n.get("text") or "",
                        "desc": n.get("contentDescription") or "",
                        "id": n.get("resourceId") or "",
                        "bounds": box,
                        "checked": bool(n.get("isChecked")),
                    }
                )
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append(
                {
                    "text": unescape(a.get("text", "")),
                    "desc": a.get("content-desc", ""),
                    "id": a.get("resource-id", ""),
                    "bounds": tuple(nums),
                    "checked": a.get("checked") == "true",
                }
            )
    return out


def _by_id(nodes, name):
    return [n for n in nodes if n["id"] == _ID + name]


def _tap_node(device, node):
    left, top, right, bottom = node["bounds"]
    device.tap((left + right) // 2, (top + bottom) // 2, 0.15)


def _press(device, keys: str, nodes=None):
    nodes = nodes or visible_nodes(device)
    pos = {n["id"][len(_ID) :]: n for n in nodes if n["id"].startswith(_ID + "btn_")}
    for ch in keys:
        if ch == " ":
            continue
        key = _KEYS.get(ch)
        if key not in pos:
            raise ValueError(f"no button for {ch!r} on this screen")
        _tap_node(device, pos[key])


def parse_number(text: str) -> float | None:
    t = (text or "").replace(",", "").replace("−", "-").strip()
    try:
        return float(t)
    except ValueError:
        return None


def expected_value(expression: str) -> float:
    """Left-to-right evaluation, as the app does."""
    tokens = [m.group(1) for m in _TOKEN.finditer(expression)]
    if not tokens or "".join(tokens) != re.sub(r"\s", "", expression):
        raise ValueError(f"unsupported expression {expression!r}: numbers and + - * / ^ only")
    acc = float(tokens[0])
    for op, num in zip(tokens[1::2], tokens[2::2]):
        b = float(num)
        acc = {
            "+": operator.add,
            "-": operator.sub,
            "*": operator.mul,
            "x": operator.mul,
            "×": operator.mul,
            "/": operator.truediv,
            "÷": operator.truediv,
            "^": operator.pow,
        }[op](acc, b)
    return acc


def _pick_unit(device, holder: str, unit: str):
    name = _by_id(visible_nodes(device), holder)
    if not name:
        raise ValueError(f"{holder} not on screen")
    _tap_node(device, name[0])
    time.sleep(0.8)
    want = unit.strip().lower()
    for attempt in range(6):
        nodes = visible_nodes(device)
        # Popup rows can have android:id/text1 on OEM builds. Never select the
        # converter's own label as if it were a popup option.
        options = [n for n in nodes if n["text"] and not n["id"].startswith(_ID)]
        hit = next((o for o in options if o["text"].lower() == want or o["text"].lower().startswith(want + " (")), None)
        if hit is not None:
            _tap_node(device, hit)
            time.sleep(0.6)
            return
        if attempt == 2:
            # The initial tap may race the converter transition. Retap only
            # while its holder is visible and no unit menu has appeared.
            holders = _by_id(nodes, holder)
            if holders and len(options) <= 1:
                _tap_node(device, holders[0])
        time.sleep(0.4)
    raise ValueError(f"unit {unit!r} not offered; options: {[o['text'] for o in options]}")


def convert_units(device, params, context):
    """Runs on the converter screen of the chosen category (the YAML steps open it)."""
    _pick_unit(device, "top_unit_name", str(params["from_unit"]))
    _pick_unit(device, "bottom_unit_name", str(params["to_unit"]))
    nodes = visible_nodes(device)
    clear = _by_id(nodes, "btn_clear")[0]
    left, top, right, bottom = clear["bounds"]
    device.long_press((left + right) // 2, (top + bottom) // 2, 800, 0.3)
    value = str(params["value"]).strip()
    negative = value.startswith("-")
    _press(device, value.lstrip("-"), nodes)
    if negative:
        _press(device, "±", nodes)
    time.sleep(0.5)
    nodes = visible_nodes(device)
    out = {
        k: next((n["text"] for n in _by_id(nodes, k)), "")
        for k in ("top_unit_name", "top_unit_text", "bottom_unit_name", "bottom_unit_text", "bottom_unit_symbol")
    }
    return {
        "success": True,
        "data": {
            "from_unit": out["top_unit_name"],
            "input": parse_number(out["top_unit_text"]),
            "to_unit": out["bottom_unit_name"],
            "value": parse_number(out["bottom_unit_text"]),
            "symbol": out["bottom_unit_symbol"],
        },
    }


# ── End-state validators: (device, context) -> bool ──────────────────────────


def result_matches(device, context) -> bool:
    want = expected_value(str(context.params["expression"]))
    shown = parse_number(next((n["text"] for n in _by_id(visible_nodes(device), "result")), ""))
    return shown is not None and abs(shown - want) <= max(1e-6, abs(want) * 1e-6)


def result_readable(device, context) -> bool:
    display = next((n["text"] for n in _by_id(visible_nodes(device), "result")), "")
    value = parse_number(display)
    return value is not None and value == context.result.get("value") and display == context.result.get("display")


def history_read(device, context) -> bool:
    nodes = visible_nodes(device)
    if not any(n["id"] == _ID + "alertTitle" and n["text"] == "History" for n in nodes):
        return False
    formulas, results = context.result.get("formulas"), context.result.get("results")
    return (
        isinstance(formulas, list)
        and isinstance(results, list)
        and len(formulas) == len(results)
        and formulas == [n["text"] for n in _by_id(nodes, "item_formula")]
        and results == [n["text"] for n in _by_id(nodes, "item_result")]
    )


def conversion_done(device, context) -> bool:
    r = context.result
    nodes = visible_nodes(device)
    values = {
        key: next((n["text"] for n in _by_id(nodes, key)), "")
        for key in ("top_unit_name", "top_unit_text", "bottom_unit_name", "bottom_unit_text", "bottom_unit_symbol")
    }
    return (
        r.get("value") is not None
        and r.get("value") == parse_number(values["bottom_unit_text"])
        and r.get("input") == parse_number(values["top_unit_text"])
        and r.get("from_unit") == values["top_unit_name"]
        and r.get("to_unit") == values["bottom_unit_name"]
        and r.get("symbol") == values["bottom_unit_symbol"]
        and r.get("input") == parse_number(str(context.params["value"]))
        and str(context.params["from_unit"]).lower() in r.get("from_unit", "").lower()
        and str(context.params["to_unit"]).lower() in r.get("to_unit", "").lower()
    )
