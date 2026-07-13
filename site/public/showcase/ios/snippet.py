# Same agent, now with an iPhone attached
# android-agent devices
from gitd.agent import Agent

agent = Agent(device="iphone-15-pro")  # Appium + WebDriverAgent
agent.run("open Settings and enable Do Not Disturb")
