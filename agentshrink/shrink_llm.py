"""
agentshrink/shrink_llm.py
==========================
PHASE 4 — ShrinkLLM

THE MOST IMPORTANT FILE IN THE PROJECT.

This is the component the developer actually uses in their agent.
It replaces ChatOpenAI with a one-word change:

    BEFORE:  llm = ChatOpenAI(model="gpt-4o-mini", ...)
    AFTER:   llm = ShrinkLLM(model="gpt-4o-mini", ...)

That's the only change to the developer's code.
Everything else — LangGraph nodes, tools, memory, callbacks —
works exactly the same.

HOW IT WORKS AT RUNTIME:
  1. Developer's agent calls llm.invoke(messages) as usual
  2. ShrinkLLM extracts the prompt text from the messages
  3. CentroidIndex finds the nearest cluster centroid (~10ms)
  4. If confidence >= threshold AND cluster has a local model:
     → Call Ollama locally (free, fast, private)
  5. If confidence < threshold OR no local model assigned:
     → Fall through to the real ChatOpenAI (paid, always works)
  6. Log the routing decision (for trace mode + monitoring)

WHY IT EXTENDS BaseChatModel:
  BaseChatModel is the base class for all LangChain chat models.
  By extending it properly, ShrinkLLM inherits:
  - Compatibility with all LangChain tools and agents
  - LangGraph node integration
  - Callback system (AgentShrinkLogger still works!)
  - Streaming support
  - Retry logic

THE FALLBACK GUARANTEE:
  If ANYTHING goes wrong (Ollama down, model not loaded,
  timeout, network issue), ShrinkLLM automatically falls
  back to the original LLM. The developer's agent never
  sees an error caused by AgentShrink. This is the safety
  guarantee that makes it production-safe.
"""

import time
import json
import logging
import pathlib
import os
from typing import Any, Iterator, List, Optional, Mapping
from dotenv import load_dotenv

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage, AIMessage, HumanMessage, SystemMessage
)
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks import CallbackManagerForLLMRun

load_dotenv()
logger = logging.getLogger(__name__)


def _messages_to_prompt(messages: List[BaseMessage]) -> str:
    """
    Convert a list of LangChain messages to a single prompt string.
    Used for centroid similarity lookup — we need plain text.

    We concatenate all message content with role labels.
    The system prompt is most distinctive for clustering,
    so we weight it by putting it first.
    """
    parts = []
    for msg in messages:
        if isinstance(msg.content, str):
            role = getattr(msg, "type", "user")
            parts.append(f"[{role}]: {msg.content}")
        elif isinstance(msg.content, list):
            # Multi-modal content — extract text chunks only
            for chunk in msg.content:
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    parts.append(chunk["text"])

    return "\n".join(parts)


def _messages_to_ollama_format(messages: List[BaseMessage]) -> List[dict]:
    """
    Convert LangChain messages to Ollama's expected format.
    Ollama uses {"role": "...", "content": "..."} dicts.
    """
    role_map = {
        "human":    "user",
        "ai":       "assistant",
        "system":   "system",
        "function": "user",
        "tool":     "user",
    }

    ollama_messages = []
    for msg in messages:
        role    = role_map.get(getattr(msg, "type", "human"), "user")
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        ollama_messages.append({"role": role, "content": content})

    return ollama_messages


class ShrinkLLM(BaseChatModel):
    """
    Drop-in replacement for ChatOpenAI that routes calls to local SLMs
    when the prompt matches a known cluster, falling back to the original
    LLM otherwise.

    ONE-WORD CHANGE to any LangChain/LangGraph agent:
        llm = ShrinkLLM(output_dir=".agentshrink_output")

    All your agent code stays exactly the same.

    Args:
        output_dir:           Path to agentshrink analyse output directory
        fallback_model:       OpenAI model for fallback (default: gpt-4o-mini)
        confidence_threshold: Minimum cosine similarity to route to SLM (default: 0.75)
        trace_mode:           Print routing decisions to console (default: False)
        ollama_timeout:       Seconds before Ollama call times out (default: 30)
        dry_run:              If True, log routing decisions but always use fallback.
                              Useful for verifying routing without changing behaviour.
    """

    # Pydantic fields — required by BaseChatModel
    output_dir:           str   = ".agentshrink_output"
    fallback_model:       str   = "gpt-4o-mini"
    fallback_provider:    str   = "openai"
    confidence_threshold: float = 0.75
    trace_mode:           bool  = False
    ollama_timeout:       int   = 30
    dry_run:              bool  = False
    temperature:          float = 0.0

    # Private attributes (not Pydantic fields)
    _index:          Any = None
    _fallback_llm:   Any = None
    _routing_counts: dict = {}

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Load the centroid index immediately on init
        self._load_index()
        # Set up the fallback LLM
        self._setup_fallback()
        self._routing_counts = {"local": 0, "fallback": 0, "error": 0}

    def _load_index(self):
        """Load the CentroidIndex from the output directory."""
        try:
            from agentshrink.centroid_index import CentroidIndex
            self._index = CentroidIndex.from_output_dir(
                pathlib.Path(self.output_dir),
                confidence_threshold=self.confidence_threshold,
            )
            stats = self._index.get_stats()
            logger.info(
                f"ShrinkLLM loaded: "
                f"{stats['local_clusters']} clusters -> local SLM, "
                f"{stats['api_clusters']} clusters -> fallback"
            )
        except FileNotFoundError as e:
            logger.warning(
                f"CentroidIndex not found: {e}\n"
                f"Run 'agentshrink analyse' first. "
                f"Using fallback only until then."
            )
            self._index = None

    def _setup_fallback(self):
        """Set up the fallback LLM instance."""
        try:
            if self.fallback_provider == "ollama":
                from langchain_ollama import ChatOllama
                self._fallback_llm = ChatOllama(
                    model=self.fallback_model,
                    temperature=self.temperature,
                    base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                )
            elif self.fallback_provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI
                self._fallback_llm = ChatGoogleGenerativeAI(
                    model=self.fallback_model,
                    temperature=self.temperature,
                    google_api_key=os.getenv("GOOGLE_API_KEY"),
                )
            elif self.fallback_provider == "nvidia":
                from langchain_openai import ChatOpenAI
                self._fallback_llm = ChatOpenAI(
                    model=self.fallback_model,
                    temperature=self.temperature,
                    base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                    api_key=os.getenv("NVIDIA_API_KEY"),
                )
            else:
                from langchain_openai import ChatOpenAI
                base_url = os.getenv("OPENAI_BASE_URL", None)
                api_key = os.getenv("OPENAI_API_KEY", None)
                kwargs = {}
                if base_url:
                    kwargs["base_url"] = base_url
                if api_key:
                    kwargs["api_key"] = api_key
                self._fallback_llm = ChatOpenAI(
                    model=self.fallback_model,
                    temperature=self.temperature,
                    **kwargs,
                )
        except Exception as e:
            logger.error(f"Failed to set up fallback LLM: {e}")
            self._fallback_llm = None

    @property
    def _llm_type(self) -> str:
        """Required by BaseChatModel."""
        return "agentshrink_shrink_llm"

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Required by BaseChatModel."""
        return {
            "output_dir":           self.output_dir,
            "fallback_model":       self.fallback_model,
            "fallback_provider":    self.fallback_provider,
            "confidence_threshold": self.confidence_threshold,
        }

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Core method called by LangChain for every LLM invocation.

        This is where routing happens:
        1. Convert messages to prompt text
        2. Look up nearest cluster centroid
        3. Route to local Ollama OR fall back to API
        4. Return result in LangChain ChatResult format

        The run_manager (callback system) still fires normally —
        AgentShrinkLogger will still capture this call regardless
        of whether it goes to Ollama or OpenAI.
        """
        start_time = time.perf_counter()

        # Convert messages to prompt string for centroid lookup
        prompt_text = _messages_to_prompt(messages)

        # ── ROUTING DECISION ──
        if self._index is None or self.dry_run:
            decision = self._make_fallback_decision(
                "no index loaded" if self._index is None else "dry_run mode"
            )
        else:
            decision = self._index.route(prompt_text)

        # ── TRACE MODE ──
        if self.trace_mode:
            self._print_trace(decision, prompt_text)

        # ── PUSH TO DASHBOARD (non-blocking, never breaks agent) ──
        self._push_dashboard_event(decision, prompt_text, start_time)

        # ── EXECUTE ──
        if decision.is_local and not self.dry_run:
            result = self._call_ollama(messages, decision, stop)
        else:
            result = self._call_fallback(messages, stop, run_manager, **kwargs)

        # Track routing stats
        key = "local" if decision.is_local and not self.dry_run else "fallback"
        self._routing_counts[key] = self._routing_counts.get(key, 0) + 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"ShrinkLLM: cluster='{decision.cluster_name}' "
            f"model='{decision.model_name}' "
            f"conf={decision.confidence:.2f} "
            f"total={elapsed_ms:.0f}ms"
        )

        return result

    def _call_ollama(
        self,
        messages: List[BaseMessage],
        decision: Any,
        stop: Optional[List[str]] = None,
    ) -> ChatResult:
        """
        Call the local Ollama model.

        Falls back to API automatically if:
        - Ollama is not running
        - Model is not loaded
        - Call times out
        - Any other error occurs

        The fallback guarantee: this method NEVER raises an exception
        that would break the developer's agent.
        """
        try:
            import ollama

            ollama_messages = _messages_to_ollama_format(messages)

            options = {"temperature": self.temperature, "num_predict": 512}
            if stop:
                options["stop"] = stop

            response = ollama.chat(
                model=decision.model_name,
                messages=ollama_messages,
                options=options,
            )

            if isinstance(response, dict):
                content = (response.get("message") or {}).get("content", "") or ""
            else:
                content = response.message.content or ""
            return ChatResult(generations=[
                ChatGeneration(
                    message=AIMessage(content=content),
                    generation_info={
                        "model":      decision.model_name,
                        "cluster":    decision.cluster_name,
                        "confidence": decision.confidence,
                        "source":     "local_ollama",
                    }
                )
            ])

        except Exception as e:
            logger.warning(
                f"Ollama call failed for model '{decision.model_name}': {e}\n"
                f"Falling back to {self.fallback_model}."
            )
            self._routing_counts["error"] = self._routing_counts.get("error", 0) + 1
            # Fallback — NEVER break the developer's agent
            return self._call_fallback(messages, stop, None)

    def _call_fallback(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Call the original API LLM (GPT-4o-mini or whatever fallback_model is set to).
        This is always the safe path.
        """
        if self._fallback_llm is None:
            raise RuntimeError(
                "Fallback LLM not available. "
                "Check your fallback provider configuration."
            )

        # Delegate to the real ChatOpenAI
        return self._fallback_llm._generate(
            messages, stop=stop, run_manager=run_manager, **kwargs
        )

    def _make_fallback_decision(self, reason: str) -> Any:
        """Create a fallback routing decision."""
        from agentshrink.centroid_index import RoutingDecision
        return RoutingDecision(
            cluster_id=-1,
            cluster_name="unknown",
            model_name=self.fallback_model,
            model_display=f"Fallback ({self.fallback_model})",
            confidence=0.0,
            is_local=False,
            reason=reason,
            nearest_cluster_name=None,
            nearest_similarity=0.0,
            threshold=self.confidence_threshold,
        )

    def _push_dashboard_event(self, decision: Any, prompt_text: str, start_time: float):
        """
        Push routing decision to the FastAPI dashboard (non-blocking).
        The dashboard WebSocket broadcasts it to all connected browser tabs.

        Uses a fire-and-forget thread so the agent call is never delayed.
        If the dashboard isn't running — silently does nothing.
        """
        import threading
        import urllib.request

        def _push():
            try:
                payload = {
                    "cluster_name":  decision.cluster_name,
                    "model_name":    decision.model_name,
                    "model_display": decision.model_display,
                    "is_local":      decision.is_local,
                    "confidence":    round(decision.confidence, 3),
                    "nearest_cluster_name": getattr(decision, "nearest_cluster_name", None),
                    "nearest_similarity": round(getattr(decision, "nearest_similarity", 0.0), 3),
                    "threshold": round(getattr(decision, "threshold", self.confidence_threshold), 3),
                    "reason": getattr(decision, "reason", ""),
                    "prompt_preview": prompt_text[:80].replace("\n", " "),
                    "timestamp":     time.time(),
                }
                data = json.dumps(payload).encode()
                req  = urllib.request.Request(
                    "http://localhost:8000/api/routing/event",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=0.5)
            except Exception:
                pass  # Dashboard not running — silent no-op

        threading.Thread(target=_push, daemon=True).start()

    def _print_trace(self, decision: Any, prompt_text: str):
        """
        Print a routing trace line to the console.
        This is the live routing feed shown in the demo.
        Format: [timestamp] cluster → model (confidence) latency
        """
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")

        if decision.is_local:
            model_str = f"\033[92m{decision.model_name}\033[0m"  # Green
            source    = "LOCAL"
        else:
            model_str = f"\033[93m{self.fallback_model}\033[0m"  # Yellow
            source    = "FALL "

        prompt_preview = prompt_text[:60].replace("\n", " ").strip()
        print(
            f"[{ts}] {source} | "
            f"cluster='{decision.cluster_name}' -> "
            f"{model_str} "
            f"(conf={decision.confidence:.2f}, nearest={getattr(decision, 'nearest_cluster_name', 'n/a')}, "
            f"sim={getattr(decision, 'nearest_similarity', 0.0):.2f}, thr={getattr(decision, 'threshold', self.confidence_threshold):.2f}) | "
            f"'{prompt_preview}...'"
        )

    def get_routing_stats(self) -> dict:
        """Return routing statistics — useful for the dashboard."""
        total = sum(self._routing_counts.values())
        return {
            "total_calls": total,
            "local_calls": self._routing_counts.get("local", 0),
            "fallback_calls": self._routing_counts.get("fallback", 0),
            "error_fallbacks": self._routing_counts.get("error", 0),
            "local_pct": round(
                self._routing_counts.get("local", 0) / total * 100, 1
            ) if total > 0 else 0.0,
        }

    def reset_stats(self):
        """Reset routing statistics."""
        self._routing_counts = {"local": 0, "fallback": 0, "error": 0}

    # ── Stream support (delegates to fallback for now) ──
    # Streaming from local Ollama is possible but adds complexity.
    # For Phase 4: local calls don't stream, API calls do.
    # Phase 5 (dashboard) will add local streaming.

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGeneration]:
        """Stream — delegates to fallback LLM for now."""
        if self._fallback_llm and hasattr(self._fallback_llm, "_stream"):
            yield from self._fallback_llm._stream(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        else:
            result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            yield result.generations[0]
