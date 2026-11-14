"""gpa-calculator helpers (GPA Calculator, com.gpa.calculator.gpa_calculator): courses with credit and grade, semester GPA.

Everything is readable: the course rows (name field, Credit and Grade buttons), the UG/MBA scheme radios and the result screen.
Credit and Grade open dropdown menus whose options are buttons with their own text.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "com.gpa.calculator.gpa_calculator"
_GRADES = {"A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F"}


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")), "cls": a.get("class", ""), "bounds": tuple(nums),
                        "checked": a.get("checked") == "true"})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _is_form(nodes) -> bool:
    return any(n["text"] == "Add Course" for n in nodes)


def read_form(device) -> dict:
    nodes = _nodes(device)
    if not _is_form(nodes):
        return {"on_form": False}
    edits = sorted((n for n in nodes if n["cls"].endswith("EditText")), key=lambda n: n["bounds"][1])
    credits = sorted((n for n in nodes if n["cls"].endswith("Button") and n["text"].startswith("Credit")), key=lambda n: n["bounds"][1])
    grades = sorted((n for n in nodes if n["cls"].endswith("Button") and n["text"].startswith("Grade")), key=lambda n: n["bounds"][1])
    rows = []
    for e, c, g in zip(edits, credits, grades):
        rows.append({"name": e["text"], "credit": c["text"].replace("Credit", "").strip(), "grade": g["text"].replace("Grade", "").strip()})
    scheme = next((n["text"] for n in nodes if n["cls"].endswith("RadioButton") and n["checked"]), "")
    points = next((n["text"] for n in nodes if re.fullmatch(r"\d+\.\d\d", n["text"]) and n["bounds"][1] < 330), "")
    return {"on_form": True, "scheme": scheme, "rows": rows, "total_points": points,
            "complete_rows": [r for r in rows if r["credit"] and r["grade"]]}


def _pick(device, button, value):
    device.tap(*_centre(button), delay=0.8)
    opt = next((n for n in _nodes(device) if n["cls"].endswith("Button") and n["text"] == value), None)
    if not opt:
        raise RuntimeError(f"option {value!r} not offered")
    device.tap(*_centre(opt), delay=0.8)


def _to_form(device):
    for _ in range(3):
        if _is_form(_nodes(device)):
            return
        device.back()
        time.sleep(0.8)
    raise RuntimeError("could not reach the course form")


# ── python_action targets ───────────────────────────────────────────────────

def go_form(device, params, context):
    _to_form(device)
    return {}


def set_scheme(device, params, context):
    want = str(params["scheme"]).strip().upper()
    if want not in ("UG", "MBA"):
        raise RuntimeError("scheme must be UG or MBA")
    n = next((n for n in _nodes(device) if n["cls"].endswith("RadioButton") and n["text"] == want), None)
    if not n:
        raise RuntimeError("scheme radios not on screen")
    device.tap(*_centre(n), delay=0.8)
    return {"scheme": want, "form": read_form(device)}


def add_course(device, params, context):
    credit, grade = str(params["credit"]).strip(), str(params["grade"]).strip().upper()
    name = str(params.get("name", "")).strip()
    if grade not in _GRADES:
        raise RuntimeError(f"grade must be one of {sorted(_GRADES)}")
    before = read_form(device)
    nodes = _nodes(device)
    edits = sorted((n for n in nodes if n["cls"].endswith("EditText")), key=lambda n: n["bounds"][1])
    credit_b = sorted((n for n in nodes if n["cls"].endswith("Button") and n["text"].startswith("Credit")), key=lambda n: n["bounds"][1])
    if not edits or not credit_b:
        raise RuntimeError("course form not on screen")
    if name:
        if not name.isascii():
            raise RuntimeError("course name must be ASCII")
        device.tap(*_centre(edits[-1]), delay=0.4)
        device.adb("shell", "input", "text", input_text_arg(name))
        device.back()
        time.sleep(0.6)
    _pick(device, sorted((n for n in _nodes(device) if n["cls"].endswith("Button") and n["text"].startswith("Credit")), key=lambda n: n["bounds"][1])[-1], credit)
    _pick(device, sorted((n for n in _nodes(device) if n["cls"].endswith("Button") and n["text"].startswith("Grade")), key=lambda n: n["bounds"][1])[-1], grade)
    add = next((n for n in _nodes(device) if n["cls"].endswith("Button") and n["bounds"][1] > edits[-1]["bounds"][1] + 100
                and n["bounds"][3] - n["bounds"][1] > 100 and n["text"] == ""), None)
    if not add:
        raise RuntimeError("Add Course button not found")
    device.tap(*_centre(add), delay=1.2)
    return {"before": before, "form": read_form(device), "added": {"name": name, "credit": credit, "grade": grade}}


def get_courses(device, params, context):
    return {"form": read_form(device)}


def calculate(device, params, context):
    before = read_form(device)
    btn = next((n for n in _nodes(device) if n["text"] == "Calculate"), None)
    if not btn:
        raise RuntimeError("Calculate button not on screen")
    device.tap(*_centre(btn), delay=1.5)
    nodes = _nodes(device)
    gpa = ""
    for i, n in enumerate(nodes):
        if n["text"].startswith("Current semester GPA"):
            gpa = next((m["text"] for m in nodes if re.fullmatch(r"\d+\.\d\d", m["text"])), "")
    if not gpa:
        raise RuntimeError("no GPA result shown (add at least one complete course)")
    device.back()
    time.sleep(0.8)
    return {"gpa": gpa, "courses": len(before["complete_rows"]), "scheme": before["scheme"]}


def clear_courses(device, params, context):
    if str(params.get("confirm", "")).lower() not in ("yes", "true", "1"):
        raise RuntimeError("clear_courses removes all courses: pass confirm=yes")
    btn = next((n for n in _nodes(device) if n["text"] == "Clear Courses"), None)
    if not btn:
        raise RuntimeError("Clear Courses button not on screen")
    device.tap(*_centre(btn), delay=1.0)
    ok = next((n for n in _nodes(device) if n["cls"].endswith("Button") and n["text"] == "Reset"), None)
    if ok:  # the app asks "Are you sure?"; the caller already passed confirm=yes
        device.tap(*_centre(ok), delay=1.0)
    return {"form": read_form(device)}


# ── validators ──────────────────────────────────────────────────────────────

def form_ready(device, context) -> bool:
    return read_form(device)["on_form"]


def scheme_set(device, context) -> bool:
    return read_form(device).get("scheme") == context.result["scheme"]


def course_added(device, context) -> bool:
    r = context.result
    now = read_form(device)
    return now["on_form"] and len(now["complete_rows"]) == len(r["before"]["complete_rows"]) + 1


def courses_read(device, context) -> bool:
    return read_form(device)["rows"] == context.result["form"]["rows"]


def gpa_shown(device, context) -> bool:
    return bool(re.fullmatch(r"\d+\.\d\d", context.result["gpa"])) and read_form(device)["on_form"]


def cleared(device, context) -> bool:
    now = read_form(device)
    return now["on_form"] and not now["complete_rows"]
