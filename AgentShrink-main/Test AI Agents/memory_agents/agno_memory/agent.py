"""
Memory Agent (Agno) — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/memory_agents/agno_memory_agent
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAIChat

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")

agent = Agent(
    name="Memory Agent",
    model=OpenAIChat(id="sarvam-m", base_url=GATEWAY_URL, api_key=GATEWAY_KEY),
    instructions=["You are a helpful assistant with persistent memory. Remember user preferences and context."],
    markdown=True,
    # memory=True,
)

if __name__ == "__main__":
    agent.print_response("My name is Arun and I work on AI systems. Remember this.")
    agent.print_response("What is my name and what do I work on?")
