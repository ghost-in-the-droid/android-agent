# On-device Gemma — no cloud round-trip
# android-agent up --provider gemma
from gitd.agent import Agent

agent = Agent(provider="gemma")  # runs on the phone
agent.run("open the calculator and compute an 18% tip on 42")
