"""Contacts skill helpers. python_action: (device, params, context) -> dict;
validators: (device, context) -> bool. Verify UI output against ContactsProvider."""

from __future__ import annotations

import re
import shlex
import time
import xml.etree.ElementTree as ET

_ID = "com.google.android.contacts:id/"


def visible_nodes(device, within: str | None = None) -> list[dict]:
    """On-screen nodes (text, desc, id, bounds). `within`: keep only the subtree of
    the first node whose resource id ends with that suffix."""
    out: list[dict] = []
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    if tree:
        roots = list(tree) if isinstance(tree, list) else [tree]
        if within:
            stack, found = list(roots), None
            while stack and found is None:
                n = stack.pop(0)
                if (n.get("resourceId") or "").endswith(within):
                    found = n
                stack.extend(n.get("children") or [])
            roots = [found] if found else []
        stack = list(reversed(roots))
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
                    }
                )
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    root = ET.fromstring(device.dump_xml())
    if within:
        root = next((n for n in root.iter("node") if n.get("resource-id", "").endswith(within)), None)
        if root is None:
            return []
    for node in root.iter("node"):
        a = node.attrib
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append(
                {
                    "text": a.get("text", ""),
                    "desc": a.get("content-desc", ""),
                    "id": a.get("resource-id", ""),
                    "bounds": tuple(nums),
                }
            )
    return out


def _names(nodes) -> list[str]:
    return [n["text"] for n in nodes if n["id"] == _ID + "cliv_name_textview" and n["text"]]


def _tap(device, node):
    b = node["bounds"]
    device.tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)


def _query(device, table, columns):
    """Fail closed on unavailable/malformed provider output, including permission errors."""
    output = device.adb(
        "shell", f"content query --uri content://com.android.contacts/{table} --projection {':'.join(columns)}"
    )
    if output.strip() == "No result found.":
        return []
    rows = []
    for line in output.splitlines():
        if not re.match(r"Row: \d+ ", line):
            raise ValueError("ContactsProvider query did not return rows")
        values = dict(re.findall(r"(?:Row: \d+ |, )(\w+)=(.*?)(?=, \w+=|$)", line))
        if not set(columns) <= values.keys():
            raise ValueError("ContactsProvider row missing requested columns")
        rows.append(values)
    if not rows:
        raise ValueError("ContactsProvider query returned no readable response")
    return rows


def _provider(device):
    contacts = _query(device, "contacts", ("_id", "display_name"))
    data = _query(device, "data", ("contact_id", "mimetype", "data1", "data2"))
    return contacts, data


def _phone(value):
    return re.sub(r"[^\d+]", "", value)


def _matching_names(device, query):
    contacts, data = _provider(device)
    q = str(query).strip().casefold()
    digits = _phone(q)
    phone_ids = (
        {
            r["contact_id"]
            for r in data
            if r["mimetype"].endswith("/phone_v2") and digits and digits in _phone(r["data1"])
        }
        if re.fullmatch(r"[+\d\s().-]+", q)
        else set()
    )
    return {r["display_name"] for r in contacts if q in r["display_name"].casefold() or r["_id"] in phone_ids}


# ── python_action targets ───────────────────────────────────────────────────


def open_insert_form(device, params, context):
    """Fire ACTION_INSERT with name/phone/email extras. Built here rather than with
    launch_intent because `adb shell` re-splits extras that contain spaces."""
    cmd = [
        "am",
        "start",
        "-a",
        "android.intent.action.INSERT",
        "-t",
        "vnd.android.cursor.dir/contact",
        "--es",
        "name",
        str(params["name"]),
    ]
    if params.get("phone"):
        cmd += ["--es", "phone", str(params["phone"])]
    if params.get("email"):
        cmd += ["--es", "email", str(params["email"])]
    device.adb("shell", " ".join(shlex.quote(c) for c in cmd))
    return {"success": True}


def search(device, params, context):
    """Open the search view, type the query, return the names it lists."""
    nodes = visible_nodes(device)
    bar = next((n for n in nodes if n["id"] == _ID + "open_search_bar"), None)
    if bar is None:
        return {"success": False, "error": "search bar not on screen"}
    _tap(device, bar)
    time.sleep(1.5)
    field = next(
        (n for n in visible_nodes(device, within="open_search_view") if n["id"] == _ID + "open_search_view_edit_text"),
        None,
    )
    if field is None:
        return {"success": False, "error": "search field not on screen"}
    _tap(device, field)
    device.adb("shell", "input", "text", shlex.quote(str(params["query"]).replace(" ", "%s")))
    time.sleep(2)
    matching = _matching_names(device, params["query"])
    names = list(dict.fromkeys(n for n in _names(visible_nodes(device, within="open_search_view")) if n in matching))
    return {"success": True, "data": {"contacts": names, "count": len(names)}}


def open_first_result(device, params, context):
    matching = _matching_names(device, params["query"])
    names = [
        n
        for n in visible_nodes(device, within="open_search_view")
        if n["id"] == _ID + "cliv_name_textview" and n["text"] in matching
    ]
    if not names:
        return {"success": False, "error": f"no contact matches {params.get('query')!r}"}
    _tap(device, names[0])
    return {"success": True}


def read_details(device, params, context):
    nodes = visible_nodes(device)
    title = next((n["text"] for n in nodes if n["id"] == _ID + "large_title"), "")
    phones, emails = [], []
    for n in nodes:
        d = n["desc"]
        m = re.fullmatch(r"Call (?:(.*?) )??([+\d(][\d\s().+-]*)", d)
        if m:
            phones.append({"type": m.group(1) or "", "number": m.group(2)})
        m = re.fullmatch(r"Email (?:(.*?) )?([^\s]+@[^\s]+)", d)
        if m:
            emails.append({"type": m.group(1) or "", "address": m.group(2)})
    return {
        "success": bool(title),
        "data": {"contact": {"name": title, "phones": phones, "emails": emails}},
        "error": "contact page not on screen",
    }


def list_all(device, params, context):
    seen: list[str] = []
    for _ in range(10):
        new = [n for n in _names(visible_nodes(device)) if n not in seen]
        if not new and seen:
            break
        seen += new
        device.swipe(540, 1800, 540, 800, 300)
    header = next((n["text"] for n in visible_nodes(device) if n["id"] == _ID + "attribution_header"), "")
    return {"success": True, "data": {"contacts": seen, "count": len(seen), "header": header}}


# ── End-state validators: (device, context) -> bool ──────────────────────────


def contact_saved(device, context) -> bool:
    want = str(context.params["name"]).strip()
    nodes = visible_nodes(device)
    ok = want in _names(nodes) or any(n["id"] == _ID + "large_title" and n["text"] == want for n in nodes)
    contacts, data = _provider(device)
    phone, email = str(context.params.get("phone") or ""), str(context.params.get("email") or "")
    # Both fields must belong to the SAME contact, even with duplicate names.
    ok = ok and any(
        r["display_name"] == want
        and (
            not phone
            or any(
                d["contact_id"] == r["_id"]
                and d["mimetype"].endswith("/phone_v2")
                and _phone(d["data1"]) == _phone(phone)
                for d in data
            )
        )
        and (
            not email
            or any(
                d["contact_id"] == r["_id"]
                and d["mimetype"].endswith("/email_v2")
                and d["data1"].casefold() == email.casefold()
                for d in data
            )
        )
        for r in contacts
    )
    if ok:
        context.result["created"] = {k: context.params.get(k) for k in ("name", "phone", "email")}
    return ok


def search_ok(device, context) -> bool:
    names = context.result.get("contacts")
    matching = _matching_names(device, context.params["query"])
    shown = _names(visible_nodes(device, within="open_search_view"))
    return (
        isinstance(names, list)
        and set(names) == matching
        and all(n in shown for n in names)
        and context.result.get("count") == len(names)
    )


def details_ok(device, context) -> bool:
    c = context.result.get("contact") or {}
    fresh = read_details(device, {}, context)
    if (
        not fresh["success"]
        or c != fresh["data"]["contact"]
        or c.get("name") not in _matching_names(device, context.params["query"])
    ):
        return False
    contacts, data = _provider(device)
    candidates = [r["_id"] for r in contacts if r["display_name"] == c["name"]]
    phones = {_phone(p["number"]) for p in c.get("phones", [])}
    emails = {e["address"].casefold() for e in c.get("emails", [])}
    # The page exposes no contact ID. Conflicting same-name records are ambiguous:
    # an empty record must not excuse omitted numbers on the displayed record.
    return bool(candidates) and all(
        phones == {_phone(d["data1"]) for d in data if d["contact_id"] == cid and d["mimetype"].endswith("/phone_v2")}
        and emails
        == {d["data1"].casefold() for d in data if d["contact_id"] == cid and d["mimetype"].endswith("/email_v2")}
        for cid in candidates
    )


def list_ok(device, context) -> bool:
    contacts = _query(device, "contacts", ("_id", "display_name"))
    names = context.result.get("contacts")
    return (
        isinstance(names, list)
        and set(names) == {r["display_name"] for r in contacts}
        and context.result.get("count") == len(names)
    )


def close_contacts(device, params, context):
    """Force-stop Contacts so the next launch starts on the contact list, not on
    whatever search or contact page was open last."""
    device.adb("shell", "am", "force-stop", "com.google.android.contacts")
    return {"success": True}
