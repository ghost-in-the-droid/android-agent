"""LangChain × Ghost — per-run X profile harvester. Each run picks the next
pending @handle from SQLite, drives the phone via ReAct, writes stats back."""
import json, os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from integrations.langchain import ghost_langchain_tools
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

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
    llm    = ChatOpenAI(model="gpt-4o-mini", base_url="https://openrouter.ai/api/v1", api_key=_env["OPENROUTER_API_KEY"])
    prompt = PromptTemplate.from_template("Tools: {tools} | {tool_names}\nTask: {input}\n{agent_scratchpad}")
    tools  = ghost_langchain_tools(DEVICE)  # ← 40+ phone tools
    agent  = AgentExecutor(agent=create_react_agent(llm, tools, prompt),
                           tools=tools, max_iterations=12, handle_parsing_errors=True)  # ← any LLM
    raw    = agent.invoke({"input": f"Open X, search @{username}. OCR follower count, bio, most recent post. Return JSON: {{followers, bio, top_post}}"})["output"]
    return json.loads(raw.split("```json")[-1].split("```")[0].strip())

if __name__ == "__main__": main()
