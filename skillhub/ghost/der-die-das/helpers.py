"""der-die-das helpers (Der Die Das, com.machiav3lli.derdiedas): practise German noun genders, offline.

Compose UI with three screens: a menu (Practice / Stats / Settings), the practice screen (a German noun, its English
translation and three answer buttons Der / Die / Das, plus a Pending / Mastered counter) and a stats screen.
A correct answer shows the next noun at once; a wrong answer keeps the same noun on screen.
"""
from __future__ import annotations

import html
import re
import time

_PKG = "com.machiav3lli.derdiedas"
_ARTICLES = ("der", "die", "das")


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "desc": html.unescape(a.get("content-desc", "")),
                        "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _txt(nodes, text):
    return next((n for n in nodes if n["text"] == text), None)


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    texts = [n["text"] for n in nodes]
    if all(t in texts for t in ("Der", "Die", "Das")):
        body = sorted((n for n in nodes if n["text"] and n["cls"] == "TextView" and 400 < n["bounds"][1] < 900), key=lambda n: n["bounds"][1])
        counter = next((n["text"] for n in nodes if n["text"].startswith("Pending:")), "")
        m = re.search(r"Pending:\s*(\d+)\s*\|\s*Mastered:\s*(\d+)", counter)
        return {"screen": "practice", "german": body[0]["text"] if body else "", "english": body[1]["text"] if len(body) > 1 else "",
                "pending": int(m.group(1)) if m else None, "mastered": int(m.group(2)) if m else None}
    if any(t.startswith("Fully learned words") for t in texts):
        m = next((re.fullmatch(r"(\d+)\s*/\s*(\d+)", t) for t in texts if re.fullmatch(r"(\d+)\s*/\s*(\d+)", t)), None)
        return {"screen": "stats", "learned": int(m.group(1)) if m else None, "total": int(m.group(2)) if m else None}
    if all(t in texts for t in ("Practice", "Stats", "Settings")):
        return {"screen": "menu"}
    if "Theme" in texts and "Language" in texts:
        return {"screen": "settings"}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _back(device):
    back = next((n for n in _nodes(device) if n["desc"] == "Back"), None)
    if not back:
        raise RuntimeError("no Back control on this screen")
    device.tap(*_centre(back), delay=1.3)


def _to_menu(device):
    st = read_state(device)["screen"]
    if st == "menu":
        return
    if st == "other":
        raise RuntimeError("the app is not on one of its known screens")
    _back(device)
    _wait(device, "menu")


def _open_tab(device, label, want):
    _to_menu(device)
    device.tap(*_centre(_txt(_nodes(device), label)), delay=1.4)
    return _wait(device, want)


def _article_key(value) -> str:
    a = str(value).strip().lower()
    if a not in _ARTICLES:
        raise RuntimeError("article must be der, die or das")
    return a


def _tap_and_read(device, before: dict, article: str) -> dict:
    btn = _txt(_nodes(device), article.capitalize())
    device.tap(*_centre(btn), delay=0.4)
    after = before
    for _ in range(5):
        time.sleep(0.5)
        after = read_state(device)
        if after["screen"] == "practice" and after["german"] != before["german"]:
            break
    return after


def _answer_one(device, article: str) -> dict:
    before = _wait(device, "practice")
    after = _tap_and_read(device, before, article)
    taps = 1
    if after["screen"] == "practice" and after["german"] == before["german"]:
        # after a wrong answer the app swallows the next right press, so press the same article once more
        after = _tap_and_read(device, before, article)
        taps = 2
    correct = after["screen"] == "practice" and after["german"] != before["german"]
    return {"word": before["german"], "english": before["english"], "chosen": article, "correct": correct, "taps": taps,
            "next_word": after.get("german", ""), "next_english": after.get("english", ""),
            "pending": after.get("pending"), "mastered": after.get("mastered")}


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_practice(device, params, context):
    return {"state": _open_tab(device, "Practice", "practice")}


def seed_practice(device, params, context):
    """Pre-step: make sure the practice screen is on screen."""
    if read_state(device)["screen"] != "practice":
        _open_tab(device, "Practice", "practice")
    return {}


def get_word(device, params, context):
    return {"state": _wait(device, "practice")}


def answer(device, params, context):
    return _answer_one(device, _article_key(params.get("article", "")))


def answer_many(device, params, context):
    arts = [a for a in str(params.get("articles", "")).replace(";", ",").split(",") if a.strip()]
    if not 1 <= len(arts) <= 10:
        raise RuntimeError("articles must list 1 to 10 of der, die, das separated by commas")
    results = [_answer_one(device, _article_key(a)) for a in arts]
    return {"count": len(results), "correct": sum(r["correct"] for r in results), "results": results}


def get_stats(device, params, context):
    return {"state": _open_tab(device, "Stats", "stats")}


# ── validators ──────────────────────────────────────────────────────────────

def practice_open(device, context) -> bool:
    return read_state(device)["screen"] == "practice"


def word_read(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "practice" and bool(context.result["state"]["german"])


def answered(device, context) -> bool:
    r = context.result
    s = read_state(device)
    if s["screen"] != "practice":
        return False
    return s["german"] == (r["next_word"] if r["correct"] else r["word"])


def answered_many(device, context) -> bool:
    r = context.result
    return read_state(device)["screen"] == "practice" and r["count"] == len(r["results"])


def stats_open(device, context) -> bool:
    s = read_state(device)
    return s["screen"] == "stats" and s["total"] is not None
