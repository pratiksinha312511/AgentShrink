"""AgentShrink - Automatically convert LLM agents to use cheaper local SLMs.

Based on NVIDIA Research arXiv:2506.02153 (June 2025).
"""

__version__ = "0.1.0"
__all__ = ["AgentShrinkLogger", "ShrinkLLM"]


def __getattr__(name: str):
    if name == "AgentShrinkLogger":
        from agentshrink.logger import AgentShrinkLogger

        return AgentShrinkLogger
    if name == "ShrinkLLM":
        from agentshrink.shrink_llm import ShrinkLLM

        return ShrinkLLM
    raise AttributeError(f"module 'agentshrink' has no attribute {name!r}")
