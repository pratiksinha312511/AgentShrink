"""Local model execution helpers for the AgentShrink gateway."""

from __future__ import annotations

import time
from typing import Any, Iterator


class LocalOllamaExecutor:
    provider = "ollama"

    def chat_completions_create(self, payload: dict[str, Any], model_name: str) -> dict[str, Any]:
        import ollama

        messages = payload.get("messages") or []
        response = ollama.chat(
            model=model_name,
            messages=messages,
            options={
                "temperature": payload.get("temperature", 0) or 0,
                "num_predict": payload.get("max_tokens", 512) or 512,
            },
        )

        if isinstance(response, dict):
            content = (response.get("message") or {}).get("content", "") or ""
        else:
            content = response.message.content or ""

        return {
            "id": f"chatcmpl-local-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    def iter_chat_completions(self, payload: dict[str, Any], model_name: str) -> Iterator[dict[str, Any]]:
        import ollama

        messages = payload.get("messages") or []
        stream = ollama.chat(
            model=model_name,
            messages=messages,
            stream=True,
            options={
                "temperature": payload.get("temperature", 0) or 0,
                "num_predict": payload.get("max_tokens", 512) or 512,
            },
        )

        aggregated = []
        for chunk in stream:
            if isinstance(chunk, dict):
                content = (chunk.get("message") or {}).get("content", "") or ""
            else:
                content = getattr(getattr(chunk, "message", None), "content", "") or ""
            if content:
                aggregated.append(content)
                yield {
                    "id": f"chatcmpl-local-stream-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                }

        yield {
            "id": f"chatcmpl-local-stream-{int(time.time())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model_name,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }
