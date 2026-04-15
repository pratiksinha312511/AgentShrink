from __future__ import annotations

import os
import uuid
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()


class GatewayStudioChat:
    """
    Minimal raw-HTTP adaptation of simple_ai_agents/nebius_chat/app.py
    that points to AgentShrink's OpenAI-compatible gateway.
    """

    def __init__(self):
        self.api_key = os.getenv("AGENTSHRINK_GATEWAY_API_KEY", "agentshrink-local")
        self.base_url = os.getenv("AGENTSHRINK_GATEWAY_BASE_URL", "http://127.0.0.1:8100/v1")
        self.models = {
            "Mock Model": os.getenv("AGENTSHRINK_GATEWAY_MODEL", "mock-model"),
        }
        self.conversation_history = []
        self.custom_instruction = "You are a helpful AI assistant."

    def send_message(
        self,
        message: str,
        model: str | None = None,
        temperature: float = 0.6,
        max_tokens: int = 512,
        top_p: float = 0.95,
        node_name: str = "nebius_raw_gateway_demo",
        run_id: str | None = None,
    ):
        if not self.api_key:
            return None, "API key not configured", {}

        run_id = run_id or f"nebius-raw-{uuid.uuid4().hex[:8]}"
        model = model or self.models["Mock Model"]

        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "x-agentshrink-node": node_name,
                "x-agentshrink-run-id": run_id,
            }

            messages = []
            if self.custom_instruction:
                messages.append({"role": "system", "content": self.custom_instruction})
            for entry in self.conversation_history[-5:]:
                messages.append({"role": "user", "content": entry["user"]})
                messages.append({"role": "assistant", "content": entry["assistant"]})
            messages.append({"role": "user", "content": message})

            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }

            response = requests.post(url, json=payload, headers=headers, timeout=120)
            if response.status_code == 200:
                result = response.json()
                assistant_response = result["choices"][0]["message"]["content"].strip()
                usage = result.get("usage", {})
                conversation_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "user": message,
                    "assistant": assistant_response,
                    "model": model,
                    "temperature": temperature,
                    "run_id": run_id,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                }
                self.conversation_history.append(conversation_entry)
                return assistant_response, None, conversation_entry["usage"]
            return None, f"Gateway Error: {response.status_code} - {response.text}", {}
        except Exception as exc:
            return None, f"Error: {exc}", {}
