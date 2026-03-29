import os


def analysis_provider() -> str:
    return os.getenv("AGENTSHRINK_ANALYSIS_PROVIDER", os.getenv("TARGET_AGENT_PROVIDER", "openai")).strip().lower()


def analysis_model(provider: str | None = None) -> str:
    provider = (provider or analysis_provider()).strip().lower()
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
