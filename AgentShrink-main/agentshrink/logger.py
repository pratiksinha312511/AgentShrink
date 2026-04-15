"""
LangChain callback instrumentation for AgentShrink.

This file preserves the original public API:
  - AgentShrinkLogger(...)
  - .mark_run_failed()
  - .get_summary()
  - .from_db(...)

Internally it now uses the shared tracing core so future SDK wrappers and
gateway instrumentation can write to the same schema.
"""

from __future__ import annotations

import logging
import pathlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from agentshrink.tracing.core import (
    CREATE_TABLE_SQL,
    DEFAULT_DB_PATH,
    TraceStore,
    estimate_cost as _estimate_cost,
    extract_prompt_text as _extract_prompt_text,
    hash_prompt as _hash_prompt,
)

load_dotenv()
logger = logging.getLogger(__name__)


class AgentShrinkLogger(BaseCallbackHandler):
    """Drop-in LangChain callback handler that stores LLM traces in SQLite."""

    def __init__(self, db_path: Optional[pathlib.Path] = None, run_id: Optional[str] = None):
        super().__init__()
        self.db_path = pathlib.Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or str(uuid.uuid4())
        self._store = TraceStore(db_path=self.db_path, run_id=self.run_id)
        self._in_flight: Dict[str, Dict[str, Any]] = {}
        logger.debug("AgentShrinkLogger initialized. DB: %s, Run: %s", self.db_path, self.run_id[:8])

    def _init_db(self):
        self._store._init_db()

    def _get_conn(self):
        return self._store._get_conn()

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        call_id = str(run_id)
        model_name = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("name", "unknown")
        )

        node_name = "unknown"
        if metadata and "langgraph_node" in metadata:
            node_name = metadata["langgraph_node"]
        elif tags:
            for tag in tags:
                if not tag.startswith("seq:step:"):
                    node_name = tag
                    break

        self._in_flight[call_id] = {
            "call_id": call_id,
            "start_time": time.perf_counter(),
            "prompt": _extract_prompt_text(prompts),
            "model_name": model_name,
            "node_name": node_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        call_id = str(run_id)
        model_name = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("name", "unknown")
        )
        node_name = "unknown"
        if metadata and "langgraph_node" in metadata:
            node_name = metadata["langgraph_node"]

        self._in_flight[call_id] = {
            "call_id": call_id,
            "start_time": time.perf_counter(),
            "prompt": _extract_prompt_text(messages),
            "model_name": model_name,
            "node_name": node_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        **kwargs: Any,
    ) -> None:
        call_id = str(run_id)
        if call_id not in self._in_flight:
            logger.warning("on_llm_end called for unknown call_id: %s", call_id[:8])
            return

        in_flight = self._in_flight.pop(call_id)
        latency_ms = int((time.perf_counter() - in_flight["start_time"]) * 1000)

        response_text = ""
        try:
            if response.generations:
                gen = response.generations[0]
                if gen:
                    response_text = (
                        getattr(gen[0], "text", "")
                        or getattr(getattr(gen[0], "message", None), "content", "")
                        or ""
                    )
        except (IndexError, AttributeError, TypeError):
            pass

        tokens_in = 0
        tokens_out = 0
        if response.llm_output:
            usage = response.llm_output.get("token_usage") or response.llm_output.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)

        record = self._store.default_record(
            call_id=call_id,
            prompt=in_flight["prompt"],
            model_name=in_flight["model_name"],
            node_name=in_flight["node_name"],
            timestamp=in_flight["timestamp"],
            response=response_text,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        self._write_record(record)

        logger.debug(
            "Captured call: node=%s, model=%s, latency=%sms, tokens=%s+%s",
            record["node_name"],
            record["model_name"],
            latency_ms,
            tokens_in,
            tokens_out,
        )

    def _write_record(self, record: Dict[str, Any]):
        try:
            self._store.write_record(record)
        except Exception as e:
            logger.error("Failed to write call record: %s", e)

    def mark_run_failed(self):
        try:
            self._store.mark_run_failed()
        except Exception as e:
            logger.error("Failed to mark run as failed: %s", e)

    def on_llm_error(self, error: Exception, *, run_id: uuid.UUID, **kwargs):
        call_id = str(run_id)
        self._in_flight.pop(call_id, None)
        logger.warning("LLM error on call %s: %s", call_id[:8], error)

    def get_summary(self) -> Dict[str, Any]:
        try:
            return self._store.get_summary()
        except Exception as e:
            return {"error": str(e)}

    @classmethod
    def from_db(cls, db_path: Optional[pathlib.Path] = None) -> "AgentShrinkLogger":
        return cls(db_path=db_path)


__all__ = [
    "AgentShrinkLogger",
    "CREATE_TABLE_SQL",
    "DEFAULT_DB_PATH",
    "_estimate_cost",
    "_extract_prompt_text",
    "_hash_prompt",
]
