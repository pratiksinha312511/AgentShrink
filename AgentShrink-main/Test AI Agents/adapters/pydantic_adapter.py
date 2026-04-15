"""
PydanticAI Adapter for AgentShrink Gateway + Sarvam AI
=======================================================
Original: OpenAIProvider(base_url='https://api.tokenfactory.nebius.com/v1', api_key=...)
Adapted:  OpenAIProvider(base_url='http://127.0.0.1:8100/v1', api_key='project-token')

Works for: pydantic_starter and any PydanticAI-based agent
"""
import os
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")


def create_sarvam_model(model_id: str = "sarvam-m") -> OpenAIModel:
    return OpenAIModel(
        model_name=model_id,
        provider=OpenAIProvider(
            base_url=GATEWAY_URL,
            api_key=GATEWAY_KEY,
        ),
    )


# --- Example: Adapt pydantic_starter ---
# BEFORE:
#   model = OpenAIModel(
#       model_name='meta-llama/Meta-Llama-3.1-70B-Instruct',
#       provider=OpenAIProvider(base_url='https://api.tokenfactory.nebius.com/v1',
#                               api_key=os.environ['NEBIUS_API_KEY'])
#   )
#
# AFTER:
#   model = create_sarvam_model("sarvam-m")

if __name__ == "__main__":
    model = create_sarvam_model("sarvam-m")
    agent = Agent(
        model=model,
        system_prompt="You are a helpful assistant routed through AgentShrink gateway.",
    )
    result = agent.run_sync("What is AgentShrink?")
    print(result.data)
