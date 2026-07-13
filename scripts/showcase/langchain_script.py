"""LangChain × Ghost — subreddit harvester. Claude Code (your own subscription,
no cloud API key) drives the phone through LangChain tools and writes to SQLite."""
import json, os, re, sqlite3, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from integrations.langchain import ghost_langchain_tools
from langchain_claude_code import ChatClaudeCode

DB, DEVICE = Path(__file__).with_name("posts.db"), os.environ.get("GHOST_DEVICE") or os.environ["ANDROID_SERIAL"]
SEED = ["LocalLLaMA", "MachineLearning"]


def main():
    subreddit = next_pending()
    if not subreddit:
        print("all subreddits profiled"); return
    print(f"harvesting r/{subreddit} …")
    llm   = ChatClaudeCode(model="sonnet", permission_mode="bypassPermissions",
                           disallowed_tools=["Bash", "WebFetch", "WebSearch"])  # phone only, no shortcuts
    tools = ghost_langchain_tools(DEVICE)          # 53 phone tools, as an in-process MCP
    task  = (f"Force-stop and reopen the Reddit app fresh, then navigate to r/{subreddit}. "
             f"Read the title, upvotes and comment count of the first 2 posts. Reply with "
             f"ONLY a JSON array in a ```json fenced block.")
    posts = parse(llm.bind_tools(tools).invoke(task).content)   # Claude Code drives the phone
    save(subreddit, posts)
    print(f"✓ r/{subreddit}: {len(posts)} posts → {DB.name}")


# --- plumbing ---------------------------------------------------------------
def next_pending():
    row = _db().execute("SELECT subreddit FROM subs WHERE status='pending' LIMIT 1").fetchone()
    return row[0] if row else None

def save(subreddit, posts):
    conn = _db()
    conn.executemany("INSERT INTO posts VALUES (?,?,?,?)",
                     [(subreddit, p.get("title"), p.get("upvotes"), p.get("comments")) for p in posts])
    conn.execute("UPDATE subs SET status='done' WHERE subreddit=?", (subreddit,))
    conn.commit()

def parse(out):
    for cand in (out.split("```json")[-1].split("```")[0].strip(), out.strip()):
        try:    return json.loads(cand)
        except: pass
    m = re.search(r"\[.*\]", out, re.DOTALL)   # any JSON array anywhere
    return json.loads(m.group(0)) if m else []

def _db():
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS subs(subreddit PRIMARY KEY, status)")
    conn.execute("CREATE TABLE IF NOT EXISTS posts(subreddit, title, upvotes, comments)")
    conn.executemany("INSERT OR IGNORE INTO subs VALUES (?,'pending')", [(s,) for s in SEED])
    conn.commit(); return conn

if __name__ == "__main__": main()
