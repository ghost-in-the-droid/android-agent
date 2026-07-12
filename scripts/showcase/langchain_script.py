"""LangChain × Ghost — X profile harvester. Reads pending @handles from SQLite,
drives the phone via a ReAct agent, writes back followers/bio/top-post."""
import json, os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from integrations.langchain import ghost_langchain_tools
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

DB = Path(__file__).with_name("users.db")
SEED = ["karpathy", "ylecun", "sama", "emostaque", "hwchung16"]
DEVICE = os.environ["GHOST_DEVICE"]

def db():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS users(username PRIMARY KEY, status, followers, bio, top_post)")
    for u in SEED:
        c.execute("INSERT OR IGNORE INTO users(username, status) VALUES (?, 'pending')", (u,))
    c.commit(); return c

def show(c):
    print(f"{'username':<16}{'status':<10}{'followers':<12}bio")
    for r in c.execute("SELECT username, status, followers, substr(coalesce(bio,''),1,40) FROM users"):
        print(f"{r[0]:<16}{r[1]:<10}{str(r[2] or '-'):<12}{r[3] or ''}")

def harvest(username):
    llm = ChatOpenAI(model="gpt-4o-mini", base_url="https://openrouter.ai/api/v1",
                     api_key=os.environ["OPENROUTER_API_KEY"])
    tools = ghost_langchain_tools(DEVICE)
    prompt = PromptTemplate.from_template(
        "You have phone tools. {tools}\n\nTools: {tool_names}\n\nTask: {input}\n\n{agent_scratchpad}")
    exe = AgentExecutor(agent=create_react_agent(llm, tools, prompt), tools=tools,
                        max_iterations=12, handle_parsing_errors=True)
    out = exe.invoke({"input": f"Open X, search @{username}. OCR their follower count, bio, "
                              f"and most recent post. Return JSON: {{followers, bio, top_post}}"})
    return json.loads(out["output"].split("```json")[-1].split("```")[0].strip())

def main():
    c = db()
    if "--stats" in sys.argv: show(c); return
    row = c.execute("SELECT username FROM users WHERE status='pending' LIMIT 1").fetchone()
    if not row: print("done: no pending users"); show(c); return
    u = row[0]; print(f"harvesting @{u}...")
    d = harvest(u)
    c.execute("UPDATE users SET status='done', followers=?, bio=?, top_post=? WHERE username=?",
              (d.get("followers"), d.get("bio"), d.get("top_post"), u))
    c.commit(); print(f"✓ @{u}: {d.get('followers')} followers")

if __name__ == "__main__":
    main()
