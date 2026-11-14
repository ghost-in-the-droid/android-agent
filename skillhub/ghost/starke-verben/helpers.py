"""starke-verben helpers (Starke Verben, org.sw24softwares.starkeverben): German strong verbs, offline.

Tabs: Lesson (one verb with all forms, tapping the tab again shows another), Test (a form with one field filled,
VERIFY shows the correct forms), List (all verbs, expandable, searchable). adb can only type ASCII, so umlauts
(for example in faehrt) cannot be typed into the test fields.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "org.sw24softwares.starkeverben"
_FIELDS = {"infinitive": "Infinitive", "preterite": "Preterite", "participle": "Participle",
           "third_person": "3rd Person", "translation": "Translation"}
_IDS = {"infinitive": "infinitive", "preterite": "preterite", "participle": "participe",
        "third_person": "third_person", "translation": "traduction"}


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "id": a.get("resource-id", "").split("/")[-1],
                        "checked": a.get("checked") == "true", "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _txt(nodes, ident) -> str:
    n = _by(nodes, ident)
    return n["text"] if n else ""


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _by(nodes, "infinitif_single_lesson"):
        return {"screen": "lesson", "infinitive": _txt(nodes, "infinitif_single_lesson"), "preterite": _txt(nodes, "preterit_single_lesson"),
                "auxiliary": _txt(nodes, "auxiliary_single_lesson"), "participle": _txt(nodes, "participe_single_lesson"),
                "third_person": _txt(nodes, "troisieme_personne_single_lesson"), "translation": _txt(nodes, "traduction_single_lesson")}
    if _by(nodes, "verify"):
        fields = {k: _by(nodes, i) for k, i in _IDS.items()}
        given = {k: n["text"] for k, n in fields.items() if n and n["text"] != _FIELDS[k]}
        return {"screen": "test", "given": given, "empty": [k for k in _FIELDS if k not in given]}
    if _by(nodes, "participle_result"):
        return {"screen": "test_result", "infinitive": _txt(nodes, "infinitive_result"), "preterite": _txt(nodes, "preterit_result"),
                "auxiliary": _txt(nodes, "auxiliary_result"), "participle": _txt(nodes, "participle_result"),
                "third_person": _txt(nodes, "third_person_result"), "translation": _txt(nodes, "translation_result")}
    if _by(nodes, "search_src_text"):
        return {"screen": "list"}
    if _by(nodes, "fab") and any(n["text"] == "CHART" for n in nodes):
        return {"screen": "test_tab"}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] in (want if isinstance(want, tuple) else (want,)):
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _tab(device, ident):
    device.tap(*_centre(_by(_nodes(device), ident)), delay=1.4)


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_verbs(device, params, context):
    return {"state": _wait(device, "lesson")}


def get_lesson(device, params, context):
    return {"state": _wait(device, "lesson")}


def next_lesson(device, params, context):
    before = _wait(device, "lesson")["infinitive"]
    for _ in range(6):
        _tab(device, "single_lesson")
        st = _wait(device, "lesson")
        if st["infinitive"] != before:
            return {"previous": before, "state": st}
    raise RuntimeError("the lesson did not change")


def get_verb(device, params, context):
    verb = str(params.get("verb", "")).strip().lower()
    if not re.fullmatch(r"[a-z]{2,20}", verb):
        raise RuntimeError("verb must be 2 to 20 plain letters (infinitive, for example essen)")
    _wait(device, ("lesson", "test_tab", "list", "test", "test_result"))
    if read_state(device)["screen"] not in ("lesson", "test_tab", "list"):
        raise RuntimeError("finish the test first")
    _tab(device, "lesson")
    _wait(device, "list")
    nodes = _nodes(device)
    device.tap(*_centre(_by(nodes, "search_src_text")), delay=0.6)
    device.adb("shell", "input", "keycombination", "KEYCODE_CTRL_LEFT", "KEYCODE_A")
    device.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    device.adb("shell", "input", "text", input_text_arg(verb))
    time.sleep(0.6)
    device.adb("shell", "input", "keyevent", "KEYCODE_ENTER")  # the list filters on submit
    time.sleep(1.5)
    nodes = _nodes(device)
    head = next((n for n in nodes if n["id"] == "lesson_expandable_group_text" and n["text"].lower() == verb), None)
    if not head:
        names = [n["text"] for n in nodes if n["id"] == "lesson_expandable_group_text"]
        raise RuntimeError(f"verb not found: {verb}; matches: {names[:8]}")
    if not any(n["id"] == "lesson_expandable_item_text" for n in nodes):
        device.tap(*_centre(head), delay=1.2)
        nodes = _nodes(device)
    forms = {}
    for n in nodes:
        if n["id"] == "lesson_expandable_item_text" and " : " in n["text"]:
            k, _, v = n["text"].partition(" : ")
            key = k.strip().lower().replace(" ", "_")
            forms["third_person" if key == "3rd_person" else key] = v.strip()
    if not forms:
        raise RuntimeError("the verb forms did not open")
    return {"verb": verb, "forms": forms}


def start_test(device, params, context):
    _wait(device, ("lesson", "test_tab", "list"))
    _tab(device, "progression")
    _wait(device, "test_tab")
    device.tap(*_centre(_by(_nodes(device), "fab")), delay=1.8)
    return {"state": _wait(device, "test")}


def get_test(device, params, context):
    return {"state": _wait(device, "test")}


def answer_test(device, params, context):
    st = _wait(device, "test")
    typed = {}
    for key, ident in _IDS.items():
        val = str(params.get(key, "")).strip()
        if not val or key in st["given"]:
            continue
        if not re.fullmatch(r"[A-Za-z ,'\-]{1,40}", val):
            raise RuntimeError(f"{key}: only plain ASCII letters can be typed (no umlauts or ss), got {val!r}")
        node = _by(_nodes(device), ident)
        device.tap(*_centre(node), delay=0.5)
        device.adb("shell", "input", "text", input_text_arg(val))
        time.sleep(0.4)
        typed[key] = val
    aux = str(params.get("auxiliary", "")).strip().lower()
    if aux in ("sein", "haben"):
        box = _by(_nodes(device), "auxiliary")
        if box and box["checked"] != (aux == "sein"):
            device.tap(*_centre(box), delay=0.5)
    verify = _by(_nodes(device), "verify")
    if not verify:  # the keyboard can push the button off screen layout; re-dump after a short wait
        time.sleep(0.8)
        verify = _by(_nodes(device), "verify")
    device.tap(*_centre(verify), delay=1.8)
    res = _wait(device, "test_result")
    correct = {}
    for key, val in typed.items():
        want = res[key].lower()
        correct[key] = val.lower() == want or (key == "translation" and val.lower() in want)
    if aux in ("sein", "haben"):
        correct["auxiliary"] = (aux == "sein") == (res["auxiliary"].lower() == "ist")
    return {"given": st["given"], "typed": typed, "correct": correct, "answers": {k: v for k, v in res.items() if k != "screen"}}


def finish_test(device, params, context):
    res = _wait(device, "test_result")
    device.tap(*_centre(_by(_nodes(device), "finish")), delay=1.6)
    no = _by(_nodes(device), "button2")
    if no:
        device.tap(*_centre(no), delay=1.4)
    return {"state": _wait(device, ("test_tab", "lesson", "list"))}


def seed_test(device, params, context):
    """Pre-step: make sure a test question is on screen."""
    st = read_state(device)["screen"]
    if st == "test":
        return {}
    if st == "test_result":
        finish_test(device, params, context)
    start_test(device, params, context)
    return {}


def seed_result(device, params, context):
    """Pre-step: end on the test result screen."""
    if read_state(device)["screen"] != "test_result":
        seed_test(device, params, context)
        answer_test(device, {"preterite": "x"}, context)
    return {}


# ── validators ──────────────────────────────────────────────────────────────

def lesson_open(device, context) -> bool:
    return read_state(device).get("screen") == "lesson"


def lesson_changed(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "lesson" and s["infinitive"] == r["state"]["infinitive"] and s["infinitive"] != r["previous"]


def lesson_read(device, context) -> bool:
    s = read_state(device)
    return s.get("screen") == "lesson" and s["infinitive"] == context.result["state"]["infinitive"]


def verb_read(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "list" and r["forms"].get("infinitive", "") == r["verb"] and bool(r["forms"].get("preterite"))


def test_started(device, context) -> bool:
    return read_state(device).get("screen") == "test"


def test_answered(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "test_result" and bool(r["answers"].get("participle")) and set(r["typed"]) <= set(r["correct"])


def test_finished(device, context) -> bool:
    return read_state(device).get("screen") in ("test_tab", "lesson", "list")
