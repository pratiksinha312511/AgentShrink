"""
Phase A verification tests:
  - shared tracing core still works through AgentShrinkLogger
  - OpenAI-compatible wrapper writes to the same SQLite schema
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import types
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from agentshrink import AgentShrinkLogger, wrap_openai_client
from agentshrink.tracing.core import TraceStore


def _temp_db() -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / f"agentshrink_phaseA_{uuid.uuid4().hex}.db"


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeGeneration:
    def __init__(self, text: str):
        self.text = text
        self.message = _FakeMessage(text)


class _FakeLLMResult:
    def __init__(self):
        self.generations = [[_FakeGeneration("hello back")]]
        self.llm_output = {"token_usage": {"prompt_tokens": 12, "completion_tokens": 5}}


class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeChoiceMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeChoiceMessage(content)


class _FakeDelta:
    def __init__(self, content: str):
        self.content = content


class _FakeStreamChoice:
    def __init__(self, content: str):
        self.delta = _FakeDelta(content)


class _FakeChatCompletion:
    def __init__(self, content: str, prompt_tokens: int = 7, completion_tokens: int = 9):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage(prompt_tokens, completion_tokens)


class _FakeStreamChunk:
    def __init__(self, content: str = "", prompt_tokens: int = 0, completion_tokens: int = 0):
        self.choices = [_FakeStreamChoice(content)]
        self.usage = _FakeUsage(prompt_tokens, completion_tokens)


class _FakeChatCompletions:
    def create(self, *args, **kwargs):
        if kwargs.get("stream"):
            return iter([
                _FakeStreamChunk("wrapped ", 0, 0),
                _FakeStreamChunk("stream", 7, 9),
            ])
        return _FakeChatCompletion("wrapped response")


class _FakeOpenAIClient:
    def __init__(self):
        self.chat = types.SimpleNamespace(completions=_FakeChatCompletions())


def test_trace_store_summary():
    db = _temp_db()
    store = TraceStore(db_path=db, run_id="run-1")
    store.write_record(
        store.default_record(
            call_id="call-1",
            prompt="[user]: hi",
            model_name="gpt-4o-mini",
            node_name="demo_node",
            response="hello",
            latency_ms=123,
            tokens_in=10,
            tokens_out=5,
        )
    )
    summary = store.get_summary()
    assert summary["total_calls"] == 1
    assert summary["total_runs"] == 1
    assert summary["nodes"][0]["name"] == "demo_node"


def test_langchain_logger_uses_shared_core():
    db = _temp_db()
    logger_instance = AgentShrinkLogger(db_path=db, run_id="run-logger")
    run_id = uuid.uuid4()
    logger_instance.on_llm_start(
        {"kwargs": {"model_name": "gpt-4o-mini"}},
        ["Tell me a joke"],
        run_id=run_id,
        metadata={"langgraph_node": "joke_node"},
    )
    logger_instance.on_llm_end(_FakeLLMResult(), run_id=run_id)

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT node_name, model_name, tokens_in, tokens_out FROM llm_calls"
        ).fetchone()
    assert row == ("joke_node", "gpt-4o-mini", 12, 5)


def test_chat_model_start_path_and_failed_run():
    db = _temp_db()
    logger_instance = AgentShrinkLogger(db_path=db, run_id="run-chat")
    run_id = uuid.uuid4()

    class _ChatMsg:
        def __init__(self, msg_type: str, content: str):
            self.type = msg_type
            self.content = content

    logger_instance.on_chat_model_start(
        {"kwargs": {"model": "gpt-4o-mini"}},
        [[_ChatMsg("system", "Be concise"), _ChatMsg("human", "Hello there")]],
        run_id=run_id,
        metadata={"langgraph_node": "chat_node"},
    )
    logger_instance.on_llm_end(_FakeLLMResult(), run_id=run_id)
    logger_instance.mark_run_failed()

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT node_name, prompt, workflow_success FROM llm_calls"
        ).fetchone()
    assert row[0] == "chat_node"
    assert "[system]: Be concise" in row[1]
    assert row[2] == 0


def test_on_llm_error_cleans_inflight():
    db = _temp_db()
    logger_instance = AgentShrinkLogger(db_path=db, run_id="run-error")
    run_id = uuid.uuid4()
    logger_instance.on_llm_start(
        {"kwargs": {"model_name": "gpt-4o-mini"}},
        ["Prompt before error"],
        run_id=run_id,
    )
    assert str(run_id) in logger_instance._in_flight
    logger_instance.on_llm_error(RuntimeError("boom"), run_id=run_id)
    assert str(run_id) not in logger_instance._in_flight


def test_wrap_openai_client_records_call():
    db = _temp_db()
    client = wrap_openai_client(_FakeOpenAIClient(), db_path=db, run_id="run-wrapper", default_node_name="sdk_node")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Say hi"},
        ],
    )
    assert response.choices[0].message.content == "wrapped response"

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT run_id, node_name, model_name, prompt, response, tokens_in, tokens_out FROM llm_calls"
        ).fetchone()

    assert row[0] == "run-wrapper"
    assert row[1] == "sdk_node"
    assert row[2] == "gpt-4o-mini"
    assert "[system]: You are helpful." in row[3]
    assert row[4] == "wrapped response"
    assert row[5] == 7
    assert row[6] == 9


def test_wrap_openai_client_records_streaming_call():
    db = _temp_db()
    client = wrap_openai_client(_FakeOpenAIClient(), db_path=db, run_id="run-stream", default_node_name="stream_node")
    chunks = list(
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Stream hi"},
            ],
            stream=True,
        )
    )
    assert len(chunks) == 2

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT node_name, response, tokens_in, tokens_out FROM llm_calls"
        ).fetchone()
    assert row[0] == "stream_node"
    assert row[1] == "wrapped stream"
    assert row[2] == 7
    assert row[3] == 9


if __name__ == "__main__":
    test_trace_store_summary()
    test_langchain_logger_uses_shared_core()
    test_chat_model_start_path_and_failed_run()
    test_on_llm_error_cleans_inflight()
    test_wrap_openai_client_records_call()
    test_wrap_openai_client_records_streaming_call()
    print("Phase A instrumentation tests passed.")
