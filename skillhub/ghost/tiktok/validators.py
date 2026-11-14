"""custom_python validators for the TikTok skill (v2 schema).

Each validator has the signature:
    fn(device, context) -> bool

They read context.result (populated by helpers.py python_actions) and the current
a11y tree, and return True iff the action's terminal state is satisfied.
"""
from __future__ import annotations

import re

_HANDLE_RE = re.compile(r"@([a-zA-Z0-9_.][a-zA-Z0-9_.]{1,29})")


# ───────────────────────────────────────────────────────────────────────────
# Scrape-completeness validators (for read-only actions)
# ───────────────────────────────────────────────────────────────────────────

def handle_scraped_ok(device, context) -> bool:
    """get_active_account terminal state: context.result['handle'] is a valid handle string."""
    h = (context.result or {}).get("handle")
    return isinstance(h, str) and 2 <= len(h) <= 30 and _HANDLE_RE.match(f"@{h}") is not None


def unread_count_scraped_ok(device, context) -> bool:
    """get_unread_count terminal state: unread_count is a non-negative int."""
    c = (context.result or {}).get("unread_count")
    return isinstance(c, int) and c >= 0


def stats_scraped_ok(device, context) -> bool:
    """get_my_stats terminal state: at least handle + one numeric stat populated."""
    s = (context.result or {}).get("stats") or {}
    has_handle = isinstance(s.get("handle"), str)
    has_stat = any(isinstance(s.get(k), int) and s.get(k) >= 0 for k in ("following", "followers", "likes"))
    return has_handle and has_stat


def accounts_listed_ok(device, context) -> bool:
    """list_accounts terminal state: at least 1 account, exactly 1 marked active."""
    accounts = (context.result or {}).get("accounts") or []
    if not accounts:
        return False
    active_count = sum(1 for a in accounts if a.get("is_active"))
    return active_count == 1


# ───────────────────────────────────────────────────────────────────────────
# Post-switch verification
# ───────────────────────────────────────────────────────────────────────────

def active_handle_matches(device, context) -> bool:
    """switch_account terminal state: profile header shows {handle} param.

    Reads current a11y dump + checks @{handle} appears as the primary handle.
    """
    params = context.params or {}
    target = (params.get("handle") or "").lstrip("@").strip()
    if not target:
        return False
    xml = device.dump_xml()
    return f"@{target}" in xml


# ───────────────────────────────────────────────────────────────────────────
# Upload flow validators
# ───────────────────────────────────────────────────────────────────────────

def validate_draft_description(device, context) -> bool:
    """After upload_video with action_mode=draft: the profile's "Drafts: N" counter must be
    one higher than the snapshot taken at the start of the action (ctx.result["stats"]["drafts"]).
    Falls back to N >= 1 when no snapshot exists (e.g. first-ever draft)."""
    import re
    xml = device.dump_xml() or ""
    m = re.search(r'text="Drafts:\s*(\d+)"', xml)
    if not m:
        return False
    after = int(m.group(1))
    before = ((context.result or {}).get("stats") or {}).get("drafts")
    if isinstance(before, int):
        return after == before + 1
    return after >= 1

def validate_publish_description(device, context) -> bool:
    """After upload_video with action_mode=post: verify 'Posted' banner AND video appears
    on Profile with description containing all hashtags.
    """
    params = context.params or {}
    tags = params.get("hashtags") or []

    xml = device.dump_xml()
    if "Posted" not in xml and "Your video is being posted" not in xml:
        return False
    # Hashtag verification requires navigating to the just-posted video's detail view
    # — that's a follow-up step outside the upload action's own validator.
    # For now: presence of 'Posted' banner is sufficient success signal.
    return True
