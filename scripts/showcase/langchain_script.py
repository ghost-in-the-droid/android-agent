"""LangChain × Ghost — per-run X profile harvester. Each run picks the next
pending @handle from SQLite, drives the phone via ReAct, writes stats back."""
import json, os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from integrations.langchain import ghost_langchain_tools
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

DB, DEVICE = Path(__file__).with_name("users.db"), os.environ.get("GHOST_DEVICE") or os.environ["ANDROID_SERIAL"]
SEED = ["karpathy", "ylecun", "sama", "emostaque", "hwchung16"]
_env  = dict(l.split("=",1) for l in (Path(__file__).parents[2]/".env").read_text().splitlines() if "=" in l and not l.startswith("#"))

def db():
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS users(username PRIMARY KEY, status, followers, bio, top_post)")
    conn.executemany("INSERT OR IGNORE INTO users(username,status) VALUES(?,'pending')", [(u,) for u in SEED])
    conn.commit(); return conn

def show(conn):
    print(f"{'username':<16}{'status':<10}{'followers':<12}bio")
    for row in conn.execute("SELECT username,status,followers,substr(coalesce(bio,''),1,40) FROM users"):
        print(f"{row[0]:<16}{row[1]:<10}{str(row[2] or '-'):<12}{row[3] or ''}")

def main():
    conn = db()
    if "--stats" in sys.argv: show(conn); return
    pending = conn.execute("SELECT username FROM users WHERE status='pending' LIMIT 1").fetchone()
    if not pending: print("all done"); show(conn); return
    username = pending[0]
    print(f"harvesting @{username}...")
    data = harvest(username)
    conn.execute("UPDATE users SET status='done',followers=?,bio=?,top_post=? WHERE username=?",
                 (data.get("followers"), data.get("bio"), data.get("top_post"), username))
    conn.commit(); print(f"✓ @{username}: {data.get('followers')} followers")

def harvest(username):
    llm   = ChatAnthropic(model="claude-sonnet-5",
                          api_key=_env["ANTHROPIC_API_KEY"], max_tokens=3072)
    tools = ghost_langchain_tools(DEVICE)  # ← 40+ phone tools
    agent = create_react_agent(llm, tools)  # ← any LLM
    task  = f"Open the X app and find the public profile of @{username}. Steps: (1) use launch_app to open com.twitter.android, (2) take a screenshot to see what's on screen — if you see a compose/reply box or draft dialog, tap BACK immediately and do NOT type anything, (3) tap the Search icon (magnifying glass), (4) type '@{username}' and search, (5) tap 'People' filter tab, (6) tap the account named '{username}' with the most followers to open their profile, (7) screenshot and OCR the profile page to read their follower count, bio, and first post. Reply with ONLY a JSON object in a ```json fenced block: {{followers, bio, top_post}}"
    out   = agent.invoke({"messages": [("user", task)]}, {"recursion_limit": 45})["messages"][-1].content
    try:    return json.loads(out.split("```json")[-1].split("```")[0].strip())
    except: return json.loads(out)

if __name__ == "__main__": main()
