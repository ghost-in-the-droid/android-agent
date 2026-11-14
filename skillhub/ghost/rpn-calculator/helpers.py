"""rpn-calculator helpers (RPNcalc, dev.pesic.rpncalc): a reverse Polish notation calculator.

The keypad buttons carry their label as content-desc and the stack lines are content-desc views, so the skill pushes
numbers, applies operators and reads the stack. Operand order is the usual RPN one: `3 4 -` is -1.
"""
from __future__ import annotations

import html
import math
import re
import time

_PKG = "dev.pesic.rpncalc"
_OPS = {"+": "+", "-": "−", "*": "×", "/": "÷", "^": "yˣ", "%": "％", "neg": "±", "swap": "Swap"}


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")), "cls": a.get("class", "").split(".")[-1],
                        "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _keys(nodes) -> dict:
    return {n["text"]: n for n in nodes if n["cls"] == "Button" and n["text"] and n["text"] != "R"}


def read_state(device) -> dict:
    nodes = _nodes(device)
    keys = _keys(nodes)
    if "Enter" not in keys:
        return {"screen": "other"}
    # stack lines are plain views above the keypad; the lowest line is the top of the stack (X register)
    lines = sorted((n for n in nodes if n["cls"] == "View" and n["bounds"][1] < 530 and n["bounds"][1] > 100 and n["text"]),
                   key=lambda n: n["bounds"][1], reverse=True)
    stack = [n["text"] for n in lines]
    return {"screen": "calc", "stack": stack, "top": stack[0] if stack else ""}


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st.get("screen") == "calc":
            return st
        time.sleep(0.8)
    raise RuntimeError("the calculator is not on screen")


def _tap_labels(device, labels):
    keys = _keys(_nodes(device))
    for lab in labels:
        if lab not in keys:
            raise RuntimeError(f"key {lab!r} not on the keypad")
        device.tap(*_centre(keys[lab]), delay=0.25)


def _clear(device):
    """C clears an entry in progress and then becomes AC, which clears the stack."""
    for _ in range(3):
        keys = _keys(_nodes(device))
        lab = "C" if "C" in keys else "AC"
        device.tap(*_centre(keys[lab]), delay=0.5)
        if lab == "AC":
            return


def _op(device, label):
    """Tap an operator and make sure it took: the first tap right after Backspace is sometimes swallowed."""
    before = read_state(device).get("stack")
    for _ in range(3):
        _tap_labels(device, [label])
        time.sleep(0.5)
        if read_state(device).get("stack") != before:
            return
    raise RuntimeError(f"the operator {label!r} did not change the stack (not enough numbers?)")


def _num(text):
    try:
        return float(str(text).replace(",", "").replace(" ", "").replace(" ", "").replace(" ", "").replace("−", "-"))
    except ValueError:
        return None


def _value_keys(value: str):
    v = str(value).strip().replace(",", ".")
    if not re.fullmatch(r"-?(\d+\.?\d*|\.\d+)", v):
        raise RuntimeError(f"{value!r} is not a number like 12, -3.5 or .25")
    neg = v.startswith("-")
    return neg, list(v.lstrip("-"))


def _type(device, value):
    """Type a number into the X register. Enter (a separate step) lifts the stack and leaves a copy of X that the
    next typed number overwrites, which is how an HP style RPN calculator works."""
    neg, chars = _value_keys(value)
    _tap_labels(device, chars)
    if neg:
        _tap_labels(device, ["\u00b1"])


def rpn_eval(tokens):
    st = []
    for t in tokens:
        if t in ("+", "-", "*", "/", "^"):
            b, a = st.pop(), st.pop()
            st.append({"+": a + b, "-": a - b, "*": a * b, "/": a / b if b else math.nan, "^": a ** b}[t])
        elif t == "neg":
            st.append(-st.pop())
        else:
            st.append(float(t))
    return st


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_calc(device, params, context):
    return {"state": _wait(device)}


def clear_all(device, params, context):
    _wait(device)
    _clear(device)
    time.sleep(0.6)
    return {"state": read_state(device)}


def type_number(device, params, context):
    before = _wait(device)
    _type(device, params["value"])
    time.sleep(0.6)
    return {"value": str(params["value"]).strip(), "before": before, "state": read_state(device)}


def enter(device, params, context):
    before = _wait(device)
    _tap_labels(device, ["Enter"])
    time.sleep(0.6)
    return {"before": before, "state": read_state(device)}


def operate(device, params, context):
    op = str(params["op"]).strip().lower()
    op = {"add": "+", "plus": "+", "sub": "-", "minus": "-", "mul": "*", "x": "*", "times": "*", "div": "/", "pow": "^", "negate": "neg",
          "percent": "%", "−": "-", "×": "*", "÷": "/"}.get(op, op)
    if op not in _OPS:
        raise RuntimeError(f"op must be one of {sorted(_OPS)}")
    before = _wait(device)
    if len(before["stack"]) < (1 if op == "neg" else 2):
        raise RuntimeError("not enough numbers on the stack for this operator")
    _op(device, _OPS[op])
    return {"op": op, "before": before, "state": read_state(device)}


def evaluate(device, params, context):
    expr = str(params["expression"]).strip()
    tokens = [t for t in re.split(r"[\s,]+", expr) if t]
    if not tokens:
        raise RuntimeError("expression is empty")
    expected = rpn_eval([t.replace("−", "-") if t not in ("-",) else t for t in tokens])  # raises on a malformed expression
    if not expected:
        raise RuntimeError("expression leaves nothing on the stack")
    _wait(device)
    _clear(device)
    time.sleep(0.5)
    for i, t in enumerate(tokens):
        if t in _OPS:
            _op(device, _OPS[t])
        else:
            _type(device, t)
            if i + 1 < len(tokens) and tokens[i + 1] not in _OPS:
                _tap_labels(device, ["Enter"])  # only between two numbers
    time.sleep(0.8)
    return {"expression": expr, "expected_top": expected[-1], "state": read_state(device)}


def get_stack(device, params, context):
    return {"state": _wait(device)}


# ── validators ──────────────────────────────────────────────────────────────

def calc_open(device, context) -> bool:
    return read_state(device).get("screen") == "calc"


def cleared(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "calc" and all(_num(x) in (0.0, None) for x in s["stack"])


def typed(device, context) -> bool:
    r = context.result
    s = read_state(device)
    want = _num(r["value"].replace(",", "."))
    return s.get("screen") == "calc" and _num(s["top"]) is not None and abs(_num(s["top"]) - want) < 1e-9 * max(1, abs(want))


def entered(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "calc" and len(s["stack"]) == len(r["before"]["stack"]) + 1 and s["top"] == r["before"]["top"]


def operated(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "calc" and s["top"] == r["state"]["top"] and bool(s["top"])


def evaluated(device, context) -> bool:
    r = context.result
    s = read_state(device)
    got = _num(s.get("top", ""))
    return s.get("screen") == "calc" and got is not None and math.isclose(got, r["expected_top"], rel_tol=1e-4, abs_tol=1e-6)


def stack_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "calc" and s["stack"] == context.result["state"]["stack"]
