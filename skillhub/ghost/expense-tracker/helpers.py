"""expense-tracker helpers (My Expenses, org.totschnig.myexpenses).

Local only: the default account "Budget Book" lives on the phone, no account or sync. The list shows one row per
transaction ("note / payee", amount, date); the totals strip shows income, expenses, transfers and the balance.

Uses the engine-fixed API: python_action returns a plain dict merged into context.result.
"""
from __future__ import annotations

import re
import time

from gitd.bots.common.adb import input_text_arg

_ID = "org.totschnig.myexpenses:id/"


def _nodes(device) -> list[dict]:
    out = []
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""), "id": a.get("resource-id", ""),
                        "bounds": tuple(nums)})
    return out


def _by(nodes, suffix):
    return [n for n in nodes if n["id"] == _ID + suffix]


def _centre(n):
    b = n["bounds"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def _tap(device, n, delay=1.0):
    device.tap(*_centre(n), delay=delay)


def _wait(device, pred, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        nodes = _nodes(device)
        hit = pred(nodes)
        if hit:
            return nodes
        time.sleep(0.5)
    raise RuntimeError("expected screen did not appear")


def on_list(nodes) -> bool:
    return any(n["desc"].startswith("New Transaction") for n in nodes) or any(n["text"] == "No Expenses Yet!" for n in nodes)


def money(text: str) -> float | None:
    m = re.search(r"([−\-]?)\s*€?\s*([\d.,]+)", text.replace("−", "-"))
    if not m:
        return None
    v = float(m.group(2).replace(",", ""))
    return -v if m.group(1) in ("-", "−") else v


def _ascii(text) -> str:
    text = str(text)
    if not text.isascii():
        raise RuntimeError("payee and note must be plain ASCII (adb text input cannot type other characters)")
    return text


# ── python_action targets ───────────────────────────────────────────────────

def to_list(device, params, context):
    """First run: click through the onboarding slides (Next/Start); BACK out of forms; end on the transaction list."""
    for _ in range(8):
        nodes = _nodes(device)
        if on_list(nodes):
            return {}
        nxt = next((n for n in nodes if n["text"] in ("Next", "Start", "Finish", "Done", "Get started", "OK")), None)
        if nxt:
            _tap(device, nxt, delay=1.2)
            continue
        device.back()
        time.sleep(0.8)
    raise RuntimeError("could not reach the transaction list")


def _new(device, income: bool, amount: str, payee: str, note: str):
    if not re.fullmatch(r"\d+([.,]\d{1,2})?", str(amount).strip()):
        raise RuntimeError("amount must be a positive number like 12.50")
    nodes = _nodes(device)
    new = next((n for n in nodes if n["desc"].startswith("New Transaction")), None)
    if not new:
        raise RuntimeError("New Transaction button not on screen")
    _tap(device, new, delay=2.0)
    nodes = _wait(device, lambda ns: _by(ns, "AmountEditText"))
    if income:
        sw = _by(nodes, "TaType")
        if sw:
            _tap(device, sw[0], delay=0.8)
    amt = _by(nodes, "AmountEditText")[0]
    _tap(device, amt, delay=0.6)
    if not re.fullmatch(r"\d{1,9}([.,]\d{1,2})?", str(amount).strip()):
        raise RuntimeError("amount must be a positive number like 12.50")
    device.adb("shell", "input", "text", input_text_arg(str(amount).strip().replace(",", ".")))
    if payee:
        _tap(device, _by(_nodes(device), "auto_complete_textview")[0], delay=0.6)
        device.adb("shell", "input", "text", input_text_arg(_ascii(payee)))
        device.back()
        time.sleep(0.5)
    if note:
        _tap(device, _by(_nodes(device), "Comment")[0], delay=0.6)
        device.adb("shell", "input", "text", input_text_arg(_ascii(note)))
        device.back()
        time.sleep(0.5)
    _tap(device, _by(_nodes(device), "fab")[0], delay=2.5)
    _wait(device, on_list)


def add_expense(device, params, context):
    before = read_totals(device)
    _new(device, False, params["amount"], params.get("payee", ""), params.get("note", ""))
    return {"added": {"type": "expense", "amount": str(params["amount"]), "payee": params.get("payee", ""), "note": params.get("note", "")},
            "before": before, "totals": read_totals(device)}


def add_income(device, params, context):
    before = read_totals(device)
    _new(device, True, params["amount"], params.get("payee", ""), params.get("note", ""))
    return {"added": {"type": "income", "amount": str(params["amount"]), "payee": params.get("payee", ""), "note": params.get("note", "")},
            "before": before, "totals": read_totals(device)}


def read_totals(device) -> dict:
    nodes = _nodes(device)
    bal = next((money(n["text"]) for n in nodes if n["bounds"][1] < 135 and re.search(r"€", n["text"]) and n["bounds"][0] < 300), None)
    inc = next((money(n["desc"].split(":")[1]) for n in nodes if n["desc"].startswith("Income:")), None)
    exp = next((money(n["desc"].split(":")[1]) for n in nodes if n["desc"].startswith("Expenses:")), None)
    trf = next((money(n["desc"].split(":")[1]) for n in nodes if n["desc"].startswith("Transfers:")), None)
    acct = next((n["text"] for n in nodes if n["bounds"][1] < 110 and n["bounds"][0] < 120 and n["text"] and "€" not in n["text"]), "")
    return {"account": acct, "balance": bal, "income": inc, "expenses": exp, "transfers": trf}


def read_rows(nodes) -> list[dict]:
    rows = []
    amts = [n for n in nodes if re.fullmatch(r"[−\-+]?€[\d.,]+", n["text"].strip()) and n["bounds"][1] > 260]
    for a in sorted(amts, key=lambda n: n["bounds"][1]):
        y0, y1 = a["bounds"][1] - 20, a["bounds"][3] + 60
        label = next((n["text"] for n in nodes if y0 <= n["bounds"][1] <= y1 and n["bounds"][0] < 200 and n["text"]), "")
        date = next((n["text"] for n in nodes if y0 <= n["bounds"][1] <= y1 and re.fullmatch(r"\d+ \w+ \d{4}", n["text"])), "")
        note, _, payee = label.partition(" / ")
        if not payee:
            note, payee = "", label
        rows.append({"note": note, "payee": payee, "amount": money(a["text"]), "date": date})
    return rows


def list_tx(device, params, context):
    nodes = _nodes(device)
    return {"transactions": read_rows(nodes), "totals": read_totals(device)}


def totals(device, params, context):
    return {"totals": read_totals(device)}


# ── validators ──────────────────────────────────────────────────────────────

def added(device, context) -> bool:
    r = context.result
    nodes = _nodes(device)
    want = abs(float(str(r["added"]["amount"]).replace(",", ".")))
    sign = 1 if r["added"]["type"] == "income" else -1
    return on_list(nodes) and any(abs(abs(t["amount"] or 0) - want) < 0.005 and (t["amount"] or 0) * sign > 0 for t in read_rows(nodes))


def listed(device, context) -> bool:
    got = context.result.get("transactions")
    return on_list(_nodes(device)) and isinstance(got, list) and got == read_rows(_nodes(device))


def totals_read(device, context) -> bool:
    t = context.result.get("totals", {})
    return on_list(_nodes(device)) and t.get("balance") is not None and t == read_totals(device)
