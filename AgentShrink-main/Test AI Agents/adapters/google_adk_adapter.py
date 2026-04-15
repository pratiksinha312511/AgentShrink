"""
Google ADK + LiteLLM Adapter for AgentShrink Gateway + Sarvam AI
=================================================================
Original: LiteLlm(model="openai/...", api_base="https://api.studio.nebius.ai/v1")
Adapted:  LiteLlm(model="openai/sarvam-m", api_base="http://127.0.0.1:8100/v1")

Works for: google_adk_starter, trend_analyzer_agent, conference_talk_abstract_generator
"""
import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


def create_sarvam_model(model_id: str = "sarvam-m") -> LiteLlm:
    return LiteLlm(
        model=f"openai/{model_id}",
        api_base=GATEWAY_URL,
        api_key=GATEWAY_KEY,
    )


# --- Example: Adapt google_adk_starter ---
# BEFORE:
#   model = LiteLlm(model="openai/meta-llama/Meta-Llama-3.1-8B-Instruct",
#                    api_base=os.getenv("NEBIUS_API_BASE"),
#                    api_key=os.getenv("NEBIUS_API_KEY"))
#
# AFTER:
#   model = create_sarvam_model("sarvam-m")

if __name__ == "__main__":
    model = create_sarvam_model("sarvam-m")
    root_agent = Agent(
        name="TestAgent",
        model=model,
        description="Test agent routed through AgentShrink.",
        instruction="You are a helpful assistant.",
        tools=[],
    )
    print("Google ADK agent configured with AgentShrink gateway + Sarvam AI")
