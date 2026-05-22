"""Compatibility shim: gitd.db — raw SQLite helpers for TikTok bots.

The bots in internal/ghost_premium/bots/tiktok/ were written against the old
gitd.db module (Flask era). This shim re-exposes the same function signatures
so those bots can import without modification.

Only the functions actually imported by the bots are included. Do not add more
unless a new bot import requires it.
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "gitd.db"


def get_connection(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS influencers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        handle          TEXT    NOT NULL UNIQUE,
        display_name    TEXT,
        platform        TEXT    DEFAULT 'TikTok',
        profile_url     TEXT,
        followers       INTEGER,
        following       INTEGER,
        total_likes     INTEGER,
        bio             TEXT,
        niche           TEXT,
        pet_focus       TEXT,
        caption         TEXT,
        top_views       TEXT,
        avg_views       TEXT,
        num_videos      TEXT,
        screenshot_path TEXT,
        source_query    TEXT,
        scraped_at      TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        updated_at      TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS outreach_strategies (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        name             TEXT    NOT NULL,
        description      TEXT,
        message_template TEXT,
        is_active        INTEGER DEFAULT 1,
        created_at       TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS outreach_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        influencer_id   INTEGER NOT NULL REFERENCES influencers(id),
        strategy_id     INTEGER REFERENCES outreach_strategies(id),
        status          TEXT    DEFAULT 'not_contacted',
        deal_status     TEXT,
        contacted_at    TEXT,
        notes           TEXT,
        source          TEXT    DEFAULT 'bot',
        source_account  TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        updated_at      TEXT    DEFAULT (datetime('now'))
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_outreach_influencer
        ON outreach_log(influencer_id);

    CREATE TABLE IF NOT EXISTS crawl_runs (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        run_hex             TEXT,
        name                TEXT,
        labels              TEXT    DEFAULT '[]',
        query               TEXT,
        tab                 TEXT    DEFAULT 'top',
        started_at          TEXT,
        ended_at            TEXT,
        tiles_processed     INTEGER DEFAULT 0,
        influencers_new     INTEGER DEFAULT 0,
        influencers_known   INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS influencer_labels (
        influencer_id   INTEGER NOT NULL REFERENCES influencers(id) ON DELETE CASCADE,
        label           TEXT    NOT NULL,
        PRIMARY KEY (influencer_id, label)
    );

    CREATE TABLE IF NOT EXISTS content_videos (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id        INTEGER UNIQUE,
        filename        TEXT    NOT NULL UNIQUE,
        original_path   TEXT,
        source          TEXT    DEFAULT 'other',
        video_type      TEXT,
        template_key    TEXT,
        handle          TEXT,
        prompt_name     TEXT,
        input_image     TEXT,
        pet_type        TEXT,
        pet_name        TEXT,
        account_vibe    TEXT,
        follower_tier   TEXT,
        followers       INTEGER,
        width           INTEGER,
        height          INTEGER,
        orientation     TEXT,
        file_size_mb    REAL,
        file_mtime      TEXT,
        content_plan_id INTEGER,
        agent_run_id    INTEGER,
        source_account  TEXT,
        status          TEXT    DEFAULT 'ready',
        created_at      TEXT    DEFAULT (datetime('now')),
        updated_at      TEXT    DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_cv_handle  ON content_videos(handle);
    CREATE INDEX IF NOT EXISTS idx_cv_status  ON content_videos(status);

    CREATE TABLE IF NOT EXISTS content_posts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id        INTEGER NOT NULL REFERENCES content_videos(id) ON DELETE CASCADE,
        action          TEXT    NOT NULL,
        caption_used    TEXT,
        hashtags_used   TEXT,
        device          TEXT,
        source_account  TEXT,
        inject_tts      INTEGER DEFAULT 0,
        status          TEXT    DEFAULT 'uploading',
        draft_upload_at TEXT,
        draft_position  INTEGER,
        draft_tag       TEXT,
        published_at    TEXT,
        tiktok_video_id TEXT,
        tiktok_url      TEXT,
        views           INTEGER,
        likes           INTEGER,
        comments        INTEGER,
        shares          INTEGER,
        last_scraped_at TEXT,
        notes           TEXT,
        created_at      TEXT    DEFAULT (datetime('now')),
        updated_at      TEXT    DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_cp_video_id ON content_posts(video_id);
    CREATE INDEX IF NOT EXISTS idx_cp_status   ON content_posts(status);

    CREATE TABLE IF NOT EXISTS tiktok_accounts (
        handle          TEXT PRIMARY KEY,
        display_name    TEXT,
        phone_serial    TEXT,
        niche           TEXT,
        is_default      INTEGER DEFAULT 0,
        is_active       INTEGER DEFAULT 1,
        notes           TEXT,
        created_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS inbox_snapshots (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        scanned_at      TEXT NOT NULL,
        total           INTEGER DEFAULT 0,
        reply_count     INTEGER DEFAULT 0,
        seen_count      INTEGER DEFAULT 0,
        sent_count      INTEGER DEFAULT 0,
        failed_count    INTEGER DEFAULT 0,
        new_replies     INTEGER DEFAULT 0,
        device          TEXT,
        account         TEXT
    );

    CREATE TABLE IF NOT EXISTS inbox_replies (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        handle          TEXT NOT NULL UNIQUE,
        last_msg        TEXT,
        status          TEXT DEFAULT 'reply',
        unread          INTEGER DEFAULT 0,
        influencer_id   INTEGER REFERENCES influencers(id),
        outreach_updated INTEGER DEFAULT 0,
        needs_reply     INTEGER DEFAULT 1,
        first_seen_at   TEXT NOT NULL,
        last_seen_at    TEXT NOT NULL,
        snapshot_id     INTEGER REFERENCES inbox_snapshots(id)
    );

    CREATE TABLE IF NOT EXISTS post_analytics (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        content_post_id  INTEGER REFERENCES content_posts(id),
        account          TEXT,
        post_index       INTEGER,
        posted_on        TEXT,
        video_views      INTEGER,
        likes            INTEGER,
        comments         INTEGER,
        shares           INTEGER,
        bookmarks        INTEGER,
        avg_watch_time   TEXT,
        watched_full_pct TEXT,
        new_followers    INTEGER,
        traffic_sources_json TEXT,
        viewers_json     TEXT,
        engagement_json  TEXT,
        scraped_at       TEXT NOT NULL,
        UNIQUE(content_post_id, scraped_at)
    );
    """)
    conn.commit()

    # Soft migrations — ignore if column already exists
    for migration in [
        "ALTER TABLE outreach_log ADD COLUMN source TEXT DEFAULT 'bot'",
        "ALTER TABLE outreach_log ADD COLUMN source_account TEXT",
        "ALTER TABLE content_videos ADD COLUMN content_plan_id INTEGER",
        "ALTER TABLE content_videos ADD COLUMN agent_run_id INTEGER",
        "ALTER TABLE content_videos ADD COLUMN source_account TEXT",
        "ALTER TABLE content_posts ADD COLUMN source_account TEXT",
        "ALTER TABLE content_posts ADD COLUMN draft_tag TEXT",
        "ALTER TABLE inbox_snapshots ADD COLUMN account TEXT",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except sqlite3.OperationalError:
            pass


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_int(val) -> int | None:
    if val is None or str(val).strip() in ("", "-"):
        return None
    s = str(val).strip().upper().replace(",", "")
    try:
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("B"):
            return int(float(s[:-1]) * 1_000_000_000)
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _parse_metric(val) -> int | None:
    if not val:
        return None
    val = str(val).replace(",", "").strip()
    if not val:
        return None
    m = re.match(r"^([\d.]+)([KMB]?)$", val, re.IGNORECASE)
    if not m:
        return _parse_int(val)
    num = float(m.group(1))
    suffix = m.group(2).upper()
    if suffix == "K":
        return int(num * 1_000)
    if suffix == "M":
        return int(num * 1_000_000)
    if suffix == "B":
        return int(num * 1_000_000_000)
    return int(num)


# ── Influencers ───────────────────────────────────────────────────────────────

def get_influencer_id(conn: sqlite3.Connection, handle: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM influencers WHERE handle = ?", (handle.strip(),)
    ).fetchone()
    return row["id"] if row else None


def upsert_influencer(conn: sqlite3.Connection, row: dict,
                      labels: list | None = None) -> int | None:
    handle = (row.get("handle") or "").strip()
    if not handle:
        return None
    followers = _parse_int(row.get("followers") or row.get("followers_n"))
    following = _parse_int(row.get("following") or row.get("following_n"))
    total_likes = _parse_int(row.get("total_likes") or row.get("likes") or row.get("likes_n"))
    conn.execute("""
        INSERT INTO influencers
            (handle, display_name, platform, profile_url,
             followers, following, total_likes,
             bio, niche, pet_focus, caption, top_views,
             avg_views, num_videos, screenshot_path,
             source_query, scraped_at, updated_at)
        VALUES
            (:handle, :display_name, :platform, :profile_url,
             :followers, :following, :total_likes,
             :bio, :niche, :pet_focus, :caption, :top_views,
             :avg_views, :num_videos, :screenshot_path,
             :source_query, :scraped_at, :updated_at)
        ON CONFLICT(handle) DO UPDATE SET
            display_name    = COALESCE(excluded.display_name,    display_name),
            followers       = COALESCE(excluded.followers,       followers),
            following       = COALESCE(excluded.following,       following),
            total_likes     = COALESCE(excluded.total_likes,     total_likes),
            bio             = COALESCE(excluded.bio,             bio),
            niche           = COALESCE(excluded.niche,           niche),
            pet_focus       = COALESCE(excluded.pet_focus,       pet_focus),
            caption         = COALESCE(excluded.caption,         caption),
            top_views       = COALESCE(excluded.top_views,       top_views),
            avg_views       = COALESCE(excluded.avg_views,       avg_views),
            num_videos      = COALESCE(excluded.num_videos,      num_videos),
            screenshot_path = COALESCE(excluded.screenshot_path, screenshot_path),
            source_query    = COALESCE(excluded.source_query,    source_query),
            scraped_at      = COALESCE(excluded.scraped_at,      scraped_at),
            updated_at      = :updated_at
    """, {
        "handle":          handle,
        "display_name":    row.get("display_name") or None,
        "platform":        row.get("platform") or "TikTok",
        "profile_url":     row.get("profile_url") or None,
        "followers":       followers,
        "following":       following,
        "total_likes":     total_likes,
        "bio":             row.get("bio") or None,
        "niche":           row.get("niche") or None,
        "pet_focus":       row.get("pet_focus") or None,
        "caption":         row.get("caption") or None,
        "top_views":       row.get("top_views") or None,
        "avg_views":       row.get("avg_views") or None,
        "num_videos":      row.get("num_videos") or None,
        "screenshot_path": row.get("screenshot") or row.get("screenshot_path") or None,
        "source_query":    row.get("query") or row.get("source_query") or None,
        "scraped_at":      row.get("scraped_at") or None,
        "updated_at":      _now(),
    })
    conn.commit()
    inf_id = get_influencer_id(conn, handle)
    if inf_id and labels:
        for label in labels:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO influencer_labels (influencer_id, label) VALUES (?, ?)",
                    (inf_id, label),
                )
            except sqlite3.Error:
                pass
        conn.commit()
    return inf_id


# ── Outreach ──────────────────────────────────────────────────────────────────

def upsert_outreach(conn: sqlite3.Connection, influencer_id: int,
                    status: str = "not_contacted",
                    strategy_id: int | None = None,
                    deal_status: str | None = None,
                    notes: str | None = None,
                    contacted_at: str | None = None,
                    source: str = "bot",
                    source_account: str | None = None):
    now = _now()
    existing = conn.execute(
        "SELECT id FROM outreach_log WHERE influencer_id = ?", (influencer_id,)
    ).fetchone()
    if existing:
        conn.execute("""
            UPDATE outreach_log SET
                status         = ?,
                strategy_id    = COALESCE(?, strategy_id),
                deal_status    = COALESCE(?, deal_status),
                notes          = COALESCE(?, notes),
                contacted_at   = COALESCE(?, contacted_at),
                source         = ?,
                source_account = COALESCE(?, source_account),
                updated_at     = ?
            WHERE influencer_id = ?
        """, (status, strategy_id, deal_status, notes, contacted_at,
              source, source_account, now, influencer_id))
    else:
        conn.execute("""
            INSERT INTO outreach_log
                (influencer_id, strategy_id, status, deal_status, notes,
                 contacted_at, source, source_account, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (influencer_id, strategy_id, status, deal_status, notes,
              contacted_at, source, source_account, now, now))
    conn.commit()


def get_all_strategies(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM outreach_strategies WHERE is_active = 1 ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def seed_default_strategies(conn: sqlite3.Connection):
    existing = conn.execute("SELECT COUNT(*) FROM outreach_strategies").fetchone()[0]
    if existing:
        return
    conn.executemany(
        "INSERT INTO outreach_strategies (name, description, message_template) VALUES (?, ?, ?)",
        [
            ("Free credits offer",
             "Offer free Tailframe credits in exchange for a post",
             "Hey {name}! Love your content 🐾 We built an AI tool that turns pet photos into viral videos — want to try it for free? tailframe.com"),
            ("Collab ask",
             "Direct collaboration ask",
             "Hey {name}! We'd love to collab with you on Tailframe — AI pet video generation. Interested?"),
        ],
    )
    conn.commit()


# ── Crawl runs ────────────────────────────────────────────────────────────────

def create_crawl_run(conn: sqlite3.Connection, run_hex: str,
                     name: str | None, labels: list,
                     query: str, tab: str) -> int:
    cur = conn.execute("""
        INSERT INTO crawl_runs (run_hex, name, labels, query, tab, started_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (run_hex, name or None, json.dumps(labels or []), query, tab, _now()))
    conn.commit()
    return cur.lastrowid


def update_crawl_run(conn: sqlite3.Connection, run_id: int,
                     tiles_processed: int = 0,
                     influencers_new: int = 0,
                     influencers_known: int = 0):
    conn.execute("""
        UPDATE crawl_runs
        SET ended_at=?, tiles_processed=?, influencers_new=?, influencers_known=?
        WHERE id=?
    """, (_now(), tiles_processed, influencers_new, influencers_known, run_id))
    conn.commit()


# ── Content posts ─────────────────────────────────────────────────────────────

def create_content_post(conn: sqlite3.Connection, video_id: int, action: str,
                        caption: str = "", hashtags: str = "", device: str = "",
                        inject_tts: bool = False,
                        draft_position: int | None = None) -> int:
    cur = conn.execute("""
        INSERT INTO content_posts
            (video_id, action, caption_used, hashtags_used, device, inject_tts,
             status, draft_position)
        VALUES (?, ?, ?, ?, ?, ?, 'uploading', ?)
    """, (video_id, action, caption or None, hashtags or None,
          device or None, 1 if inject_tts else 0, draft_position))
    conn.commit()
    return cur.lastrowid


def update_content_post(conn: sqlite3.Connection, post_id: int, **kwargs):
    kwargs["updated_at"] = _now()
    sets = ", ".join(f"{k} = :{k}" for k in kwargs)
    kwargs["post_id"] = post_id
    conn.execute(f"UPDATE content_posts SET {sets} WHERE id = :post_id", kwargs)
    conn.commit()


def update_content_video_status(conn: sqlite3.Connection, vid_id: int, status: str):
    conn.execute(
        "UPDATE content_videos SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), vid_id),
    )
    conn.commit()


# ── Post analytics ────────────────────────────────────────────────────────────

def save_post_analytics(conn: sqlite3.Connection, post_data: dict,
                        account: str | None = None,
                        post_index: int | None = None) -> int:
    now = _now()
    posted_on = post_data.get("posted_on", "")

    cp_id = None
    if posted_on:
        _clean = posted_on.replace("Posted on", "").strip()
        iso_prefix = None
        for fmt in ("%b %d, %Y, %I:%M %p", "%b %d,%Y,%I:%M%p",
                    "%b %d, %Y, %I:%M%p", "%b %d,%Y, %I:%M %p"):
            try:
                dt = datetime.strptime(_clean, fmt)
                iso_prefix = dt.strftime("%Y-%m-%d %H:%M")
                break
            except ValueError:
                continue
        if iso_prefix:
            acct_clause = "AND source_account = ?" if account else ""
            params = (f"{iso_prefix}%",) + ((account,) if account else ())
            row = conn.execute(
                f"SELECT id FROM content_posts WHERE published_at LIKE ? {acct_clause} ORDER BY id DESC LIMIT 1",
                params,
            ).fetchone()
            if row:
                cp_id = row[0]
                conn.execute("""
                    UPDATE content_posts SET
                        views=?, likes=?, comments=?, shares=?, last_scraped_at=?
                    WHERE id=?
                """, (_parse_metric(post_data.get("video_views")),
                      _parse_metric(post_data.get("likes")),
                      _parse_metric(post_data.get("comments")),
                      _parse_metric(post_data.get("shares")),
                      now, cp_id))

    cur = conn.execute("""
        INSERT INTO post_analytics
            (posted_on, post_index, content_post_id, account,
             video_views, likes, comments, shares, bookmarks,
             avg_watch_time, watched_full_pct, new_followers,
             traffic_sources_json, viewers_json, engagement_json, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (posted_on, post_index, cp_id, account,
          _parse_metric(post_data.get("video_views")),
          _parse_metric(post_data.get("likes")),
          _parse_metric(post_data.get("comments")),
          _parse_metric(post_data.get("shares")),
          _parse_metric(post_data.get("bookmarks")),
          post_data.get("avg_watch_time"),
          post_data.get("watched_full_pct"),
          _parse_metric(post_data.get("new_followers")),
          json.dumps(post_data.get("traffic_sources", {})),
          json.dumps(post_data.get("viewers", {})),
          json.dumps(post_data.get("engagement", {})),
          now))
    conn.commit()
    return cur.lastrowid
