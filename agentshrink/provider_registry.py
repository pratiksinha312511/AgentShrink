from __future__ import annotations

import json
import os
import pathlib
from typing import Any

from agentshrink.provider_runtime import PROVIDER_PRESETS


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / ".agentshrink"
PROVIDER_REGISTRY_PATH = STATE_DIR / "providers.json"


DEFAULT_PROVIDER_REGISTRY = {
    "providers": [
        {
            "id": "mock",
            "name": "Mock",
            "adapter": "mock",
            "builtin": True,
            "enabled": True,
            "description": "Free local testing with mock gateway responses.",
            "default_model": "mock-model",
            "base_url": "",
            "api_key": "",
            "api_key_env": "",
            "base_url_env": "",
            "extra_headers": {},
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "adapter": "openai_compatible",
            "builtin": True,
            "enabled": True,
            "description": "Standard OpenAI-compatible provider using OPENAI_API_KEY.",
            "default_model": "gpt-4o-mini",
            "base_url": "",
            "api_key": "",
            "api_key_env": "OPENAI_API_KEY",
            "base_url_env": "OPENAI_BASE_URL",
            "extra_headers": {},
        },
        {
            "id": "nvidia",
            "name": "NVIDIA",
            "adapter": "openai_compatible",
            "builtin": True,
            "enabled": True,
            "description": "OpenAI-compatible NVIDIA inference endpoint.",
            "default_model": "meta/llama-3.1-8b-instruct",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key": "",
            "api_key_env": "NVIDIA_API_KEY",
            "base_url_env": "NVIDIA_BASE_URL",
            "extra_headers": {},
        },
        {
            "id": "ollama",
            "name": "Ollama",
            "adapter": "openai_compatible",
            "builtin": True,
            "enabled": True,
            "description": "Local Ollama server through its OpenAI-compatible /v1 endpoint.",
            "default_model": "llama3.2:3b",
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
            "api_key_env": "AGENTSHRINK_GATEWAY_OLLAMA_API_KEY",
            "base_url_env": "AGENTSHRINK_GATEWAY_OLLAMA_BASE_URL",
            "extra_headers": {},
        },
        {
            "id": "huggingface",
            "name": "Hugging Face",
            "adapter": "huggingface_chat",
            "builtin": True,
            "enabled": True,
            "description": "Hugging Face InferenceClient chat completion adapter.",
            "default_model": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
            "base_url": "",
            "api_key": "",
            "api_key_env": "HF_TOKEN",
            "base_url_env": "",
            "extra_headers": {},
        },
        {
            "id": "gemini",
            "name": "Gemini",
            "adapter": "gemini_native",
            "builtin": True,
            "enabled": True,
            "description": "Google Gemini chat via the native Google Generative AI adapter.",
            "default_model": "gemini-2.0-flash-lite",
            "base_url": "",
            "api_key": "",
            "api_key_env": "GOOGLE_API_KEY",
            "base_url_env": "",
            "extra_headers": {},
        },
        *PROVIDER_PRESETS,
    ]
}


def _ensure_state_dir() -> pathlib.Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


def _normalize_provider(provider: dict[str, Any]) -> dict[str, Any]:
    raw_api_key = str(provider.get("api_key") or "").strip()
    raw_api_key_env = str(provider.get("api_key_env") or "").strip()
    raw_base_url = str(provider.get("base_url") or "").strip()
    raw_base_url_env = str(provider.get("base_url_env") or "").strip()

    # Rescue common UI mistakes where users paste a real secret or URL into the env-var field.
    if not raw_api_key and raw_api_key_env and (raw_api_key_env.startswith("sk_") or " " in raw_api_key_env):
        raw_api_key = raw_api_key_env
        raw_api_key_env = ""
    if not raw_base_url and raw_base_url_env and raw_base_url_env.startswith(("http://", "https://")):
        raw_base_url = raw_base_url_env
        raw_base_url_env = ""

    normalized = {
        "id": str(provider.get("id") or "").strip().lower(),
        "name": str(provider.get("name") or "").strip(),
        "adapter": str(provider.get("adapter") or "openai_compatible").strip().lower(),
        "builtin": bool(provider.get("builtin", False)),
        "enabled": bool(provider.get("enabled", True)),
        "description": str(provider.get("description") or "").strip(),
        "default_model": str(provider.get("default_model") or "").strip(),
        "base_url": raw_base_url,
        "api_key": raw_api_key,
        "api_key_env": raw_api_key_env,
        "base_url_env": raw_base_url_env,
        "extra_headers": provider.get("extra_headers") or {},
    }
    if not normalized["name"]:
        normalized["name"] = normalized["id"].replace("-", " ").title()
    return normalized


def load_provider_registry() -> dict[str, Any]:
    _ensure_state_dir()
    if PROVIDER_REGISTRY_PATH.exists():
        with open(PROVIDER_REGISTRY_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = {}

    merged = _deep_copy(DEFAULT_PROVIDER_REGISTRY)
    merged_by_id = {
        provider["id"]: _normalize_provider(provider)
        for provider in merged.get("providers", [])
    }

    for provider in raw.get("providers", []) if isinstance(raw, dict) else []:
        normalized = _normalize_provider(provider)
        provider_id = normalized["id"]
        if not provider_id:
            continue
        if provider_id in merged_by_id:
            _deep_update(merged_by_id[provider_id], normalized)
        else:
            merged_by_id[provider_id] = normalized

    default_order = [provider["id"] for provider in DEFAULT_PROVIDER_REGISTRY["providers"]]
    custom_ids = sorted(
        [provider_id for provider_id in merged_by_id.keys() if provider_id not in default_order],
        key=lambda provider_id: merged_by_id[provider_id]["name"].lower(),
    )
    ordered_ids = default_order + custom_ids
    return {"providers": [merged_by_id[provider_id] for provider_id in ordered_ids if provider_id in merged_by_id]}


def save_provider_registry(registry: dict[str, Any]) -> dict[str, Any]:
    _ensure_state_dir()
    normalized = {"providers": [_normalize_provider(provider) for provider in registry.get("providers", [])]}
    with open(PROVIDER_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2)
    return load_provider_registry()


def list_provider_configs(*, include_disabled: bool = True) -> list[dict[str, Any]]:
    providers = load_provider_registry().get("providers", [])
    if include_disabled:
        return providers
    return [provider for provider in providers if provider.get("enabled", True)]


def get_provider_config(provider_id: str | None) -> dict[str, Any] | None:
    normalized_id = str(provider_id or "").strip().lower()
    if not normalized_id:
        return None
    for provider in list_provider_configs():
        if provider.get("id") == normalized_id:
            return provider
    return None


def upsert_provider_config(provider: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_provider(provider)
    if not normalized["id"]:
        raise ValueError("Provider id is required.")
    registry = load_provider_registry()
    providers = registry.get("providers", [])
    replaced = False
    for index, existing in enumerate(providers):
        if existing.get("id") == normalized["id"]:
            next_provider = _deep_copy(existing)
            _deep_update(next_provider, normalized)
            providers[index] = _normalize_provider(next_provider)
            replaced = True
            break
    if not replaced:
        providers.append(normalized)
    saved = save_provider_registry({"providers": providers})
    result = get_provider_config(normalized["id"])
    if result is None:
        raise ValueError(f"Provider '{normalized['id']}' could not be saved.")
    return result


def delete_provider_config(provider_id: str) -> dict[str, Any]:
    normalized_id = str(provider_id or "").strip().lower()
    if not normalized_id:
        raise ValueError("Provider id is required.")
    provider = get_provider_config(normalized_id)
    if provider and provider.get("builtin"):
        raise ValueError("Built-in providers cannot be deleted.")
    registry = load_provider_registry()
    saved = save_provider_registry({
        "providers": [provider for provider in registry.get("providers", []) if provider.get("id") != normalized_id]
    })
    return saved


def resolve_provider_api_key(provider: dict[str, Any]) -> str:
    env_name = str(provider.get("api_key_env") or "").strip()
    if env_name and os.getenv(env_name):
        return str(os.getenv(env_name) or "").strip()
    return str(provider.get("api_key") or "").strip()


def resolve_provider_base_url(provider: dict[str, Any]) -> str:
    env_name = str(provider.get("base_url_env") or "").strip()
    if env_name and os.getenv(env_name):
        return str(os.getenv(env_name) or "").strip()
    return str(provider.get("base_url") or "").strip()


def provider_exists(provider_id: str | None) -> bool:
    return get_provider_config(provider_id) is not None
