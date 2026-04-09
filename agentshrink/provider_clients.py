import os
import json
import urllib.request
from types import SimpleNamespace

from agentshrink.app_setup import load_product_config
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


class _HuggingFaceChatAdapter:
    def __init__(self, *, model: str, token: str | None, temperature: float = 0):
        from huggingface_hub import InferenceClient

        self.model = model
        self.temperature = temperature
        self.client = InferenceClient(model=model, token=token)

    def invoke(self, prompt_or_messages):
        messages = prompt_or_messages
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        response = self.client.chat_completion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        choice = (getattr(response, "choices", None) or [None])[0]
        message = getattr(choice, "message", None) if choice is not None else None
        content = getattr(message, "content", "") if message is not None else ""
        return SimpleNamespace(content=(content or "").strip())


class _MockChatAdapter:
    def __init__(self, *, model: str):
        self.model = model

    def invoke(self, prompt_or_messages):
        if isinstance(prompt_or_messages, str):
            text = prompt_or_messages
        else:
            text = ""
            for message in reversed(prompt_or_messages or []):
                content = getattr(message, "content", None)
                if content:
                    text = str(content)
                    break
                if isinstance(message, dict) and message.get("content"):
                    text = str(message["content"])
                    break
        return SimpleNamespace(content=f"[mock:{self.model}] {text[:200]}".strip())


class _GeminiNativeChatAdapter:
    def __init__(self, *, model: str, api_key: str | None, temperature: float = 0):
        from langchain_google_genai import ChatGoogleGenerativeAI

        self.client = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=api_key,
        )

    def invoke(self, prompt_or_messages):
        return self.client.invoke(prompt_or_messages)


class _AnthropicNativeChatAdapter:
    def __init__(self, *, model: str, api_key: str | None, base_url: str, version: str):
        self.model = model
        self.api_key = api_key or ""
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.version = version

    def invoke(self, prompt_or_messages):
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = []
            for message in prompt_or_messages or []:
                if isinstance(message, dict):
                    messages.append({
                        "role": message.get("role", "user"),
                        "content": str(message.get("content", "")),
                    })
                else:
                    role = getattr(message, "role", "user")
                    content = getattr(message, "content", "")
                    messages.append({"role": role, "content": str(content)})

        system_messages = [msg["content"] for msg in messages if msg.get("role") == "system"]
        anthropic_messages = [
            {"role": "assistant" if msg.get("role") == "assistant" else "user", "content": msg.get("content", "")}
            for msg in messages if msg.get("role") != "system"
        ]
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": anthropic_messages or [{"role": "user", "content": ""}],
        }
        if system_messages:
            payload["system"] = "\n\n".join(system_messages)

        request = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.version,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
        parts = body.get("content") or []
        text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
        return SimpleNamespace(content=text.strip())


class _AzureOpenAIChatAdapter:
    def __init__(self, *, model: str, api_key: str | None, endpoint: str, api_version: str):
        from openai import AzureOpenAI

        self.model = model
        self.client = AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint,
        )

    def invoke(self, prompt_or_messages):
        messages = prompt_or_messages
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1024,
        )
        choice = (getattr(response, "choices", None) or [None])[0]
        message = getattr(choice, "message", None) if choice is not None else None
        content = getattr(message, "content", "") if message is not None else ""
        return SimpleNamespace(content=(content or "").strip())


class _CustomHTTPChatAdapter:
    def __init__(self, *, provider_config: dict, model: str):
        self.provider_config = provider_config
        self.model = model

    def invoke(self, prompt_or_messages):
        if isinstance(prompt_or_messages, str):
            messages = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = []
            for message in prompt_or_messages or []:
                if isinstance(message, dict):
                    messages.append({
                        "role": message.get("role", "user"),
                        "content": str(message.get("content", "")),
                    })
                else:
                    messages.append({
                        "role": getattr(message, "role", "user"),
                        "content": str(getattr(message, "content", "")),
                    })
        payload = build_custom_http_payload(self.provider_config, model=self.model, messages=messages)
        request = urllib.request.Request(
            resolve_provider_base_url(self.provider_config),
            data=json.dumps(payload).encode("utf-8"),
            headers=build_custom_http_headers(self.provider_config),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
        return SimpleNamespace(content=extract_custom_http_text(self.provider_config, body).strip())


def analysis_provider() -> str:
    provider = os.getenv("AGENTSHRINK_ANALYSIS_PROVIDER", os.getenv("TARGET_AGENT_PROVIDER", "")).strip().lower()
    if provider:
        return provider
    product_provider = str(((load_product_config().get("gateway") or {}).get("upstream_provider")) or "").strip().lower()
    return product_provider or "openai"


def analysis_model(provider: str | None = None) -> str:
    provider = (provider or analysis_provider()).strip().lower()
    provider_config = get_provider_config(provider)
    if provider_config:
        configured_default = str(provider_config.get("default_model") or "").strip()
        if configured_default:
            return os.getenv("AGENTSHRINK_ANALYSIS_MODEL", configured_default)
    if provider == "nvidia":
        return os.getenv("AGENTSHRINK_ANALYSIS_MODEL", os.getenv("TARGET_AGENT_NVIDIA_MODEL", "moonshotai/kimi-k2-instruct"))
    if provider == "gemini":
        return os.getenv("AGENTSHRINK_ANALYSIS_MODEL", os.getenv("TARGET_AGENT_GEMINI_MODEL", "gemini-2.0-flash-lite"))
    if provider == "ollama":
        return os.getenv("AGENTSHRINK_ANALYSIS_MODEL", os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b"))
    return os.getenv("AGENTSHRINK_ANALYSIS_MODEL", os.getenv("TARGET_AGENT_OPENAI_MODEL", "gpt-4o-mini"))


def infer_provider_from_model_name(model_name: str | None) -> str:
    """Best-effort provider inference for historical logs that only stored model_name."""
    model_name = (model_name or "").strip()
    if not model_name:
        return "unknown"

    catalog_matches = [
        ("TARGET_AGENT_NVIDIA_MODEL", "nvidia"),
        ("TARGET_AGENT_OLLAMA_MODEL", "ollama"),
        ("TARGET_AGENT_OPENAI_MODEL", "openai"),
        ("TARGET_AGENT_GEMINI_MODEL", "gemini"),
    ]
    for env_var, provider in catalog_matches:
        if model_name == os.getenv(env_var, "").strip():
            return provider

    lowered = model_name.lower()
    if any(token in lowered for token in ["gpt-", "o1", "o3", "openai"]):
        return "openai"
    if any(token in lowered for token in ["claude", "anthropic"]):
        return "anthropic"
    if any(token in lowered for token in ["gemini"]):
        return "gemini"
    if any(token in lowered for token in ["kimi", "moonshot"]):
        return "nvidia"
    if ":" in model_name or any(token in lowered for token in ["llama", "gemma", "phi", "mistral", "qwen"]):
        return "ollama"
    return "unknown"


def get_chat_model(provider: str | None = None, model: str | None = None, temperature: float = 0, callbacks=None):
    provider = (provider or analysis_provider()).strip().lower()
    model = model or analysis_model(provider)
    callbacks = callbacks or []

    provider_config = get_provider_config(provider)
    if provider_config:
        adapter = str(provider_config.get("adapter") or "openai_compatible").strip().lower()
        if adapter == "mock":
            return _MockChatAdapter(model=model)

        if adapter == "huggingface_chat":
            return _HuggingFaceChatAdapter(
                model=model,
                token=resolve_provider_api_key(provider_config) or None,
                temperature=temperature,
            )

        if adapter == "gemini_native":
            return _GeminiNativeChatAdapter(
                model=model,
                api_key=resolve_provider_api_key(provider_config) or None,
                temperature=temperature,
            )

        if adapter == "anthropic_native":
            return _AnthropicNativeChatAdapter(
                model=model,
                api_key=resolve_provider_api_key(provider_config) or None,
                base_url=resolve_provider_base_url(provider_config) or "https://api.anthropic.com",
                version=provider_anthropic_version(provider_config),
            )

        if adapter == "azure_openai":
            return _AzureOpenAIChatAdapter(
                model=model,
                api_key=resolve_provider_api_key(provider_config) or None,
                endpoint=resolve_provider_base_url(provider_config),
                api_version=provider_api_version(provider_config),
            )

        if adapter == "custom_http":
            return _CustomHTTPChatAdapter(
                provider_config=provider_config,
                model=model,
            )

        if adapter == "openai_compatible":
            from langchain_openai import ChatOpenAI

            kwargs = {}
            base_url = resolve_provider_base_url(provider_config)
            api_key = resolve_provider_api_key(provider_config)
            extra_headers = provider_config.get("extra_headers") or {}
            if base_url:
                kwargs["base_url"] = base_url
            if api_key:
                kwargs["api_key"] = api_key
            if extra_headers:
                kwargs["default_headers"] = extra_headers
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                callbacks=callbacks,
                **kwargs,
            )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            temperature=temperature,
            callbacks=callbacks,
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )

    if provider == "nvidia":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            callbacks=callbacks,
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            api_key=os.getenv("NVIDIA_API_KEY"),
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            callbacks=callbacks,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    from langchain_openai import ChatOpenAI

    kwargs = {}
    base_url = os.getenv("OPENAI_BASE_URL", None)
    api_key = os.getenv("OPENAI_API_KEY", None)
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        callbacks=callbacks,
        **kwargs,
    )
