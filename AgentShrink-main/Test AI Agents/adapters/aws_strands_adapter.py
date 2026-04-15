"""
AWS Strands + LiteLLM Adapter for AgentShrink Gateway + Sarvam AI
==================================================================
Original: LiteLLMModel(model_id="nebius/...", client_args={"api_key": ...})
Adapted:  LiteLLMModel(model_id="openai/sarvam-m", client_args={"api_key": ..., "api_base": gateway})

Works for: aws_strands_starter, aws_strands_agent_with_memori
"""
import os
from strands import Agent
from strands.models.litellm import LiteLLMModel

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


def create_sarvam_model(model_id: str = "sarvam-m") -> LiteLLMModel:
    return LiteLLMModel(
        client_args={
            "api_key": GATEWAY_KEY,
            "api_base": GATEWAY_URL,
        },
        model_id=f"openai/{model_id}",
        params={
            "max_tokens": 1000,
            "temperature": 0.7,
        },
    )


# --- Example: Adapt aws_strands_starter ---
# BEFORE:
#   model = LiteLLMModel(
#       client_args={"api_key": os.getenv("NEBIUS_API_KEY")},
#       model_id="nebius/deepseek-ai/DeepSeek-V3-0324",
#   )
#
# AFTER:
#   model = create_sarvam_model("sarvam-m")

if __name__ == "__main__":
    model = create_sarvam_model("sarvam-m")
    agent = Agent(
        system_prompt="You are a helpful assistant.",
        model=model,
    )
    response = agent("What is AgentShrink?")
    print(response)
