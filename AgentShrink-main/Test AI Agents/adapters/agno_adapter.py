"""
Agno Framework Adapter for AgentShrink Gateway + Sarvam AI
==========================================================
Original: from agno.models.nebius import Nebius
Adapted:  from agno.models.openai import OpenAIChat  (points to AgentShrink gateway)

Works for: agno_starter, agno_ai_examples, finance_agent, agno_ui_agent,
           agno_memory_agent, agentic_rag, deep_researcher, finance_service_agent,
           content_team_agent, youtube_trend_agent
"""
import os
from agno.agent import Agent
from agno.models.openai import OpenAIChat

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")

def create_sarvam_model(model_id: str = "sarvam-m") -> OpenAIChat:
    return OpenAIChat(
        id=model_id,
        base_url=GATEWAY_URL,
        api_key=GATEWAY_KEY,
    )

# --- Example: Adapt agno_starter HackerNews agent ---
# BEFORE:
#   from agno.models.nebius import Nebius
#   model=Nebius(id="Qwen/Qwen3-30B-A3B", api_key=os.getenv("NEBIUS_API_KEY"))
#
# AFTER:
#   model=create_sarvam_model("sarvam-m")

if __name__ == "__main__":
    agent = Agent(
        name="AgentShrink Test Agent",
        instructions=["You are a helpful assistant routed through AgentShrink gateway."],
        model=create_sarvam_model("sarvam-m"),
        markdown=True,
    )
    agent.print_response("Hello! What can you do?")
