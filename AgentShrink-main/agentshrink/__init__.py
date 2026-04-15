"""AgentShrink - Automatically convert LLM agents to use cheaper local SLMs.

Based on NVIDIA Research arXiv:2506.02153 (June 2025).
"""

__version__ = "0.6.0"
__all__ = ["AgentShrinkLogger", "ShrinkLLM", "wrap_openai_client"]


def __getattr__(name: str):
    if name == "AgentShrinkLogger":
        from agentshrink.logger import AgentShrinkLogger

        return AgentShrinkLogger
    if name == "ShrinkLLM":
        from agentshrink.shrink_llm import ShrinkLLM

        return ShrinkLLM
    if name == "wrap_openai_client":
        from agentshrink.wrappers.openai import wrap_openai_client

        return wrap_openai_client
    raise AttributeError(f"module 'agentshrink' has no attribute {name!r}")
