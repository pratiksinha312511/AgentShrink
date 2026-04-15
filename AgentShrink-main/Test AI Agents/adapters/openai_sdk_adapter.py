"""
OpenAI Agents SDK Adapter for AgentShrink Gateway + Sarvam AI
==============================================================
Original: AsyncOpenAI(base_url="https://api.tokenfactory.nebius.com/v1", api_key=...)
Adapted:  AsyncOpenAI(base_url="http://127.0.0.1:8100/v1", api_key="project-token")

Works for: openai_agents_sdk, arxiv_researcher_agent_with_memori,
           nebius_chat, and any OpenAI SDK-based agent
"""
import os
import asyncio
from openai import AsyncOpenAI, OpenAI
from agents import (
    Agent, Model, ModelProvider, OpenAIChatCompletionsModel,
    RunConfig, Runner, set_tracing_disabled,
)

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")

client = AsyncOpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)
set_tracing_disabled(disabled=True)


class SarvamModelProvider(ModelProvider):
    def get_model(self, model_name: str | None) -> Model:
        return OpenAIChatCompletionsModel(
            model=model_name or "sarvam-m",
            openai_client=client,
        )


SARVAM_PROVIDER = SarvamModelProvider()

# --- Example: Adapt openai_agents_sdk starter ---
# BEFORE:
#   client = AsyncOpenAI(base_url="https://api.tokenfactory.nebius.com/v1", api_key=nebius_key)
#   run_config=RunConfig(model_provider=CUSTOM_MODEL_PROVIDER)
#
# AFTER:
#   client = AsyncOpenAI(base_url="http://127.0.0.1:8100/v1", api_key="project-token")
#   run_config=RunConfig(model_provider=SARVAM_PROVIDER)

async def main():
    agent = Agent(
        name="AgentShrink Test",
        instructions="You are a helpful assistant routed through AgentShrink.",
    )
    result = await Runner.run(
        agent,
        "Explain what AgentShrink does in one sentence.",
        run_config=RunConfig(model_provider=SARVAM_PROVIDER),
    )
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
