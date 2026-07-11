"""Local CRM lookup helpers shared by MCP and in-process agents.

Read-only views over the local contact/message tables: a fact sheet for a
single contact and a list of contacts with unread messages. No network calls,
no writes.
"""

from __future__ import annotations

from pathlib import Path


def crm_lookup_contact(handle: str, db_path: str | Path | None = None) -> str:
    """Return a text fact sheet for one stored contact."""
    from gitd.db import DEFAULT_DB, get_connection

    h = handle.strip()
    if not h.startswith("@"):
        h = "@" + h
    conn = get_connection(Path(db_path) if db_path else DEFAULT_DB)
    try:
        row = conn.execute("SELECT * FROM influencers WHERE handle = ?", (h,)).fetchone()
        if not row:
            return f"No contact record for {h}"
        out = [
            f"HANDLE:    {row['handle']}",
            f"FOLLOWERS: {row['followers']:,}" if row["followers"] else "FOLLOWERS: ?",
            f"FOLLOWING: {row['following']:,}" if row["following"] else "FOLLOWING: ?",
            f"LIKES:     {row['total_likes']:,}" if row["total_likes"] else "LIKES: ?",
            f"NICHE:     {row['niche'] or '-'}",
            f"BIO:       {row['bio'] or '-'}",
        ]
        if row["caption"]:
            sample = row["caption"][:120].replace("\n", " ")
            out.append(f"SAMPLE:    {sample}...")

        contact = conn.execute(
            "SELECT ol.*, s.name AS strategy_name FROM outreach_log ol "
            "LEFT JOIN outreach_strategies s ON s.id = ol.strategy_id "
            "WHERE ol.influencer_id = ?",
            (row["id"],),
        ).fetchone()
        if contact:
            out.append("")
            out.append("CONTACT STATUS:")
            out.append(f"  Status:       {contact['status']}")
            out.append(f"  Contacted via: @{contact['source_account'] or '?'}")
            out.append(f"  Contacted at:  {contact['contacted_at'] or contact['updated_at']}")
            if contact["deal_status"]:
                out.append(f"  Deal:          {contact['deal_status']}")
            if contact["notes"]:
                out.append(f"  Notes:         {contact['notes']}")
        else:
            out.append("")
            out.append("CONTACT STATUS: never contacted")

        bare = row["handle"].lstrip("@")
        msg = conn.execute(
            "SELECT * FROM inbox_replies WHERE handle = ? OR handle LIKE ?",
            (bare, f"%{bare}%"),
        ).fetchone()
        if msg:
            out.append("")
            out.append("CONVERSATION:")
            out.append(f"  Last msg:   {msg['last_msg']}")
            out.append(f"  Status:     {msg['status']}")
            out.append(f"  Unread:     {msg['unread']}")
            out.append(f"  First seen: {msg['first_seen_at']}")
            out.append(f"  Last seen:  {msg['last_seen_at']}")
        return "\n".join(out)
    finally:
        conn.close()


def crm_list_unread_messages(db_path: str | Path | None = None) -> str:
    """Return contacts with unread messages sorted by recency."""
    from gitd.db import DEFAULT_DB, get_connection

    conn = get_connection(Path(db_path) if db_path else DEFAULT_DB)
    try:
        rows = conn.execute(
            "SELECT handle, unread, last_msg, last_seen_at "
            "FROM inbox_replies WHERE unread > 0 ORDER BY last_seen_at DESC"
        ).fetchall()
        if not rows:
            return "0 unread"
        out = [f"{len(rows)} unread:"]
        for r in rows:
            preview = (r["last_msg"] or "").replace("\n", " ")[:80]
            out.append(f"  [{r['unread']}] {r['handle']:<35} - {preview}")
            out.append(f"      seen: {r['last_seen_at']}")
        return "\n".join(out)
    finally:
        conn.close()
