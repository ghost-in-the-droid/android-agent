"""Marketing lead lookup helpers shared by MCP and in-process agents."""

from __future__ import annotations

from pathlib import Path


def lookup_lead(handle: str, db_path: str | Path | None = None) -> str:
    """Return a text fact sheet for one influencer lead."""
    from gitd.db import DEFAULT_DB, get_connection

    h = handle.strip()
    if not h.startswith("@"):
        h = "@" + h
    conn = get_connection(Path(db_path) if db_path else DEFAULT_DB)
    try:
        inf = conn.execute("SELECT * FROM influencers WHERE handle = ?", (h,)).fetchone()
        if not inf:
            return f"No influencer record for {h}"
        out = [
            f"HANDLE:    {inf['handle']}",
            f"PROFILE:   https://www.tiktok.com/{inf['handle']}",
            f"FOLLOWERS: {inf['followers']:,}" if inf["followers"] else "FOLLOWERS: ?",
            f"FOLLOWING: {inf['following']:,}" if inf["following"] else "FOLLOWING: ?",
            f"LIKES:     {inf['total_likes']:,}" if inf["total_likes"] else "LIKES: ?",
            f"NICHE:     {inf['niche'] or '-'}",
            f"BIO:       {inf['bio'] or '-'}",
            f"FOUND VIA: {inf['source_query'] or '-'} (scraped {inf['scraped_at'] or '?'})",
        ]
        if inf["total_likes"] and inf["followers"]:
            try:
                ratio = inf["total_likes"] / inf["followers"]
                out.append(f"ENGAGEMENT: {ratio:.1f} likes/follower")
            except (ZeroDivisionError, TypeError):
                pass
        if inf["caption"]:
            sample = inf["caption"][:120].replace("\n", " ")
            out.append(f"SAMPLE:    {sample}...")

        ol = conn.execute(
            "SELECT ol.*, s.name AS strategy_name FROM outreach_log ol "
            "LEFT JOIN outreach_strategies s ON s.id = ol.strategy_id "
            "WHERE ol.influencer_id = ?",
            (inf["id"],),
        ).fetchone()
        if ol:
            out.append("")
            out.append("OUTREACH:")
            out.append(f"  Status:    {ol['status']}")
            out.append(f"  Sent from: @{ol['source_account'] or '?'}")
            out.append(f"  Contacted: {ol['contacted_at'] or ol['updated_at']}")
            out.append(f"  Strategy:  {ol['strategy_name'] or ol['strategy_id']}")
            if ol["deal_status"]:
                out.append(f"  Deal:      {ol['deal_status']}")
            if ol["notes"]:
                out.append(f"  Notes:     {ol['notes']}")
        else:
            out.append("")
            out.append("OUTREACH:  never contacted")

        bare = inf["handle"].lstrip("@")
        ir = conn.execute(
            "SELECT * FROM inbox_replies WHERE handle = ? OR handle LIKE ?",
            (bare, f"%{bare}%"),
        ).fetchone()
        if ir:
            out.append("")
            out.append("CONVERSATION:")
            out.append(f"  Last msg:  {ir['last_msg']}")
            out.append(f"  Status:    {ir['status']}")
            out.append(f"  Unread:    {ir['unread']}")
            out.append(f"  First seen: {ir['first_seen_at']}")
            out.append(f"  Last seen:  {ir['last_seen_at']}")
        return "\n".join(out)
    finally:
        conn.close()


def list_unread_leads(db_path: str | Path | None = None) -> str:
    """Return unread influencer replies sorted by recency."""
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
