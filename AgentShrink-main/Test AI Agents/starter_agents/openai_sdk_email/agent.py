"""
OpenAI Agents SDK Email/Haiku Agent — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/starter_ai_agents/openai_agents_sdk/main.py
"""
import asyncio
import os
from openai import AsyncOpenAI
from agents import (
    Agent, Model, ModelProvider, OpenAIChatCompletionsModel,
    RunConfig, Runner, function_tool, set_tracing_disabled,
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


@function_tool
def send_email(to: str, subject: str, body: str):
    """Sends an email (mock for testing)."""
    print(f"[MOCK] Sending email to {to}: {subject}")
    return {"status": "success", "message_id": "mock-id-123"}


async def main():
    agent = Agent(
        name="Assistant",
        instructions="You only respond in haikus.",
        tools=[send_email],
    )
    result = await Runner.run(
        agent,
        "Send an email to test@example.com with subject 'Hello' and body 'Test from AgentShrink'",
        run_config=RunConfig(model_provider=SARVAM_PROVIDER),
    )
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
