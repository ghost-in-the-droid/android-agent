"""geological-timescale helpers (Geological Time Scale, org.tengel.timescale): the geological time scale as a table, offline.

One screen: a coloured table (Eonothem, Erathem, then Period, Epoch, Age as you zoom in) with the start of each unit in
million years ago. The toolbar has zoom minus and zoom plus. Parent cells span several rows, so a row is the age column
entry plus every name cell whose vertical range contains it.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "org.tengel.timescale"
_AGE_X = 515


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"id": a.get("resource-id", "").split("/")[-1], "text": html.unescape(a.get("text", "")).strip(),
                        "desc": html.unescape(a.get("content-desc", "")), "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if not any(n["id"] == "option_zoom_plus" for n in nodes):
        return {"screen": "other"}
    cells = [n for n in nodes if n["text"] and n["bounds"][1] > 230 and not n["id"]]
    ages = sorted((n for n in cells if n["bounds"][0] >= _AGE_X and n["text"] != "*"), key=lambda n: (n["bounds"][1], n["bounds"][0]))
    rows = []
    for n in ages:
        cy = (n["bounds"][1] + n["bounds"][3]) // 2
        if rows and abs(rows[-1]["cy"] - cy) <= 18:
            rows[-1]["pieces"].append(n["text"])
        else:
            rows.append({"cy": cy, "pieces": [n["text"]]})
    out = []
    for r in rows:
        text = "".join(r["pieces"])
        m = re.match(r"^(\d+(?:\.\d+)?)(?:±(\d+(?:\.\d+)?))?$", text)
        names = [n["text"] for n in sorted(cells, key=lambda n: n["bounds"][0]) if n["bounds"][2] <= _AGE_X + 4 and n["bounds"][1] <= r["cy"] <= n["bounds"][3] and re.search(r"[A-Za-z]{2}", n["text"])]
        out.append({"names": names, "unit": names[-1] if names else "", "start_mya": float(m.group(1)) if m else None, "uncertainty_mya": float(m.group(2)) if m and m.group(2) else None})
    header = [n["text"] for n in sorted((n for n in nodes if n["text"] and 140 < n["bounds"][1] < 235), key=lambda n: n["bounds"][0]) if n["text"] not in ("m", "ya")]
    return {"screen": "table", "columns": header, "rows": out}


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == "table" and st["rows"]:
            return st
        time.sleep(0.7)
    raise RuntimeError("the time scale table is not on screen")


def _zoom(device, ident):
    before = _wait(device)
    n = next(n for n in _nodes(device) if n["id"] == ident)
    device.tap(*_centre(n), delay=1.3)
    after = _wait(device)
    after["changed"] = after["rows"] != before["rows"]
    return after


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_timescale(device, params, context):
    return {"state": _wait(device)}


def get_scale(device, params, context):
    return {"state": _wait(device)}


def zoom_in(device, params, context):
    return {"state": _zoom(device, "option_zoom_plus")}


def zoom_out(device, params, context):
    return {"state": _zoom(device, "option_zoom_minus")}


def seed_zoomed(device, params, context):
    """Pre-step: zoom in once so zoom_out has something to undo."""
    if len(_wait(device)["columns"]) <= 2:
        _zoom(device, "option_zoom_plus")
    return {}


def lookup_unit(device, params, context):
    name = str(params.get("name", "")).strip().lower()
    if not name:
        raise RuntimeError("name must be a unit such as Jurassic or Cambrian")
    for _ in range(5):
        st = _wait(device)
        for i, r in enumerate(st["rows"]):
            if any(x.lower() == name for x in r["names"]):
                prev = st["rows"][i - 1]["start_mya"] if i > 0 else 0.0
                return {"unit": next(x for x in r["names"] if x.lower() == name), "hierarchy": r["names"], "start_mya": r["start_mya"], "uncertainty_mya": r["uncertainty_mya"],
                        "end_mya": prev, "columns": st["columns"]}
        nxt = _zoom(device, "option_zoom_plus")
        if not nxt["changed"]:
            break
    raise RuntimeError(f"unit {params.get('name')} not found at any zoom level")


# ── validators ──────────────────────────────────────────────────────────────

def table_open(device, context) -> bool:
    return read_state(device)["screen"] == "table"


def scale_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "table" and s["rows"] == context.result["state"]["rows"]


def zoomed(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "table" and s["rows"] == context.result["state"]["rows"]


def unit_found(device, context) -> bool:
    r = context.result
    return read_state(device)["screen"] == "table" and r["start_mya"] is not None
