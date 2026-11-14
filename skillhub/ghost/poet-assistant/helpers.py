"""poet-assistant helpers (Poet Assistant, ca.rmen.android.poetassistant): rhymes, thesaurus and dictionary offline.

Type a word, pick a tab (RHYMER, THESAURUS, DICTIONARY) and read the result rows: rhyme groups, synonyms and
antonyms per part of speech, or definitions. Long lists are read by scrolling.
"""
from __future__ import annotations

import html
import re
import time

from gitd.bots.common.adb import input_text_arg

_PKG = "ca.rmen.android.poetassistant"
_TABS = {"rhymes": "RHYMER", "thesaurus": "THESAURUS", "dictionary": "DICTIONARY"}
_IDS = ("text1", "word_type", "definition")


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": html.unescape(a.get("text", "") or a.get("content-desc", "")),
                        "id": a.get("resource-id", "").split("/")[-1], "cls": a.get("class", "").split(".")[-1], "bounds": tuple(nums)})
    return out


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _by(nodes, ident):
    return next((n for n in nodes if n["id"] == ident), None)


def _rows(nodes):
    return [(n["id"], n["text"]) for n in sorted((n for n in nodes if n["id"] in _IDS and n["text"]), key=lambda n: n["bounds"][1])]


def _active_tab(nodes):
    """The tab whose result list is shown is not exposed directly: infer it from the row ids."""
    rows = _rows(nodes)
    if any(i == "definition" for i, _ in rows):
        return "dictionary"
    texts = [t for _, t in rows]
    if any(t in ("Synonyms:", "Antonyms:") for t in texts):
        return "thesaurus"
    if rows:
        return "rhymes"
    return ""


def read_state(device) -> dict:
    nodes = _nodes(device)
    if not any(n["text"] == "RHYMER" for n in nodes):
        return {"screen": "other"}
    head = _by(nodes, "tv_list_header")
    return {"screen": "poet", "word": head["text"] if head else "", "tab": _active_tab(nodes) if head else ""}


def _wait(device, tries=10):
    for _ in range(tries):
        st = read_state(device)
        if st.get("screen") == "poet":
            return st
        time.sleep(0.8)
    raise RuntimeError("Poet Assistant is not on screen")


def _merge(acc, new):
    for k in range(min(len(acc), len(new)), -1, -1):
        if k == 0 or acc[-k:] == new[:k]:
            return acc + new[k:]
    return acc + new


def _collect(device, limit_scrolls=5):
    acc = _rows(_nodes(device))
    for _ in range(limit_scrolls):
        device.swipe(360, 1250, 360, 450, 400)
        time.sleep(0.9)
        new = _rows(_nodes(device))
        merged = _merge(acc, new)
        if len(merged) == len(acc):
            break
        acc = merged
    for _ in range(limit_scrolls + 1):
        device.swipe(360, 500, 360, 1300, 250)
    return acc


def _parse(tab, rows):
    if tab == "dictionary":
        out, kind = [], None
        for i, t in rows:
            if i == "word_type":
                kind = t
            elif i == "definition":
                out.append({"type": kind or "", "definition": t})
        return {"definitions": out}
    if tab == "thesaurus":
        out, pos, group = [], None, None
        for _, t in rows:
            if t in ("Synonyms:", "Antonyms:"):
                group = t[:-1].lower()
                out[-1][group] = []
            elif group is None or (out and "synonyms" not in out[-1] and "antonyms" not in out[-1]) or t.lower() in ("noun", "verb", "adjective", "adverb"):
                out.append({"pos": t})
                group = None
            else:
                out[-1][group].append(t)
        return {"entries": out}
    groups, cur = {}, "matches"
    for _, t in rows:
        if t.endswith(":"):
            cur = t[:-1]
            groups[cur] = []
        else:
            groups.setdefault(cur, []).append(t)
    return {"groups": groups}


# ── python_action targets ───────────────────────────────────────────────────

def restart_app(device, params, context):
    device.adb("shell", "am", "force-stop", _PKG)
    time.sleep(0.5)
    return {}


def open_poet(device, params, context):
    return {"state": _wait(device)}


def lookup(device, params, context):
    word = str(params["word"]).strip().lower()
    mode = str(params.get("mode", "rhymes")).strip().lower()
    mode = {"rhyme": "rhymes", "rhymer": "rhymes", "synonyms": "thesaurus", "definition": "dictionary", "define": "dictionary"}.get(mode, mode)
    if mode not in _TABS:
        raise RuntimeError("mode must be rhymes, thesaurus or dictionary")
    if not re.fullmatch(r"[a-z][a-z' -]{0,30}", word):
        raise RuntimeError("word must be letters (ASCII)")
    _wait(device)
    for _ in range(3):
        nodes = _nodes(device)
        field = _by(nodes, "open_search_view_edit_text") or next((n for n in nodes if n["id"] == "toolbar" and n["cls"] == "EditText"), None)
        if not field:
            raise RuntimeError("search field not on screen")
        device.tap(*_centre(field), delay=1.0)
        # the first tap can only open the search overlay: look again for the focused field before typing
        nodes = _nodes(device)
        field = _by(nodes, "open_search_view_edit_text") or _by(nodes, "toolbar") or field
        device.tap(*_centre(field), delay=0.6)
        device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END", *(["KEYCODE_DEL"] * 30))
        device.adb("shell", "input", "text", input_text_arg(word))
        time.sleep(0.5)
        device.adb("shell", "input", "keyevent", "KEYCODE_ENTER")
        time.sleep(2.5)
        if read_state(device).get("word") == word:
            break
    else:
        raise RuntimeError(f"could not look up {word!r}")
    tab = next((n for n in _nodes(device) if n["text"] == _TABS[mode] and n["cls"] == "LinearLayout"), None)  # the tab strip (content-desc)
    if tab:
        device.tap(*_centre(tab), delay=2.5)
    st = read_state(device)
    rows = _collect(device)
    return {"word": word, "mode": mode, "state": st, "result": _parse(mode, rows)}


def get_results(device, params, context):
    st = _wait(device)
    if not st["word"]:
        raise RuntimeError("no word looked up yet: run lookup first")
    return {"word": st["word"], "mode": st["tab"], "state": st, "result": _parse(st["tab"], _collect(device))}


# ── validators ──────────────────────────────────────────────────────────────

def poet_open(device, context) -> bool:
    return read_state(device).get("screen") == "poet"


def looked_up(device, context) -> bool:
    r = context.result
    s = read_state(device)
    body = r["result"]
    filled = any(body.get(k) for k in ("groups", "entries", "definitions"))
    return s.get("screen") == "poet" and s["word"] == r["word"] and s["tab"] == r["mode"] and filled


def results_read(device, context) -> bool:
    r = context.result
    s = read_state(device)
    return s.get("screen") == "poet" and s["word"] == r["word"] and bool(r["result"])
