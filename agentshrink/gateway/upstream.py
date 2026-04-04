"""Upstream provider abstraction for the AgentShrink gateway."""

from __future__ import annotations

import os
import time
from typing import Any, Iterator


class OpenAICompatibleUpstream:
    """Minimal upstream interface using the OpenAI SDK for compatible providers."""

    def __init__(self, provider: str | None = None):
        self.provider = (provider or os.getenv("AGENTSHRINK_GATEWAY_UPSTREAM_PROVIDER") or os.getenv("TARGET_AGENT_PROVIDER", "openai")).strip().lower()
        self._client = None

    def _build_client(self):
        if self.provider == "mock":
            return None

        if self.provider == "huggingface":
            from huggingface_hub import InferenceClient

            return InferenceClient(
                model=os.getenv("AGENTSHRINK_GATEWAY_HF_MODEL", os.getenv("TARGET_AGENT_HF_MODEL", "HuggingFaceTB/SmolLM2-1.7B-Instruct")),
                token=os.getenv("HF_TOKEN"),
            )

        from openai import OpenAI

        if self.provider == "nvidia":
            return OpenAI(
                base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                api_key=os.getenv("NVIDIA_API_KEY"),
            )
        if self.provider == "ollama":
            return OpenAI(
                base_url=os.getenv("AGENTSHRINK_GATEWAY_OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://localhost:11434")) + "/v1",
                api_key=os.getenv("AGENTSHRINK_GATEWAY_OLLAMA_API_KEY", "ollama"),
            )
        base_url = os.getenv("OPENAI_BASE_URL", None)
        api_key = os.getenv("OPENAI_API_KEY", None)
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAI(**kwargs)

    @property
    def client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _mock_text(self, payload: dict[str, Any]) -> str:
        messages = payload.get("messages") or []
        user_text = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_text = str(message.get("content", ""))
                break
        return f"[mock:{payload.get('model', 'unknown')}] {user_text[:120] or 'Hello from AgentShrink Gateway'}"

    def _normalize_response(self, response: Any, payload: dict[str, Any]) -> dict[str, Any]:
        if self.provider == "mock":
            content = self._mock_text(payload)
            tokens_in = max(1, len(content) // 6)
            tokens_out = max(1, len(content) // 8)
            return {
                "id": f"chatcmpl-mock-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model", "mock-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": tokens_in,
                    "completion_tokens": tokens_out,
                    "total_tokens": tokens_in + tokens_out,
                },
            }

        if self.provider == "huggingface":
            message = getattr(response, "choices", [None])[0]
            content = ""
            finish_reason = "stop"
            if message is not None:
                hf_message = getattr(message, "message", None)
                content = getattr(hf_message, "content", "") if hf_message is not None else ""
                finish_reason = getattr(message, "finish_reason", "stop") or "stop"
            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or (prompt_tokens + completion_tokens))
            return {
                "id": getattr(response, "id", f"chatcmpl-hf-{int(time.time())}"),
                "object": "chat.completion",
                "created": int(getattr(response, "created", int(time.time())) or int(time.time())),
                "model": payload.get("model", os.getenv("AGENTSHRINK_GATEWAY_HF_MODEL", "huggingface")),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": finish_reason,
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            }

        choices = []
        for choice in getattr(response, "choices", []) or []:
            message = getattr(choice, "message", None)
            choices.append(
                {
                    "index": getattr(choice, "index", 0),
                    "message": {
                        "role": getattr(message, "role", "assistant") if message is not None else "assistant",
                        "content": getattr(message, "content", "") if message is not None else "",
                    },
                    "finish_reason": getattr(choice, "finish_reason", "stop"),
                }
            )
        usage = getattr(response, "usage", None)
        usage_payload = {
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }
        return {
            "id": getattr(response, "id", f"chatcmpl-{int(time.time())}"),
            "object": getattr(response, "object", "chat.completion"),
            "created": int(getattr(response, "created", int(time.time())) or int(time.time())),
            "model": getattr(response, "model", payload.get("model", "unknown")),
            "choices": choices,
            "usage": usage_payload,
        }

    def chat_completions_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.provider == "mock":
            return self._normalize_response(None, payload)

        if self.provider == "huggingface":
            response = self.client.chat_completion(**payload)
            return self._normalize_response(response, payload)

        response = self.client.chat.completions.create(**payload)
        return self._normalize_response(response, payload)

    def iter_chat_completions(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        if self.provider == "mock":
            full = self._mock_text(payload)
            chunk_size = 18
            for i in range(0, len(full), chunk_size):
                text = full[i:i + chunk_size]
                yield {
                    "id": f"chatcmpl-mock-stream-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": payload.get("model", "mock-model"),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": None,
                        }
                    ],
                }
            yield {
                "id": f"chatcmpl-mock-stream-{int(time.time())}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": payload.get("model", "mock-model"),
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": self.chat_completions_create(payload)["usage"],
            }
            return

        if self.provider == "huggingface":
            response = self.chat_completions_create(payload)
            content = ((response.get("choices") or [{}])[0].get("message") or {}).get("content", "")
            chunk_size = 24
            for i in range(0, len(content), chunk_size):
                text = content[i:i + chunk_size]
                yield {
                    "id": response["id"],
                    "object": "chat.completion.chunk",
                    "created": response["created"],
                    "model": response["model"],
                    "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                }
            yield {
                "id": response["id"],
                "object": "chat.completion.chunk",
                "created": response["created"],
                "model": response["model"],
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": response["usage"],
            }
            return

        stream = self.client.chat.completions.create(**payload, stream=True)
        usage_payload = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for chunk in stream:
            chunk_dict = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk.dict()
            usage = chunk_dict.get("usage") or {}
            if usage:
                usage_payload = {
                    "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                }
                chunk_dict["usage"] = usage_payload
            yield chunk_dict
