"""Upstream provider abstraction for the AgentShrink gateway."""

from __future__ import annotations

import os
import time
import json
import urllib.request
from typing import Any, Iterator

from agentshrink.provider_registry import (
    get_provider_config,
    resolve_provider_api_key,
    resolve_provider_base_url,
)
from agentshrink.provider_runtime import provider_anthropic_version, provider_api_version
from agentshrink.provider_runtime import (
    build_custom_http_headers,
    build_custom_http_payload,
    extract_custom_http_text,
)


class OpenAICompatibleUpstream:
    """Minimal upstream interface using the OpenAI SDK for compatible providers."""

    def __init__(self, provider: str | None = None):
        self.provider = (provider or os.getenv("AGENTSHRINK_GATEWAY_UPSTREAM_PROVIDER") or os.getenv("TARGET_AGENT_PROVIDER", "openai")).strip().lower()
        self.provider_config = get_provider_config(self.provider)
        if self.provider_config is None:
            raise ValueError(f"Unknown AgentShrink upstream provider '{self.provider}'. Add it in Settings -> provider registry first.")
        self.adapter = str(self.provider_config.get("adapter") or "openai_compatible").strip().lower()
        self._client = None

    def _build_client(self):
        if self.adapter == "mock":
            return None

        if self.adapter == "gemini_native":
            import google.generativeai as genai

            api_key = resolve_provider_api_key(self.provider_config)
            if api_key:
                genai.configure(api_key=api_key)
            return genai.GenerativeModel(
                self.provider_config.get("default_model")
                or os.getenv("AGENTSHRINK_GATEWAY_GEMINI_MODEL", os.getenv("TARGET_AGENT_GEMINI_MODEL", "gemini-2.0-flash-lite"))
            )

        if self.adapter == "huggingface_chat":
            from huggingface_hub import InferenceClient

            return InferenceClient(
                model=self.provider_config.get("default_model") or os.getenv("AGENTSHRINK_GATEWAY_HF_MODEL", os.getenv("TARGET_AGENT_HF_MODEL", "HuggingFaceTB/SmolLM2-1.7B-Instruct")),
                token=resolve_provider_api_key(self.provider_config),
            )

        if self.adapter == "azure_openai":
            from openai import AzureOpenAI

            return AzureOpenAI(
                api_key=resolve_provider_api_key(self.provider_config),
                api_version=provider_api_version(self.provider_config),
                azure_endpoint=resolve_provider_base_url(self.provider_config),
            )

        if self.adapter == "custom_http":
            return None

        from openai import OpenAI

        base_url = resolve_provider_base_url(self.provider_config)
        api_key = resolve_provider_api_key(self.provider_config)
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        extra_headers = self.provider_config.get("extra_headers") or {}
        if extra_headers:
            kwargs["default_headers"] = extra_headers
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
        if self.adapter == "mock":
            content = self._mock_text(payload)
            tokens_in = max(1, len(content) // 6)
            tokens_out = max(1, len(content) // 8)
            return {
                "id": f"chatcmpl-mock-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model", self.provider_config.get("default_model", "mock-model")),
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

        if self.adapter == "gemini_native":
            content = getattr(response, "text", "") or ""
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
            completion_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
            total_tokens = int(getattr(usage, "total_token_count", prompt_tokens + completion_tokens) or (prompt_tokens + completion_tokens))
            return {
                "id": f"chatcmpl-gemini-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model", self.provider_config.get("default_model") or "gemini"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            }

        if self.adapter == "huggingface_chat":
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
                "model": payload.get("model", self.provider_config.get("default_model") or os.getenv("AGENTSHRINK_GATEWAY_HF_MODEL", "huggingface")),
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

        if self.adapter == "anthropic_native":
            parts = response.get("content") or []
            content = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
            usage = response.get("usage") or {}
            prompt_tokens = int(usage.get("input_tokens", 0) or 0)
            completion_tokens = int(usage.get("output_tokens", 0) or 0)
            return {
                "id": response.get("id", f"chatcmpl-anthropic-{int(time.time())}"),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model", self.provider_config.get("default_model") or "anthropic"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": response.get("stop_reason") or "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }

        if self.adapter == "custom_http":
            content = extract_custom_http_text(self.provider_config, response)
            usage = response.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
            completion_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
            return {
                "id": response.get("id", f"chatcmpl-custom-{int(time.time())}"),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": payload.get("model", self.provider_config.get("default_model") or "custom-http"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": response.get("finish_reason") or "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": int(usage.get("total_tokens", prompt_tokens + completion_tokens) or (prompt_tokens + completion_tokens)),
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
        if self.adapter == "mock":
            return self._normalize_response(None, payload)

        if self.adapter == "gemini_native":
            messages = payload.get("messages") or []
            prompt = "\n".join(
                f"{message.get('role', 'user')}: {message.get('content', '')}"
                for message in messages
            )
            response = self.client.generate_content(prompt)
            return self._normalize_response(response, payload)

        if self.adapter == "huggingface_chat":
            response = self.client.chat_completion(**payload)
            return self._normalize_response(response, payload)

        if self.adapter == "custom_http":
            request_payload = build_custom_http_payload(
                self.provider_config,
                model=payload.get("model", self.provider_config.get("default_model") or "custom-http"),
                messages=payload.get("messages") or [],
            )
            request = urllib.request.Request(
                resolve_provider_base_url(self.provider_config),
                data=json.dumps(request_payload).encode("utf-8"),
                headers=build_custom_http_headers(self.provider_config),
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
            return self._normalize_response(body, payload)

        if self.adapter == "anthropic_native":
            messages = payload.get("messages") or []
            system_messages = [str(message.get("content", "")) for message in messages if message.get("role") == "system"]
            anthropic_messages = [
                {
                    "role": "assistant" if message.get("role") == "assistant" else "user",
                    "content": str(message.get("content", "")),
                }
                for message in messages
                if message.get("role") != "system"
            ]
            request_payload = {
                "model": payload.get("model", self.provider_config.get("default_model")),
                "max_tokens": int(payload.get("max_tokens") or 1024),
                "messages": anthropic_messages or [{"role": "user", "content": ""}],
            }
            if system_messages:
                request_payload["system"] = "\n\n".join(system_messages)
            request = urllib.request.Request(
                f"{(resolve_provider_base_url(self.provider_config) or 'https://api.anthropic.com').rstrip('/')}/v1/messages",
                data=json.dumps(request_payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": resolve_provider_api_key(self.provider_config),
                    "anthropic-version": provider_anthropic_version(self.provider_config),
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
            return self._normalize_response(body, payload)

        response = self.client.chat.completions.create(**payload)
        return self._normalize_response(response, payload)

    def iter_chat_completions(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        if self.adapter == "mock":
            full = self._mock_text(payload)
            chunk_size = 18
            for i in range(0, len(full), chunk_size):
                text = full[i:i + chunk_size]
                yield {
                    "id": f"chatcmpl-mock-stream-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": payload.get("model", self.provider_config.get("default_model", "mock-model")),
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
                "model": payload.get("model", self.provider_config.get("default_model", "mock-model")),
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": self.chat_completions_create(payload)["usage"],
            }
            return

        if self.adapter in {"gemini_native", "huggingface_chat", "anthropic_native", "custom_http"}:
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
