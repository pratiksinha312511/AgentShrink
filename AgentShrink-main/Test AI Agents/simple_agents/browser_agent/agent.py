"""
Browser Automation Agent — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/simple_ai_agents/browser_agent/main.py
"""
import asyncio
import os
from browser_use.llm import ChatOpenAI
from browser_use import Agent

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


async def run_search():
    agent = Agent(
        task="Go to flipkart.com, search for laptop, sort by best rating, and give me the price of the first result in markdown",
        llm=ChatOpenAI(
            base_url=GATEWAY_URL,
            model="sarvam-m",
            api_key=GATEWAY_KEY,
        ),
        use_vision=False,
    )
    await agent.run()


if __name__ == "__main__":
    asyncio.run(run_search())
