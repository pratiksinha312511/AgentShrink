from __future__ import annotations

import os
import uuid
from openai import OpenAI


def run_youtube_trend_gateway_demo(prompt: str, *, run_id: str | None = None) -> tuple[str, str]:
    """
    Minimal adaptation of:
      memory_agents/youtube_trend_agent/app.py

    Exact Get Started-page integration changes:
    - swap OpenAI-compatible base_url to AgentShrink gateway
    - swap api_key to AgentShrink gateway key
    - keep standard OpenAI client usage
    """
    gateway_base_url = os.getenv("AGENTSHRINK_GATEWAY_BASE_URL", "http://127.0.0.1:8152/v1")
    gateway_api_key = os.getenv("AGENTSHRINK_GATEWAY_API_KEY", "agentshrink-local")
    gateway_model = os.getenv("AGENTSHRINK_GATEWAY_MODEL", "mock-model")
    resolved_run_id = run_id or f"youtube-trend-{uuid.uuid4().hex[:8]}"

    client = OpenAI(
        base_url=gateway_base_url,
        api_key=gateway_api_key,
        default_headers={
            "x-agentshrink-node": "youtube_trend_gateway_demo",
            "x-agentshrink-run-id": resolved_run_id,
        },
    )

    response = client.chat.completions.create(
        model=gateway_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a YouTube trend analysis assistant. "
                    "Suggest useful content directions based on the user's request."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    content = (response.choices[0].message.content or "").strip()
    return content, resolved_run_id
