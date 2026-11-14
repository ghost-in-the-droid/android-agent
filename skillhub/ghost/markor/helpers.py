"""Markor helpers: type multi-line text, read the editor, list the notebook, and
check files on disk (Markor writes plain files under the notebook folder).

python_action signature: (device, params, context) -> dict
validator signature:     (device, context) -> bool
"""

from __future__ import annotations

import re
import shlex
import time
from html import unescape

_ID = "net.gsantner.markor:id/"
NOTEBOOK = "/storage/emulated/0/Documents/markor"
EDITOR = _ID + "document__fragment__edit__highlighting_editor"
_NAME_OK = re.compile(r"^[\w .,()+-]{1,80}$")


def visible_nodes(device, *, native=False) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, bounds, checked."""
    out: list[dict] = []
    tree = device.dump_portal_json() if not native and hasattr(device, "dump_portal_json") else None
    if tree:
        stack = list(tree) if isinstance(tree, list) else [tree]
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
                        "checked": bool(n.get("isChecked")),
                    }
                )
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    xml = device.dump_xml(use_portal=False) if native else device.dump_xml()
    for m in re.finditer(r"<node ([^>]*)>", xml):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append(
                {
                    "text": unescape(a.get("text", "")),
                    "desc": unescape(a.get("content-desc", "")),
                    "id": a.get("resource-id", ""),
                    "bounds": tuple(nums),
                    "checked": a.get("checked") == "true",
                    "focused": a.get("focused") == "true",
                }
            )
    return out


def _type_lines(device, text: str):
    from gitd.bots.common.adb import input_text_arg

    for i, line in enumerate(str(text).split("\n")):
        if i:
            device.adb("shell", "input", "keyevent", "KEYCODE_ENTER")
        if line:
            device.adb("shell", "input", "text", input_text_arg(line))


def _editor(device):
    return next((n for n in visible_nodes(device) if n["id"] == EDITOR), None)


def check_title(device, params, context):
    if not _NAME_OK.match(str(params["title"])):
        return {"success": False, "error": "title may use letters, digits, space and . , ( ) + - only"}
    return {"success": True}


def type_title(device, params, context):
    """Type only into a freshly confirmed, focused filename field.

    The keyboard can move this dialog after it opens. Portal can lag that
    layout change: never type using its old bounds or into the format field.
    Only the still-unsaved name is repaired if input loses characters.
    """
    from gitd.bots.common.adb import input_text_arg

    want = str(params["title"])
    for _ in range(3):
        field = next((n for n in visible_nodes(device, native=True) if n["id"] == _ID + "new_file_dialog__name"), None)
        if field is None:
            break
        left, top, right, bottom = field["bounds"]
        device.tap((left + right) // 2, (top + bottom) // 2)
        time.sleep(0.5)
        field = next((n for n in visible_nodes(device, native=True) if n["id"] == _ID + "new_file_dialog__name"), None)
        if field is None or not field.get("focused"):
            continue
        if field["text"]:
            device.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
            device.adb("shell", "input", "keyevent", *(["KEYCODE_DEL"] * len(field["text"])))
        device.adb("shell", "input", "text", input_text_arg(want))
        time.sleep(0.5)
        fresh = next((n for n in visible_nodes(device, native=True) if n["id"] == _ID + "new_file_dialog__name"), None)
        if fresh is not None and fresh.get("focused") and fresh["text"] == want:
            return {"success": True}
    return {"success": False, "error": "focused filename field does not contain the requested title; not creating a file"}


def type_content(device, params, context):
    ed = _editor(device)
    if ed is None:
        return {"success": False, "error": "editor not on screen"}
    left, top, right, bottom = ed["bounds"]
    device.tap((left + right) // 2, min(bottom - 20, top + 300), 0.3)
    _type_lines(device, params["content"])
    return {"success": True}


def append_line(device, params, context):
    """Put the cursor at the very end (Ctrl+End), start a new line if needed, type."""
    ed = _editor(device)
    if ed is None:
        return {"success": False, "error": "editor not on screen"}
    left, top, right, bottom = ed["bounds"]
    device.tap((left + right) // 2, min(bottom - 20, top + 300), 0.3)
    device.adb("shell", "input", "keycombination", "113", "123")  # CTRL_LEFT + MOVE_END
    if ed["text"].strip():
        device.adb("shell", "input", "keyevent", "KEYCODE_ENTER")
    _type_lines(device, params["text"])
    return {"success": True}


def read_editor(device, params, context):
    ed = _editor(device)
    if ed is None:
        return {"success": False, "error": "editor not on screen"}
    return {"success": True, "data": {"title": params.get("title", ""), "content": ed["text"]}}


def open_note(device, params, context):
    """API 33 folds file titles into the row description; require a filename boundary."""
    name = f"{params['title']}.md"
    row = next(
        (
            n
            for n in visible_nodes(device)
            if (n["id"] == _ID + "opoc_filesystem_item__title" and n["text"] == name)
            or (
                n["id"] == _ID + "opoc_filesystem_item__root"
                and (n["desc"] == "File " + name or n["desc"].startswith("File " + name + " "))
            )
        ),
        None,
    )
    if row is None:
        return {"success": False, "error": f"file row {name!r} not on screen"}
    left, top, right, bottom = row["bounds"]
    device.tap((left + right) // 2, (top + bottom) // 2)
    return {"success": True}


def list_notebook(device, params, context):
    seen: list[str] = []
    for _ in range(6):
        names = []
        for n in visible_nodes(device):
            if n["id"] == _ID + "opoc_filesystem_item__title":
                names.append(n["text"])
            elif n["id"] == _ID + "opoc_filesystem_item__root":
                match = re.match(r"(?:File|Folder) (.+?) \d{1,2}/\d{1,2}/\d{4}(?:,| )", n["desc"])
                if match:
                    names.append(match.group(1))
        new = list(dict.fromkeys(x for x in names if x != ".." and x not in seen))
        seen.extend(new)
        if not new:
            break
        device.swipe(540, 1800, 540, 700, 300)
        time.sleep(0.8)
    for _ in range(3):
        device.swipe(540, 700, 540, 1800, 250)
    files = [x for x in seen if "." in x]
    folders = [x for x in seen if "." not in x]
    return {"success": True, "data": {"files": files, "folders": folders, "count": len(seen)}}


def _cat(device, name: str) -> str | None:
    r = device.adb_soft("shell", "cat " + shlex.quote(f"{NOTEBOOK}/{name}"))
    return r.stdout if r.returncode == 0 else None


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.replace("\r", "").strip().split("\n"))


# ── End-state validators: (device, context) -> bool ──────────────────────────


def note_saved(device, context) -> bool:
    disk = _cat(device, f"{context.params['title']}.md")
    context.result["path"] = f"{NOTEBOOK}/{context.params['title']}.md"
    return disk is not None and _norm(str(context.params["content"])) in _norm(disk)


def note_read(device, context) -> bool:
    disk = _cat(device, f"{context.params['title']}.md")
    return disk is not None and _norm(disk) == _norm(context.result.get("content", ""))


def notebook_listed(device, context) -> bool:
    listing = device.adb_soft("shell", "ls -1Ap " + shlex.quote(NOTEBOOK))
    if listing.returncode != 0:
        return False
    entries = listing.stdout.splitlines()
    files, folders = context.result.get("files"), context.result.get("folders")
    return (
        isinstance(files, list)
        and isinstance(folders, list)
        and set(files) == {n for n in entries if not n.endswith("/")}
        and set(folders) == {n[:-1] for n in entries if n.endswith("/")}
        and context.result.get("count") == len(files) + len(folders)
    )


def todo_saved(device, context) -> bool:
    disk = _cat(device, "todo.txt") or ""
    want = str(context.params["text"]).strip()
    return any(line.rstrip().endswith(want) for line in disk.splitlines())


def quicknote_saved(device, context) -> bool:
    disk = _cat(device, "QuickNote.md") or ""
    return _norm(str(context.params["text"])) in _norm(disk)


def restart(device, params, context):
    """Cold start on the Files tab. Markor saves on pause, so a force-stop after the
    previous action's BACK loses nothing; it guarantees a known first screen."""
    device.adb("shell", "am", "force-stop", "net.gsantner.markor")
    device.adb("shell", "am", "start", "-n", "net.gsantner.markor/.activity.MainActivity")
    time.sleep(2.5)
    return {"success": True}


def ensure_new(device, params, context):
    """Markor never overwrites: for an existing name it opens that file, and typing would
    land wherever the cursor is. Refuse instead of corrupting the note."""
    if _cat(device, f"{params['title']}.md") is not None:
        return {"success": False, "error": f"{params['title']}.md already exists; pick another title"}
    return {"success": True}
