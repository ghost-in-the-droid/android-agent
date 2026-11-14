"""Wikipedia app helpers. Articles render in a WebView; Ghost Portal exposes the
whole article (also off-screen) as text nodes, so readers walk the Portal tree in
document order. Native screens use the shared on-screen reader.

python_action signature: (device, params, context) -> dict
validator signature:     (device, context) -> bool
"""
from __future__ import annotations

import re
import time

_HATNOTE = re.compile(r'^\s*(For [^.]*?, see [^.]*\.|"[^"]*" redirects here\.[^.]*\.|This article is about [^.]*\.'
                      r'|Not to be confused with [^.]*\.|[^.]{0,80} redirects here\.[^.]*\.)\s*')


def visible_nodes(device) -> list[dict]:
    """Flatten the current screen into on-screen nodes: text, desc, id, bounds, checked."""
    out: list[dict] = []
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    if tree:
        stack = list(tree) if isinstance(tree, list) else [tree]
        while stack:
            n = stack.pop()
            b = n.get("boundsInScreen") or {}
            box = (b.get("left", 0), b.get("top", 0), b.get("right", 0), b.get("bottom", 0))
            if box[2] > box[0] and box[3] > box[1] and box[0] >= 0:
                out.append({"text": n.get("text") or "", "desc": n.get("contentDescription") or "",
                            "id": n.get("resourceId") or "", "bounds": box,
                            "checked": bool(n.get("isChecked"))})
            stack.extend(reversed(n.get("children") or []))
        out.sort(key=lambda n: (n["bounds"][1], n["bounds"][0]))
        return out
    for m in re.finditer(r"<node ([^>]*)>", device.dump_xml()):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
        nums = [int(v) for v in re.findall(r"-?\d+", a.get("bounds", ""))]
        if len(nums) == 4 and nums[2] > nums[0] and nums[3] > nums[1] and nums[0] >= 0:
            out.append({"text": a.get("text", ""), "desc": a.get("content-desc", ""),
                        "id": a.get("resource-id", ""), "bounds": tuple(nums),
                        "checked": a.get("checked") == "true"})
    return out



def document_texts(device) -> list[dict]:
    """Every text node of the Portal tree in document order (WebView included)."""
    tree = device.dump_portal_json() if hasattr(device, "dump_portal_json") else None
    out: list[dict] = []
    if not tree:
        return [n for n in visible_nodes(device) if n["text"]]
    stack = list(reversed(tree)) if isinstance(tree, list) else [tree]
    while stack:
        n = stack.pop()
        if n.get("text"):
            out.append({"text": n["text"], "id": n.get("resourceId") or "",
                        "top": (n.get("boundsInScreen") or {}).get("top", 0)})
        stack.extend(reversed(n.get("children") or []))
    return out


def norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", str(t).replace("_", " ")).strip().lower()


def pairs(nodes, gap=12) -> list[dict]:
    """Title line directly above a description line, same left edge."""
    texts = sorted([n for n in nodes if n["text"]], key=lambda n: (n["bounds"][1], n["bounds"][0]))
    out, i = [], 0
    while i < len(texts) - 1:
        a, b = texts[i], texts[i + 1]
        if a["bounds"][0] == b["bounds"][0] and 0 <= b["bounds"][1] - a["bounds"][3] <= gap:
            out.append({"title": a["text"], "description": b["text"]})
            i += 2
        else:
            i += 1
    return out


def search_results(device, params, context):
    limit = int(params.get("limit") or 10)
    nodes = [n for n in visible_nodes(device) if n["bounds"][1] > 300 and not n["id"]]
    results = pairs(nodes)[:limit]
    return {"success": bool(results), "error": "no search results on screen",
            "data": {"query": params["query"], "results": results, "count": len(results)}}


def read_article(device, params, context):
    texts = document_texts(device)
    desc_i = next((i for i, n in enumerate(texts) if n["id"].endswith("pcs-edit-section-title-description")), None)
    if desc_i is None or desc_i == 0:
        return {"success": False, "error": "article header (title description) not found"}
    title, description = texts[desc_i - 1]["text"], texts[desc_i]["text"]
    body = "".join(n["text"] for n in texts[desc_i + 1:desc_i + 400])
    body = re.sub(r"\[\s*\d+\s*\]|\[\s*[a-z]\s*\]|\[citation needed\]", "", body)
    body = re.sub(r"\s+", " ", body).strip()
    for _ in range(4):
        body = _HATNOTE.sub("", body, count=1)
    lead = body[:900]
    cut = lead.rfind(". ")
    lead = lead[:cut + 1] if cut > 200 else lead
    return {"success": True, "data": {"title": title, "description": description, "lead": lead}}


def _parse_featured(texts):
    i = next((k for k, n in enumerate(texts) if n["text"] == "Featured article"), None)
    if i is None:
        return None
    rest = [n["text"] for n in texts[i + 1:i + 8] if not n["text"].startswith("Featured articles are")]
    if len(rest) < 2:
        return None
    date = next((n["text"] for n in texts[:i] if n["text"].startswith("Today")), "")
    return {"date": date.replace("Today - ", ""), "title": rest[0], "description": rest[1],
            "extract": rest[2] if len(rest) > 2 else ""}


def featured_article(device, params, context):
    """Scroll the feed to the top, then step down until the Featured article header and
    its card body are rendered together (the RecyclerView drops off-screen cards)."""
    for _ in range(4):
        device.swipe(540, 700, 540, 1900, 250)
    time.sleep(1.0)
    for _ in range(8):
        data = _parse_featured(document_texts(device))
        if data:
            return {"success": True, "data": data}
        device.swipe(540, 1700, 540, 1250, 400)
        time.sleep(1.0)
    return {"success": False, "error": "no Featured article card in the feed"}


def read_save_sheet(device, params, context):
    """The save sheet lists the article with a bookmark whose content-desc is Saved."""
    nodes = visible_nodes(device)
    want = norm_title(params["title"])
    listed = any(norm_title(n["text"]) == want for n in nodes)
    saved = any(n["desc"] == "Saved" for n in nodes)
    return {"success": True, "data": {"saved": listed and saved}}


# ── End-state validators: (device, context) -> bool ──────────────────────────

def has_results(device, context) -> bool:
    return bool(context.result.get("results"))


def article_matches(device, context) -> bool:
    want = norm_title(context.params["title"])
    return norm_title(context.result.get("title", "")) == want and len(context.result.get("lead", "")) > 40


def featured_read(device, context) -> bool:
    return bool(context.result.get("title")) and bool(context.result.get("description"))


def article_saved(device, context) -> bool:
    return bool(context.result.get("saved")) and article_matches(device, context)
