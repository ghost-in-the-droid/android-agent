"""pocket-readlex helpers (Pocket ReadLex, uk.co.busydoingnothing.pocketrl): English to Shavian dictionary, offline.

Search screen: search_edit, result rows (word, translation in Shavian letters, word_type). Entry screen (tap a row):
entry_translation ("word -> shavian"), entry_ipa, entry_type. The entry screen has no on-screen back arrow, so the
skill returns with one system Back key press from the entry (the search screen sits under it in the same app) and
checks the app is still in front.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "uk.co.busydoingnothing.pocketrl"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "")), "id": a.get("resource-id", "").split("/")[-1],
                        "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _rows(nodes) -> list[dict]:
    words = sorted((n for n in nodes if n["id"] == "word"), key=lambda n: n["bounds"][1])
    rows = []
    for w in words:
        y = w["bounds"][1]
        tr = next((n for n in nodes if n["id"] == "translation" and abs(n["bounds"][1] - y) < 12), None)
        ty = next((n for n in nodes if n["id"] == "word_type" and 0 < n["bounds"][1] - y < 70), None)
        rows.append({"word": w["text"], "shavian": tr["text"] if tr else "", "type": ty["text"] if ty else "", "node": w})
    return rows


def read_state(device, nodes=None) -> dict:
    nodes = nodes if nodes is not None else _nodes(device)
    if _by(nodes, "search_edit"):
        return {"screen": "search", "query": _by(nodes, "search_edit")["text"],
                "results": [{k: v for k, v in r.items() if k != "node"} for r in _rows(nodes)]}
    if _by(nodes, "entry_translation"):
        tr = _by(nodes, "entry_translation")["text"]
        word, _, shav = tr.partition("→")
        return {"screen": "entry", "word": word.strip(), "shavian": shav.strip(),
                "ipa": (_by(nodes, "entry_ipa") or {}).get("text", ""), "type": (_by(nodes, "entry_type") or {}).get("text", "")}
    return {"screen": "other"}


def _wait(device, want, tries=12):
    for _ in range(tries):
        st = read_state(device)
        if st["screen"] == want:
            return st
        time.sleep(0.7)
    raise RuntimeError(f"the {want} screen is not on screen")


def _back_to_search(device):
    if read_state(device)["screen"] == "entry":
        device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.2)
    return _wait(device, "search")


def _clean(word, limit=40) -> str:
    word = str(word).strip()
    if not re.fullmatch(r"[A-Za-z'\- ]{1,%d}" % limit, word):
        raise RuntimeError("use plain English letters (apostrophes and hyphens allowed)")
    return word.lower()


def _search(device, word: str) -> dict:
    st = _back_to_search(device)
    nodes = _nodes(device)
    if st["query"]:
        clear = _by(nodes, "clear_search_button")
        if clear:
            device.tap(*_centre(clear), delay=0.6)
    device.tap(*_centre(_by(_nodes(device), "search_edit")), delay=0.5)
    device.adb("shell", "input", "text", input_text_arg(word))
    for _ in range(8):
        time.sleep(0.7)
        now = read_state(device)
        if now.get("screen") == "search" and now["query"] == word and (now["results"] or True):
            time.sleep(0.6)
            return read_state(device)
    raise RuntimeError("the search did not settle")


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_search(device, params, context):
    return {"state": _wait(device, "search")}


def search_word(device, params, context):
    word = _clean(params.get("word", ""))
    st = _search(device, word)
    return {"word": word, "count": len(st["results"]), "results": st["results"], "state": st}


def get_entry(device, params, context):
    word = _clean(params.get("word", ""))
    st = _search(device, word)
    row = next((r for r in _rows(_nodes(device)) if r["word"].lower() == word), None)
    if not row:
        raise RuntimeError(f"no exact entry for {word}; results: {[r['word'] for r in st['results']][:8]}")
    device.tap(*_centre(row["node"]), delay=1.5)
    entry = _wait(device, "entry")
    after = _back_to_search(device)
    return {"word": entry["word"], "shavian": entry["shavian"], "ipa": entry["ipa"], "type": entry["type"], "state": after}


def transliterate(device, params, context):
    words = re.findall(r"[A-Za-z'\-]+", str(params.get("text", "")))
    if not 1 <= len(words) <= 8:
        raise RuntimeError("text must contain 1 to 8 English words")
    out, missing = [], []
    for w in words:
        st = _search(device, w.lower())
        hit = next((r for r in st["results"] if r["word"].lower() == w.lower()), None)
        if hit:
            out.append(hit["shavian"])
        else:
            out.append("?")
            missing.append(w)
    return {"text": " ".join(words), "shavian": " ".join(out), "missing": missing, "state": read_state(device)}


# ── validators ──────────────────────────────────────────────────────────────

def search_open(device, context) -> bool:
    return read_state(device).get("screen") == "search"


def searched(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "search" and s["query"] == r["word"] and r["count"] >= 1


def entry_read(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "search" and bool(r["shavian"]) and bool(r["ipa"])


def transliterated(device, context) -> bool:
    r = context.result
    return read_state(device).get("screen") == "search" and bool(r["shavian"]) and len(r["shavian"].split()) == len(r["text"].split())
