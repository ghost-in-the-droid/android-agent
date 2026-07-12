"""LangChain × Ghost — per-run subreddit harvester. Each run picks the next
pending subreddit, reads the top-2 post stats via ReAct, writes to DB."""
import json, os, sqlite3, subprocess, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from integrations.langchain import ghost_langchain_tools
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

DB, DEVICE = Path(__file__).with_name("posts.db"), os.environ.get("GHOST_DEVICE") or os.environ["ANDROID_SERIAL"]
SEED = ["LocalLLaMA", "MachineLearning"]
_env  = dict(l.split("=",1) for l in (Path(__file__).parents[2]/".env").read_text().splitlines() if "=" in l and not l.startswith("#"))

def db():
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS subs(subreddit PRIMARY KEY, status)")
    conn.execute("CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, subreddit, title, upvotes, comments)")
    conn.executemany("INSERT OR IGNORE INTO subs(subreddit,status) VALUES(?,'pending')", [(s,) for s in SEED])
    conn.commit(); return conn

def show(conn):
    print(f"{'subreddit':<20}{'upvotes':<10}{'comments':<10}title")
    for row in conn.execute("SELECT subreddit,upvotes,comments,substr(coalesce(title,''),1,45) FROM posts ORDER BY subreddit"):
        print(f"{row[0]:<20}{str(row[1] or '-'):<10}{str(row[2] or '-'):<10}{row[3] or ''}")

def main():
    conn = db()
    if "--stats" in sys.argv: show(conn); return
    pending = conn.execute("SELECT subreddit FROM subs WHERE status='pending' LIMIT 1").fetchone()
    if not pending: print("all done"); show(conn); return
    subreddit = pending[0]
    print(f"harvesting r/{subreddit}...")
    posts = harvest(subreddit)
    for p in posts:
        conn.execute("INSERT INTO posts(subreddit,title,upvotes,comments) VALUES(?,?,?,?)",
                     (subreddit, p.get("title"), p.get("upvotes"), p.get("comments")))
    conn.execute("UPDATE subs SET status='done' WHERE subreddit=?", (subreddit,))
    conn.commit(); print(f"✓ r/{subreddit}: {len(posts)} posts harvested")

def harvest(subreddit):
    subprocess.run(["adb", "-s", DEVICE, "shell", "am", "force-stop",
                    "com.reddit.frontpage"], capture_output=True)
    llm   = ChatOpenAI(model="anthropic/claude-sonnet-5", base_url="https://openrouter.ai/api/v1",
                       api_key=_env["OPENROUTER_API_KEY"], max_tokens=3072)
    tools = ghost_langchain_tools(DEVICE)  # ← 40+ phone tools
    agent = create_react_agent(llm, tools)  # ← any LLM
    task  = f"1. Open the Reddit app and navigate to r/{subreddit}\n2. Read the title, upvote count and comment count of the first 2 posts\nReply with ONLY a JSON array in a ```json fenced block: [{{\"title\": ..., \"upvotes\": ..., \"comments\": ...}}, {{\"title\": ..., \"upvotes\": ..., \"comments\": ...}}]"
    out   = agent.invoke({"messages": [("user", task)]}, {"recursion_limit": 45})["messages"][-1].content
    try:    return json.loads(out.split("```json")[-1].split("```")[0].strip())
    except: return json.loads(out)

if __name__ == "__main__": main()
