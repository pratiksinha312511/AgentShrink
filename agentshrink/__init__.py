"""AgentShrink — Automatically convert LLM agents to use cheaper local SLMs.

Based on NVIDIA Research arXiv:2506.02153 (June 2025).
"""
from agentshrink.logger import AgentShrinkLogger
from agentshrink.shrink_llm import ShrinkLLM

__version__ = "0.1.0"
__all__ = ["AgentShrinkLogger", "ShrinkLLM"]
