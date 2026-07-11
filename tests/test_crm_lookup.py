"""Tests for the read-only local CRM lookup service (gitd/services/crm_lookup.py)."""

from gitd.db import create_tables, get_connection
from gitd.services.crm_lookup import crm_list_unread_messages, crm_lookup_contact


def _seeded_db(tmp_path):
    db_path = tmp_path / "gitd.db"
    conn = get_connection(db_path)
    try:
        create_tables(conn)
        conn.execute(
            """
            INSERT INTO influencers
                (id, handle, followers, following, total_likes, bio, niche, caption, source_query, scraped_at)
            VALUES
                (1, '@demo', 1200, 300, 6000, 'Creator bio', 'pets', 'First line\nSecond line', '#pets', '2026-06-01')
            """
        )
        conn.execute("INSERT INTO outreach_strategies (id, name) VALUES (7, 'Creator collab')")
        conn.execute(
            """
            INSERT INTO outreach_log
                (influencer_id, strategy_id, status, deal_status, contacted_at, source_account, notes)
            VALUES
                (1, 7, 'contacted', 'negotiating', '2026-06-02', 'brandacct', 'Asked for rates')
            """
        )
        conn.execute(
            """
            INSERT INTO inbox_replies
                (handle, last_msg, status, unread, influencer_id, first_seen_at, last_seen_at)
            VALUES
                ('demo', 'Sounds good', 'reply', 2, 1, '2026-06-03', '2026-06-04')
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_crm_lookup_contact_returns_fact_sheet_with_history_and_conversation(tmp_path):
    db_path = _seeded_db(tmp_path)

    result = crm_lookup_contact("demo", db_path=db_path)

    assert "HANDLE:    @demo" in result
    assert "FOLLOWERS: 1,200" in result
    assert "CONTACT STATUS:" in result
    assert "Contacted via: @brandacct" in result
    assert "Last msg:   Sounds good" in result
    assert "Unread:     2" in result


def test_crm_lookup_contact_handles_missing_contact(tmp_path):
    db_path = tmp_path / "gitd.db"
    conn = get_connection(db_path)
    try:
        create_tables(conn)
        conn.commit()
    finally:
        conn.close()

    assert crm_lookup_contact("nobody", db_path=db_path) == "No contact record for @nobody"


def test_crm_list_unread_messages_returns_recent_unread_only(tmp_path):
    db_path = tmp_path / "gitd.db"
    conn = get_connection(db_path)
    try:
        create_tables(conn)
        conn.execute(
            """
            INSERT INTO inbox_replies
                (handle, last_msg, status, unread, first_seen_at, last_seen_at)
            VALUES
                ('newer', 'Latest reply', 'reply', 3, '2026-06-01', '2026-06-05'),
                ('read',  'Already handled', 'reply', 0, '2026-06-01', '2026-06-06'),
                ('older', 'Earlier reply', 'reply', 1, '2026-06-01', '2026-06-02')
            """
        )
        conn.commit()
    finally:
        conn.close()

    result = crm_list_unread_messages(db_path=db_path)

    assert result.startswith("2 unread:")
    assert "read" not in result.split("unread:")[1].split("\n")[0]  # zero-unread row excluded
    assert result.index("newer") < result.index("older")  # recency order


def test_crm_list_unread_messages_empty(tmp_path):
    db_path = tmp_path / "gitd.db"
    conn = get_connection(db_path)
    try:
        create_tables(conn)
        conn.commit()
    finally:
        conn.close()

    assert crm_list_unread_messages(db_path=db_path) == "0 unread"
