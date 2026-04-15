"""OpenAI-compatible SDK wrapper for AgentShrink tracing."""

from __future__ import annotations

import time
import uuid
from typing import Any, Iterable, Optional

from agentshrink.tracing.core import TraceStore, extract_prompt_text


def _extract_usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return 0, 0
    if hasattr(usage, "prompt_tokens"):
        return int(getattr(usage, "prompt_tokens", 0) or 0), int(getattr(usage, "completion_tokens", 0) or 0)
    if isinstance(usage, dict):
        return int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)
    return 0, 0


def _extract_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices", [])
    if not choices:
        return ""
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None and isinstance(first, dict):
        message = first.get("message")
    if message is None:
        return ""
    if hasattr(message, "content"):
        return getattr(message, "content", "") or ""
    if isinstance(message, dict):
        return str(message.get("content", "") or "")
    return ""


class _OpenAIStreamWrapper:
    def __init__(self, stream: Iterable[Any], store: TraceStore, record_base: dict):
        self._stream = iter(stream)
        self._store = store
        self._record_base = record_base
        self._parts: list[str] = []
        self._tokens_in = 0
        self._tokens_out = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self._stream)
        except StopIteration:
            record = dict(self._record_base)
            record["response"] = "".join(self._parts)
            record["tokens_in"] = self._tokens_in
            record["tokens_out"] = self._tokens_out
            self._store.write_record(record)
            raise

        choices = getattr(chunk, "choices", None)
        if choices:
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            if content:
                self._parts.append(content)
        prompt_tokens, completion_tokens = _extract_usage(chunk)
        self._tokens_in = max(self._tokens_in, prompt_tokens)
        self._tokens_out = max(self._tokens_out, completion_tokens)
        return chunk


def wrap_openai_client(client: Any, *, db_path=None, run_id: Optional[str] = None, default_node_name: str = "unknown"):
    """Wrap an OpenAI-compatible client so chat.completions.create is traced to AgentShrink SQLite."""

    store = TraceStore(db_path=db_path, run_id=run_id)
    original_create = client.chat.completions.create

    def traced_create(*args, **kwargs):
        call_id = str(uuid.uuid4())
        start = time.perf_counter()
        messages = kwargs.get("messages") or []
        prompt = extract_prompt_text(messages)
        model_name = kwargs.get("model", "unknown")
        metadata = kwargs.get("metadata") or {}
        node_name = metadata.get("agentshrink_node") or metadata.get("langgraph_node") or default_node_name
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        response = original_create(*args, **kwargs)
        latency_ms = int((time.perf_counter() - start) * 1000)

        record = store.default_record(
            call_id=call_id,
            prompt=prompt,
            model_name=model_name,
            node_name=node_name,
            timestamp=timestamp,
            latency_ms=latency_ms,
        )

        if kwargs.get("stream"):
            return _OpenAIStreamWrapper(response, store, record)

        tokens_in, tokens_out = _extract_usage(response)
        record["response"] = _extract_text(response)
        record["tokens_in"] = tokens_in
        record["tokens_out"] = tokens_out
        store.write_record(record)
        return response

    client.chat.completions.create = traced_create
    client._agentshrink_trace_store = store
    return client
