"""Pro Expense helpers: fill the entry form, pick a category on the horizontal strip, read the
Markor transactions file. Screen facts come from the running app (uiautomator dumps on the
AndroidWorld image), not from the AndroidWorld evaluator.

python_action signature: (device, params, context) -> dict
validator signature:     (device, context) -> bool. Rooted images use the app's SQLite table;
unrooted devices independently reopen saved entries without updating them. A pass is never a bench score.
"""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal, InvalidOperation
from html import unescape

PKG = "com.arduia.expense"
_ID = PKG + ":id/"
FAB, NAME, AMOUNT, NOTE, STRIP, CAT_NAME = (
    _ID + k for k in ("fb_main_add", "edt_name", "edt_amount", "edt_note", "rv_category", "tv_name")
)
DB = "/data/data/com.arduia.expense/databases/accounting.db"
MARKOR_FILE = "/storage/emulated/0/Documents/Markor/my_expenses.txt"
# Strip order in the app, left to right; AndroidWorld's category ids are in CATEGORY_ID.
CATEGORIES = [
    "Food",
    "Income",
    "Housing",
    "Social",
    "Entertainment",
    "Transportation",
    "Clothes",
    "Health Care",
    "Education",
    "Donation",
    "Others",
]
CATEGORY_ID = {
    "Others": 1,
    "Income": 2,
    "Food": 3,
    "Housing": 4,
    "Social": 5,
    "Entertainment": 6,
    "Transportation": 7,
    "Clothes": 8,
    "Health Care": 9,
    "Education": 10,
    "Donation": 11,
}


def dump(device) -> str:
    """Screen XML the way the engine's own steps read it (Portal, then uiautomator --compressed, then
    Device.dump_xml); an empty tree is retried because uiautomator refuses to dump while the screen animates."""
    try:
        from gitd.skills.engine.dispatch import _fast_dump as fast_dump
    except ImportError:  # pragma: no cover - engine always present when a skill runs
        fast_dump = None
    for attempt in range(4):
        xml = fast_dump(device) if fast_dump else device.dump_xml()
        if xml and "<node " in xml:
            return xml
        time.sleep(0.4 * (attempt + 1))
    return xml or ""


def nodes(device, *, native=False) -> list[dict]:
    """On-screen nodes as dicts: text, desc, id, bounds (left, t, r, b)."""
    out = []
    xml = device.dump_xml(use_portal=False) if native else dump(device)
    for m in re.finditer(r"<node ([^>]*)>", xml):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1]:
            out.append(
                {
                    "text": unescape(a.get("text", "")),
                    "desc": unescape(a.get("content-desc", "")),
                    "id": a.get("resource-id", ""),
                    "bounds": tuple(nums),
                    "checked": a.get("checked") == "true",
                }
            )
    return out


def find(ns: list[dict], rid: str | None = None, text: str | None = None) -> dict | None:
    for n in ns:
        if rid is not None and n["id"] != rid:
            continue
        if text is not None and n["text"] != text:
            continue
        return n
    return None


def tap_node(device, n: dict, delay: float = 0.8):
    left, top, right, bottom = n["bounds"]
    device.tap((left + right) // 2, (top + bottom) // 2, delay)


def dismiss_foreign_crash(device, ns: list[dict]) -> bool:
    """Close an "Application Error" dialog raised by ANOTHER app (on the AndroidWorld image the
    accessibility forwarder crashes now and then and its dialog takes focus); never our own."""
    close = find(ns, rid="android:id/aerr_close")
    title = find(ns, rid="android:id/alertTitle")
    if close is None or (title is not None and PKG in title["text"]):
        return False
    tap_node(device, close, 1.0)
    return True


def in_foreground(device) -> bool:
    state = device.adb("shell", "dumpsys", "activity", "activities")
    # Android 13 can list a resumed activity for a background stack as well.
    # Prefer the global top-resumed record; missing/ambiguous focus is not success.
    for field in ("topResumedActivity", "mResumedActivity", "mFocusedActivity"):
        matches = re.findall(r"^\s*" + field + r"\s*[:=]([^\n]*)", state, re.MULTILINE)
        if matches:
            return all(re.search(r"\b" + re.escape(PKG) + r"/", value) for value in matches)
    return False


def wait_for(device, rid: str, timeout_s: float = 10.0, *, require_foreground: bool = False) -> dict:
    deadline = time.monotonic() + timeout_s
    ns = []
    while time.monotonic() <= deadline:
        ns = nodes(device)
        n = find(ns, rid=rid)
        if n is not None and (not require_foreground or in_foreground(device)):
            return n
        if dismiss_foreign_crash(device, ns):
            continue
        time.sleep(0.5)
    seen = sorted({x["id"].split("/")[-1] for x in ns if x["id"]})[:12]
    raise RuntimeError(
        f"{rid.split('/')[-1]} did not appear within {timeout_s:.0f}s (on screen: {', '.join(seen) or 'empty dump'})"
    )


def _home_fab(device):
    if not in_foreground(device):
        device.adb("shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
    return wait_for(device, FAB, 60, require_foreground=True)


def wait_for_home(device, params, context):
    """Allow a slow launch to settle; only accept our foreground home screen."""
    _home_fab(device)
    return {"success": True}


def open_editor(device):
    """Wait up to 30s after each of at most two FAB taps; never retry Save or row entry."""
    tap_node(device, _home_fab(device), 1.0)
    for attempt in range(2):
        try:
            wait_for(device, NAME, 30, require_foreground=True)
            return
        except RuntimeError:
            if attempt:
                raise
            # Recheck after the timeout: a late editor must not receive a second tap.
            ns = nodes(device)
            if not in_foreground(device):
                raise
            if find(ns, rid=NAME) is not None:
                return
            fab = find(ns, rid=FAB)
            if fab is None:
                raise
            tap_node(device, fab, 1.0)


def type_into(device, rid: str, text: str):
    from gitd.bots.common.adb import input_text_arg

    tap_node(device, wait_for(device, rid), 0.5)
    if text:
        device.adb("shell", "input", "text", input_text_arg(str(text)))
    time.sleep(0.3)


def select_category(device, name: str):
    """Tap the category card on the horizontal strip, scrolling it into view when needed."""
    if name not in CATEGORY_ID:
        raise ValueError(f"unknown category {name!r}; one of {', '.join(CATEGORIES)}")
    for attempt in range(12):
        ns = nodes(device, native=True)
        strip = find(ns, rid=STRIP)
        if strip is None:
            if dismiss_foreign_crash(device, ns):
                continue
            raise RuntimeError("category strip not on screen")
        sl, st, sr, sb = strip["bounds"]
        for n in ns:
            left, _top, right, _bottom = n["bounds"]
            # A card is fully visible when its label has real width and sits inside the strip.
            if n["id"] == CAT_NAME and n["text"] == name and right - left > 40 and left >= sl and right <= sr:
                tap_node(device, n, 0.6)
                return
        y = (st + sb) // 2
        # First look rightwards (the strip starts at Food), then sweep back left.
        if attempt < 5:
            device.swipe(sr - 60, y, sl + 60, y, 400, 0.6)
        else:
            device.swipe(sl + 60, y, sr - 60, y, 400, 0.6)
    raise RuntimeError(f"category {name!r} not found on the strip")


def cents(amount) -> int:
    try:
        return int((Decimal(str(amount).replace("$", "").replace(",", "").strip()) * 100).to_integral_value())
    except InvalidOperation as exc:
        raise ValueError(f"bad amount {amount!r}") from exc


_AMOUNT_KEYS = ("amount", "amount_dollars")
_CATEGORY_KEYS = ("category", "category_name")


def _first(row: dict, keys: tuple[str, ...]):
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def normalize_rows(rows) -> list[dict]:
    """Caller rows -> ``{name, amount "12.50", category, note}``. Accepts AndroidWorld's own column names
    (``amount_dollars``, ``category_name``) beside ``amount`` / ``category``, a JSON string, or a single
    object. A row without an amount or a category is refused: it must never be saved as 0.00 / Others and
    then validated against that same default (ab3 finding, 2026-10-22)."""
    if isinstance(rows, str):
        rows = json.loads(rows)
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows must be a non-empty list of objects")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"row is not an object: {row!r}")
        name = str(row.get("name") or "").strip()
        if not name:
            raise ValueError("every row needs a name")
        if len(name.encode("utf-16-le")) // 2 > 20:
            raise ValueError("expense name exceeds the app's 20-character field limit")
        amount = _first(row, _AMOUNT_KEYS)
        if amount is None:
            raise ValueError(f"row {name!r} has no amount (give amount or amount_dollars)")
        category = _first(row, _CATEGORY_KEYS)
        if category is None:
            raise ValueError(
                f"row {name!r} has no category (give category or category_name; one of {', '.join(CATEGORIES)})"
            )
        category = str(category).strip()
        if category not in CATEGORY_ID:
            raise ValueError(f"unknown category {category!r} for {name!r}; one of {', '.join(CATEGORIES)}")
        normalized_amount = f"{cents(amount) / 100:.2f}"
        note = str(row.get("note") or "").strip()
        if len(normalized_amount) > 10 or len(note.encode("utf-16-le")) // 2 > 100:
            raise ValueError("expense amount or note exceeds the app's field limit (10 / 100 characters)")
        out.append(
            {
                "name": name,
                "amount": normalized_amount,
                "category": category,
                "note": note,
            }
        )
    return out


def fresh_start(device, params, context):
    """Stop any running Pro Expense first so the flow always begins on the home screen, never inside a
    half-filled entry form left by an earlier run."""
    device.adb("shell", "am", "force-stop", PKG)
    time.sleep(0.8)
    return {"success": True}


def add_row(device, row: dict):
    open_editor(device)
    type_into(device, NAME, row["name"])
    type_into(device, AMOUNT, row["amount"])
    select_category(device, row["category"])
    if row["note"]:
        type_into(device, NOTE, row["note"])
    ns = nodes(device)
    save = find(ns, text="SAVE")
    if save is None and dismiss_foreign_crash(device, ns):
        save = find(nodes(device), text="SAVE")
    if save is None:
        raise RuntimeError("SAVE button not on screen")
    tap_node(device, save, 1.0)
    wait_for(device, FAB, 10)


def add_rows(device, params, context):
    rows = normalize_rows(params["rows"])
    for row in rows:
        add_row(device, row)
    return {"success": True, "data": {"added": len(rows), "rows": rows}}


def parse_expense_text(text: str) -> list[dict]:
    """AndroidWorld's csv text representation: header line, then name|amount_dollars|category_name|note."""
    lines = [ln.rstrip("\r") for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split("|")]
    out = []
    for ln in lines[1:]:
        cells = ln.split("|")
        if len(cells) < len(header):
            continue
        row = dict(zip(header, (c.strip() for c in cells)))
        # No defaults: a file without an amount or category column is refused by normalize_rows.
        out.append(
            {
                "name": row.get("name", ""),
                "amount": row.get("amount_dollars", row.get("amount")),
                "category": row.get("category_name", row.get("category")),
                "note": row.get("note", ""),
            }
        )
    return out


def read_markor_expenses(device) -> list[dict]:
    text = device.adb("shell", "cat", MARKOR_FILE)
    if "No such file" in text:
        raise RuntimeError("my_expenses.txt is not in the Markor notebook")
    return parse_expense_text(text)


_REIMB = re.compile(r"[\s.;,-]*reimbursable[.!]?\s*$", re.IGNORECASE)


def reimbursable(rows: list[dict]) -> list[dict]:
    """Rows tagged Reimbursable, with the tag stripped from the note: the tag marks which transactions
    to log, it is not part of the expense's own note."""
    out = []
    for r in rows:
        if "reimbursable" in r["note"].lower():
            out.append({**r, "note": _REIMB.sub("", r["note"]).strip()})
    return out


def add_reimbursable_from_markor(device, params, context):
    rows = normalize_rows(reimbursable(read_markor_expenses(device)))
    if not rows:
        return {"success": False, "error": "my_expenses.txt holds no transaction marked Reimbursable"}
    for row in rows:
        add_row(device, row)
    return {"success": True, "data": {"added": len(rows), "rows": rows}}


# ── end-state validators ──────────────────────────────────────────────────────


def ledger(device) -> list[tuple[str, int, int, str]]:
    """Rows of the expense table as (name, amount_cents, category_id, note)."""
    out = device.adb("shell", f'sqlite3 {DB} "select name,amount,category,note from expense"')
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < 4:
            continue
        try:
            rows.append((parts[0].strip(), int(parts[1]), int(parts[2]), "|".join(parts[3:]).strip()))
        except ValueError:
            continue
    return rows


def rows_present(device, wanted: list[dict]) -> bool:
    try:
        have = ledger(device)
    except RuntimeError:
        return saved_rows_visible(device, wanted)
    return bool(wanted) and all(
        (r["name"], cents(r["amount"]), CATEGORY_ID[r["category"]], r["note"]) in have for r in wanted
    )


def saved_editor_row(device):
    """Read an existing entry without changing or saving it, including its checked category."""
    for attempt in range(12):
        ns = nodes(device, native=True)
        fields = [find(ns, rid=rid) for rid in (NAME, AMOUNT, NOTE)]
        update = find(ns, rid=_ID + "btn_save", text="UPDATE")
        if any(field is None for field in fields) or update is None:
            return None
        checked = [n for n in ns if n["id"] == _ID + "cd_category" and n.get("checked")]
        categories = []
        for card in checked:
            left, t, r, b = card["bounds"]
            categories.extend(
                n["text"]
                for n in ns
                if n["id"] == CAT_NAME
                and left <= n["bounds"][0] < n["bounds"][2] <= r
                and t <= n["bounds"][1] < n["bounds"][3] <= b
            )
        if len(categories) == 1 and categories[0] in CATEGORY_ID:
            return (
                fields[0]["text"].strip(),
                cents(fields[1]["text"]),
                CATEGORY_ID[categories[0]],
                fields[2]["text"].strip(),
            )
        strip = find(ns, rid=STRIP)
        if strip is None:
            return None
        left, t, r, b = strip["bounds"]
        # Read off-screen categories by scrolling only; never change selection.
        device.swipe(
            r - 40 if attempt < 6 else left + 40,
            (t + b) // 2,
            left + 40 if attempt < 6 else r - 40,
            (t + b) // 2,
            300,
            0.4,
        )
    return None


def saved_rows_visible(device, wanted):
    """Unrooted fallback: independently reopen saved rows from today's expense log.

    The action creates today's entries. A blank list, incomplete editor, wrong
    checked category, missing note or unexpected screen cannot establish success.
    This verifies membership, matching the SQLite validator's contract.
    """
    if not wanted:
        return False
    expected = {(r["name"], cents(r["amount"]), CATEGORY_ID[r["category"]], r["note"]) for r in wanted}
    names = {r[0] for r in expected}
    _home_fab(device)
    for _ in range(8):
        ns = nodes(device)
        more = find(ns, rid=_ID + "btn_more_logs")
        if more is not None:
            tap_node(device, more)
            break
        if not ns:
            return False
        width, height = max(n["bounds"][2] for n in ns), max(n["bounds"][3] for n in ns)
        device.swipe(width // 2, int(height * 0.8), width // 2, int(height * 0.3), 300, 0.5)
    else:
        return False
    have = set()
    for _ in range(8):
        ns = nodes(device)
        if find(ns, text="Expense Logs") is None:
            return False
        # The narrow log list truncates names before exposing them to a11y.
        # A prefix is only a navigation hint; the reopened editor must still
        # match the complete persisted tuple below.
        candidates = [
            n
            for n in ns
            if n["id"] == CAT_NAME
            and n["text"].rstrip("…").strip()
            and any(name.startswith(n["text"].rstrip("…").strip()) for name in names)
        ]
        for candidate in candidates:
            tap_node(device, candidate)
            edit = wait_for(device, _ID + "btn_edit", 5)
            tap_node(device, edit)
            wait_for(device, NAME, 5)
            try:
                row = saved_editor_row(device)
                if row is not None:
                    have.add(row)
            finally:
                # The editor was read only: leave without touching UPDATE.
                device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
                time.sleep(0.5)
            if expected <= have:
                device.adb("shell", "input", "keyevent", "KEYCODE_BACK")
                return True
        if not ns or not candidates:
            # Other visible rows can precede the requested ones; keep scrolling.
            if not any(n["id"] == CAT_NAME for n in ns):
                return False
        width, height = max(n["bounds"][2] for n in ns), max(n["bounds"][3] for n in ns)
        device.swipe(width // 2, int(height * 0.8), width // 2, int(height * 0.3), 300, 0.5)
    return False


def validate_expense_add_multiple(device, context) -> bool:
    return rows_present(device, normalize_rows(context.params["rows"]))


def validate_expense_add_single(device, context) -> bool:
    return rows_present(device, normalize_rows(context.params["rows"]))


def validate_expense_add_multiple_from_markor(device, context) -> bool:
    return rows_present(device, normalize_rows(reimbursable(read_markor_expenses(device))))
