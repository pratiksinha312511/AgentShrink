from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


ALLOWED_PROVIDER_ADAPTERS = {
    "mock",
    "openai_compatible",
    "huggingface_chat",
    "gemini_native",
    "anthropic_native",
    "azure_openai",
    "custom_http",
}


PROVIDER_PRESETS = [
    {
        "id": "anthropic",
        "name": "Anthropic",
        "adapter": "anthropic_native",
        "builtin": True,
        "enabled": True,
        "description": "Native Anthropic Messages API.",
        "default_model": "claude-3-5-haiku-latest",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com",
        "base_url_env": "",
        "extra_headers": {"anthropic_version": "2023-06-01"},
    },
    {
        "id": "azure-openai",
        "name": "Azure OpenAI",
        "adapter": "azure_openai",
        "builtin": True,
        "enabled": True,
        "description": "Azure OpenAI deployment endpoint.",
        "default_model": "gpt-4o-mini",
        "api_key_env": "AZURE_OPENAI_API_KEY",
        "base_url": "",
        "base_url_env": "AZURE_OPENAI_ENDPOINT",
        "extra_headers": {"api_version": "2024-10-21"},
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "adapter": "openai_compatible",
        "builtin": True,
        "enabled": True,
        "description": "OpenRouter multi-model OpenAI-compatible gateway.",
        "default_model": "openai/gpt-4o-mini",
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "base_url_env": "",
        "extra_headers": {},
    },
    {
        "id": "groq",
        "name": "Groq",
        "adapter": "openai_compatible",
        "builtin": True,
        "enabled": True,
        "description": "Groq OpenAI-compatible chat endpoint.",
        "default_model": "llama-3.1-8b-instant",
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "base_url_env": "",
        "extra_headers": {},
    },
    {
        "id": "together",
        "name": "Together AI",
        "adapter": "openai_compatible",
        "builtin": True,
        "enabled": True,
        "description": "Together AI OpenAI-compatible endpoint.",
        "default_model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "api_key_env": "TOGETHER_API_KEY",
        "base_url": "https://api.together.xyz/v1",
        "base_url_env": "",
        "extra_headers": {},
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "adapter": "openai_compatible",
        "builtin": True,
        "enabled": True,
        "description": "DeepSeek OpenAI-compatible endpoint.",
        "default_model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "base_url_env": "",
        "extra_headers": {},
    },
]


STATIC_MODEL_SUGGESTIONS = {
    "mock": ["mock-model"],
    "huggingface_chat": [
        "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "Qwen/Qwen2.5-1.5B-Instruct",
    ],
    "gemini_native": [
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ],
    "anthropic_native": [
        "claude-3-5-haiku-latest",
        "claude-3-7-sonnet-latest",
        "claude-3-opus-latest",
    ],
    "azure_openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "o4-mini",
    ],
    "custom_http": [],
}

RESERVED_EXTRA_HEADER_KEYS = {
    "api_version",
    "anthropic_version",
    "auth_header",
    "auth_scheme",
    "request_mode",
    "model_field",
    "messages_field",
    "prompt_field",
    "response_text_path",
}


def _provider_headers(provider: dict[str, Any]) -> dict[str, str]:
    headers = {
        str(key): str(value)
        for key, value in (provider.get("extra_headers") or {}).items()
        if str(key).strip() and str(value).strip()
    }
    return headers


def provider_request_headers(provider: dict[str, Any]) -> dict[str, str]:
    return {
        key: value
        for key, value in _provider_headers(provider).items()
        if key not in RESERVED_EXTRA_HEADER_KEYS
    }


def provider_api_version(provider: dict[str, Any]) -> str:
    headers = _provider_headers(provider)
    return str(headers.get("api_version") or "2024-10-21").strip()


def provider_anthropic_version(provider: dict[str, Any]) -> str:
    headers = _provider_headers(provider)
    return str(headers.get("anthropic_version") or "2023-06-01").strip()


def _models_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/models"


def _build_openai_compatible_headers(provider: dict[str, Any]) -> dict[str, str]:
    from agentshrink.provider_registry import resolve_provider_api_key

    headers = {"Content-Type": "application/json"}
    api_key = resolve_provider_api_key(provider)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    headers.update(_provider_headers(provider))
    return headers


def _http_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, payload: dict | None = None, timeout: float = 8.0) -> dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw or "{}")


def _static_models(provider: dict[str, Any]) -> list[str]:
    adapter = str(provider.get("adapter") or "").strip().lower()
    default_model = str(provider.get("default_model") or "").strip()
    models = list(STATIC_MODEL_SUGGESTIONS.get(adapter, []))
    if default_model and default_model not in models:
        models.insert(0, default_model)
    return models


def custom_http_settings(provider: dict[str, Any]) -> dict[str, str]:
    headers = _provider_headers(provider)
    return {
        "auth_header": str(headers.get("auth_header") or "Authorization").strip(),
        "auth_scheme": str(headers.get("auth_scheme") or "Bearer").strip(),
        "request_mode": str(headers.get("request_mode") or "openai_messages").strip(),
        "model_field": str(headers.get("model_field") or "model").strip(),
        "messages_field": str(headers.get("messages_field") or "messages").strip(),
        "prompt_field": str(headers.get("prompt_field") or "prompt").strip(),
        "response_text_path": str(headers.get("response_text_path") or "").strip(),
    }


def messages_to_prompt(messages: list[dict[str, Any]] | None) -> str:
    return "\n".join(
        f"{message.get('role', 'user')}: {message.get('content', '')}"
        for message in (messages or [])
    ).strip()


def build_custom_http_payload(provider: dict[str, Any], *, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    settings = custom_http_settings(provider)
    payload: dict[str, Any] = {}
    if settings["model_field"]:
        payload[settings["model_field"]] = model
    if settings["request_mode"] == "prompt_only":
        payload[settings["prompt_field"]] = messages_to_prompt(messages)
    else:
        payload[settings["messages_field"]] = messages
    return payload


def build_custom_http_headers(provider: dict[str, Any]) -> dict[str, str]:
    from agentshrink.provider_registry import resolve_provider_api_key

    headers = {"Content-Type": "application/json"}
    headers.update(provider_request_headers(provider))
    api_key = resolve_provider_api_key(provider)
    settings = custom_http_settings(provider)
    if api_key and settings["auth_header"]:
        if settings["auth_scheme"]:
            headers[settings["auth_header"]] = f"{settings['auth_scheme']} {api_key}".strip()
        else:
            headers[settings["auth_header"]] = api_key
    return headers


def _extract_path(data: Any, path: str) -> Any:
    current = data
    for segment in [part for part in path.split(".") if part]:
        if isinstance(current, list):
            current = current[int(segment)]
        elif isinstance(current, dict):
            current = current.get(segment)
        else:
            return None
    return current


def extract_custom_http_text(provider: dict[str, Any], response_data: Any) -> str:
    settings = custom_http_settings(provider)
    if settings["response_text_path"]:
        value = _extract_path(response_data, settings["response_text_path"])
        return "" if value is None else str(value)

    fallback_paths = [
        "choices.0.message.content",
        "output_text",
        "text",
        "response",
        "data.output_text",
        "result.text",
    ]
    for path in fallback_paths:
        value = _extract_path(response_data, path)
        if value not in {None, ""}:
            return str(value)
    return ""


def discover_provider_models(provider_or_id: dict[str, Any] | str, *, timeout: float = 8.0) -> dict[str, Any]:
    from agentshrink.provider_registry import get_provider_config, resolve_provider_api_key, resolve_provider_base_url

    provider = provider_or_id if isinstance(provider_or_id, dict) else get_provider_config(provider_or_id)
    if provider is None:
        raise ValueError("Unknown provider.")

    adapter = str(provider.get("adapter") or "").strip().lower()
    static_models = _static_models(provider)

    if adapter == "mock":
        return {"provider_id": provider.get("id"), "source": "static", "models": static_models}

    if adapter == "openai_compatible":
        base_url = resolve_provider_base_url(provider)
        api_key = resolve_provider_api_key(provider)
        if not base_url or not api_key:
            return {
                "provider_id": provider.get("id"),
                "source": "static",
                "models": static_models,
                "detail": "Saved static suggestions because the provider is missing a base URL or API key.",
            }
        try:
            payload = _http_json(
                _models_url(base_url),
                headers=_build_openai_compatible_headers(provider),
                timeout=timeout,
            )
            model_ids = sorted({
                str(item.get("id") or "").strip()
                for item in (payload.get("data") or [])
                if str(item.get("id") or "").strip()
            })
            return {
                "provider_id": provider.get("id"),
                "source": "live",
                "models": model_ids or static_models,
                "detail": "Discovered models from the provider /models endpoint." if model_ids else "Provider responded but did not return model ids; showing saved defaults.",
            }
        except Exception as exc:
            return {
                "provider_id": provider.get("id"),
                "source": "static",
                "models": static_models,
                "detail": f"Fell back to static model suggestions because live discovery failed: {exc}",
            }

    if adapter == "custom_http":
        base_url = resolve_provider_base_url(provider)
        if not base_url:
            return {
                "provider_id": provider.get("id"),
                "source": "static",
                "models": static_models,
                "detail": "Custom HTTP providers do not have a standard model list endpoint; showing saved defaults only.",
            }
        return {
            "provider_id": provider.get("id"),
            "source": "static",
            "models": static_models,
            "detail": "Custom HTTP providers use the saved default model list; add exact model ids manually when needed.",
        }

    return {
        "provider_id": provider.get("id"),
        "source": "static",
        "models": static_models,
        "detail": "This adapter currently uses curated model suggestions instead of a live discovery endpoint.",
    }


def test_provider_connection(provider_or_id: dict[str, Any] | str, *, timeout: float = 8.0) -> dict[str, Any]:
    from agentshrink.provider_registry import get_provider_config, resolve_provider_api_key, resolve_provider_base_url

    provider = provider_or_id if isinstance(provider_or_id, dict) else get_provider_config(provider_or_id)
    if provider is None:
        raise ValueError("Unknown provider.")

    provider_id = provider.get("id")
    adapter = str(provider.get("adapter") or "").strip().lower()

    if adapter == "mock":
        return {
            "provider_id": provider_id,
            "ok": True,
            "message": "Mock provider is always reachable for local testing.",
            "checked_via": "local-mock",
        }

    if adapter == "openai_compatible":
        base_url = resolve_provider_base_url(provider)
        api_key = resolve_provider_api_key(provider)
        if not base_url or not api_key:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": "Missing base URL or API key for this OpenAI-compatible provider.",
                "checked_via": "config-validation",
            }
        try:
            payload = _http_json(
                _models_url(base_url),
                headers=_build_openai_compatible_headers(provider),
                timeout=timeout,
            )
            model_count = len(payload.get("data") or [])
            return {
                "provider_id": provider_id,
                "ok": True,
                "message": f"Provider responded successfully to /models with {model_count} model entries.",
                "checked_via": "models-endpoint",
            }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": f"Provider returned HTTP {exc.code}: {detail}",
                "checked_via": "models-endpoint",
            }
        except Exception as exc:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": f"Provider connection failed: {exc}",
                "checked_via": "models-endpoint",
            }

    if adapter == "custom_http":
        base_url = resolve_provider_base_url(provider)
        if not base_url:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": "Missing endpoint URL for this custom HTTP provider.",
                "checked_via": "config-validation",
            }
        try:
            payload = build_custom_http_payload(
                provider,
                model=str(provider.get("default_model") or "default-model"),
                messages=[{"role": "user", "content": "Reply with OK."}],
            )
            response_data = _http_json(
                base_url,
                method="POST",
                headers=build_custom_http_headers(provider),
                payload=payload,
                timeout=timeout,
            )
            text = extract_custom_http_text(provider, response_data)
            return {
                "provider_id": provider_id,
                "ok": bool(text),
                "message": f"Custom HTTP provider responded with: {(text or '[no response text extracted]')[:120]}",
                "checked_via": "custom-http",
            }
        except Exception as exc:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": f"Custom HTTP connection failed: {exc}",
                "checked_via": "custom-http",
            }

    if adapter == "gemini_native":
        api_key = resolve_provider_api_key(provider)
        if not api_key:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": "Missing GOOGLE_API_KEY for Gemini.",
                "checked_via": "config-validation",
            }
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(provider.get("default_model") or "gemini-2.0-flash-lite")
            response = model.generate_content("Reply with OK.")
            return {
                "provider_id": provider_id,
                "ok": True,
                "message": f"Gemini responded successfully: {(getattr(response, 'text', '') or '').strip()[:80]}",
                "checked_via": "generate-content",
            }
        except Exception as exc:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": f"Gemini connection failed: {exc}",
                "checked_via": "generate-content",
            }

    if adapter == "anthropic_native":
        api_key = resolve_provider_api_key(provider)
        if not api_key:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": "Missing ANTHROPIC_API_KEY for Anthropic.",
                "checked_via": "config-validation",
            }
        try:
            payload = {
                "model": provider.get("default_model") or "claude-3-5-haiku-latest",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "Reply with OK."}],
            }
            _http_json(
                f"{resolve_provider_base_url(provider).rstrip('/')}/v1/messages",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": provider_anthropic_version(provider),
                },
                payload=payload,
                timeout=timeout,
            )
            return {
                "provider_id": provider_id,
                "ok": True,
                "message": "Anthropic responded successfully to a minimal Messages API test.",
                "checked_via": "messages-api",
            }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": f"Anthropic returned HTTP {exc.code}: {detail}",
                "checked_via": "messages-api",
            }
        except Exception as exc:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": f"Anthropic connection failed: {exc}",
                "checked_via": "messages-api",
            }

    if adapter == "azure_openai":
        api_key = resolve_provider_api_key(provider)
        endpoint = resolve_provider_base_url(provider)
        if not api_key or not endpoint:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": "Missing Azure endpoint or API key.",
                "checked_via": "config-validation",
            }
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                api_key=api_key,
                api_version=provider_api_version(provider),
                azure_endpoint=endpoint,
            )
            client.chat.completions.create(
                model=provider.get("default_model") or "gpt-4o-mini",
                messages=[{"role": "user", "content": "Reply with OK."}],
                max_tokens=8,
            )
            return {
                "provider_id": provider_id,
                "ok": True,
                "message": "Azure OpenAI responded successfully to a minimal chat completion test.",
                "checked_via": "chat-completions",
            }
        except Exception as exc:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": f"Azure OpenAI connection failed: {exc}",
                "checked_via": "chat-completions",
            }

    if adapter == "huggingface_chat":
        api_key = resolve_provider_api_key(provider)
        if not api_key:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": "Missing HF token for Hugging Face.",
                "checked_via": "config-validation",
            }
        try:
            from huggingface_hub import InferenceClient

            client = InferenceClient(model=provider.get("default_model"), token=api_key)
            client.chat_completion(
                model=provider.get("default_model"),
                messages=[{"role": "user", "content": "Reply with OK."}],
                max_tokens=8,
            )
            return {
                "provider_id": provider_id,
                "ok": True,
                "message": "Hugging Face responded successfully to a minimal chat completion test.",
                "checked_via": "chat-completion",
            }
        except Exception as exc:
            return {
                "provider_id": provider_id,
                "ok": False,
                "message": f"Hugging Face connection failed: {exc}",
                "checked_via": "chat-completion",
            }

    return {
        "provider_id": provider_id,
        "ok": False,
        "message": f"Unsupported adapter '{adapter}' for connection testing.",
        "checked_via": "not-implemented",
    }
