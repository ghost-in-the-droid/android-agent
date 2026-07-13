from gitd.db import create_tables, get_connection
from gitd.services.marketing_lookup import list_unread_leads, lookup_lead


def test_lookup_lead_returns_fact_sheet_with_outreach_and_inbox(tmp_path):
    db_path = tmp_path / "gitd.db"
    conn = get_connection(db_path)
    try:
        create_tables(conn)
        conn.execute(
            """
            INSERT INTO influencers
                (id, handle, followers, following, total_likes, bio, niche, caption, source_query, scraped_at)
            VALUES
                (1, '@demo', 1200, 300, 6000, 'Pet creator', 'dogs', 'First line\nSecond line', '#dogs', '2026-06-01')
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

    result = lookup_lead("demo", db_path=db_path)

    assert "HANDLE:    @demo" in result
    assert "FOLLOWERS: 1,200" in result
    assert "ENGAGEMENT: 5.0 likes/follower" in result
    assert "Strategy:  Creator collab" in result
    assert "Sent from: @brandacct" in result
    assert "Last msg:  Sounds good" in result


def test_list_unread_leads_returns_recent_unread(tmp_path):
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
                ('read', 'Already handled', 'reply', 0, '2026-06-01', '2026-06-06'),
                ('older', 'Older reply', 'reply', 1, '2026-06-01', '2026-06-02')
            """
        )
        conn.commit()
    finally:
        conn.close()

    result = list_unread_leads(db_path=db_path)

    assert result.splitlines()[0] == "2 unread:"
    assert "[3] newer" in result
    assert "[1] older" in result
    assert "[0] read" not in result
    assert "Already handled" not in result
    assert result.index("newer") < result.index("older")
