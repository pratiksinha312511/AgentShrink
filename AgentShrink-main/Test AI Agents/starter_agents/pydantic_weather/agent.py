"""
PydanticAI Weather Agent — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/starter_ai_agents/pydantic_starter/main.py
"""
import os
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")

model = OpenAIModel(
    model_name="sarvam-m",
    provider=OpenAIProvider(
        base_url=GATEWAY_URL,
        api_key=GATEWAY_KEY,
    ),
)

agent = Agent(
    model=model,
    tools=[duckduckgo_search_tool()],
    system_prompt="You are a weather assistant. Use DuckDuckGo to find the current weather forecast.",
)

if __name__ == "__main__":
    city = "Mumbai"
    result = agent.run_sync(f"What is the weather forecast for {city} today?")
    print(f"Weather forecast for {city}:")
    print(result.data)
