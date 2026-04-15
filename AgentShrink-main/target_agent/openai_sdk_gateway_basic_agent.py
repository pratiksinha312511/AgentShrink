from __future__ import annotations

import os
import uuid

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from dotenv import load_dotenv

load_dotenv()
set_tracing_disabled(disabled=True)


def build_gateway_agent(*, node_name: str = "openai_sdk_gateway_demo", run_id: str | None = None):
    run_id = run_id or f"openai-sdk-{uuid.uuid4().hex[:8]}"
    api_key = os.getenv("AGENTSHRINK_GATEWAY_API_KEY", "agentshrink-local")
    base_url = os.getenv("AGENTSHRINK_GATEWAY_BASE_URL", "http://127.0.0.1:8100/v1")
    model_name = os.getenv("AGENTSHRINK_GATEWAY_MODEL", "mock-model")

    model = OpenAIChatCompletionsModel(
        model=model_name,
        openai_client=AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers={
                "x-agentshrink-node": node_name,
                "x-agentshrink-run-id": run_id,
            },
        ),
    )

    agent = Agent(
        name="Assistant",
        instructions=(
            "You are an expert doctor specializing in nutrition and preventive care. "
            "Provide evidence-based medical advice and always include a brief disclaimer."
        ),
        model=model,
    )
    return agent, run_id


def run_gateway_demo(prompt: str, *, node_name: str = "openai_sdk_gateway_demo", run_id: str | None = None):
    agent, run_id = build_gateway_agent(node_name=node_name, run_id=run_id)
    result = Runner.run_sync(agent, prompt)
    return result, run_id
