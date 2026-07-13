"""LangChain × Ghost — per-run subreddit harvester. Drives the phone via LOCAL
Claude Code (no cloud API key — your own subscription) through LangChain tools,
reads the top-2 post stats, writes to DB."""
import json, os, re, sqlite3, subprocess, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from integrations.langchain import ghost_langchain_tools
from langchain_claude_code import ChatClaudeCode

DB, DEVICE = Path(__file__).with_name("posts.db"), os.environ.get("GHOST_DEVICE") or os.environ["ANDROID_SERIAL"]
SEED = ["LocalLLaMA", "MachineLearning"]

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
    llm  = ChatClaudeCode(model="sonnet", permission_mode="bypassPermissions")  # local Claude Code, no API key
    tools = ghost_langchain_tools(DEVICE)  # 53 phone tools, exposed to Claude Code as an in-process MCP
    task  = f"Open the Reddit app and navigate to r/{subreddit}. Read the title, upvote count and comment count of the first 2 posts. Reply with ONLY a JSON array in a ```json fenced block: [{{\"title\": ..., \"upvotes\": ..., \"comments\": ...}}, {{\"title\": ..., \"upvotes\": ..., \"comments\": ...}}]"
    out  = llm.bind_tools(tools).invoke(task).content  # Claude Code IS the agent loop
    txt = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL)
    for cand in (txt.split("```json")[-1].split("```")[0].strip(), txt.strip()):
        try:    return json.loads(cand)
        except: pass
    m = re.search(r"\[.*\]", txt, re.DOTALL)  # first JSON array anywhere
    return json.loads(m.group(0)) if m else json.loads(txt)

if __name__ == "__main__": main()
