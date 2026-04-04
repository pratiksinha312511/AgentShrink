"""
Phase B verification tests:
  - OpenAI-compatible gateway endpoint accepts chat completion payloads
  - request/response is logged through the shared trace core
  - passthrough abstraction can be injected and tested without network
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from agentshrink.gateway import create_gateway_app
from agentshrink.gateway.upstream import OpenAICompatibleUpstream
from agentshrink.centroid_index import RoutingDecision


def _temp_db() -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / f"agentshrink_phaseB_{uuid.uuid4().hex}.db"


class _FakeUpstream:
    provider = "nvidia"
    last_payload = None

    def chat_completions_create(self, payload: dict):
        self.last_payload = payload
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1710000000,
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "gateway response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 6, "total_tokens": 17},
        }

    def iter_chat_completions(self, payload: dict):
        self.last_payload = payload
        yield {
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "created": 1710000000,
            "model": payload["model"],
            "choices": [{"index": 0, "delta": {"content": "gateway "}, "finish_reason": None}],
        }
        yield {
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "created": 1710000000,
            "model": payload["model"],
            "choices": [{"index": 0, "delta": {"content": "stream"}, "finish_reason": None}],
        }
        yield {
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "created": 1710000000,
            "model": payload["model"],
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        }


class _FakeRouter:
    def __init__(self, decision):
        self.decision = decision

    def route_prompt(self, prompt_text: str):
        return self.decision


class _FakeLocalExecutor:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.calls = []

    def chat_completions_create(self, payload: dict, model_name: str):
        self.calls.append((payload, model_name))
        if self.should_fail:
            raise RuntimeError("local boom")
        return {
            "id": "chatcmpl-local",
            "object": "chat.completion",
            "created": 1710000001,
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "local response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }


def test_gateway_health():
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=_temp_db()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_gateway_rejects_missing_project_token_when_auth_is_enabled():
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=_temp_db(), expected_api_key="as_live_testtoken"))
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "moonshotai/kimi-k2-instruct",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 401
    assert "project token" in response.json()["detail"].lower()


def test_gateway_accepts_valid_project_token_when_auth_is_enabled():
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=_temp_db(), expected_api_key="as_live_testtoken"))
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer as_live_testtoken"},
        json={
            "model": "moonshotai/kimi-k2-instruct",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "gateway response"


def test_gateway_chat_completion_passthrough_and_logging():
    db = _temp_db()
    upstream = _FakeUpstream()
    client = TestClient(create_gateway_app(upstream=upstream, db_path=db))
    response = client.post(
        "/v1/chat/completions",
        headers={"x-agentshrink-node": "gateway_test_node", "x-agentshrink-run-id": "gateway-run"},
        json={
            "model": "moonshotai/kimi-k2-instruct",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Say hi from the gateway"},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "gateway response"

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT run_id, node_name, model_name, prompt, response, tokens_in, tokens_out, extra_metadata FROM llm_calls"
        ).fetchone()

    assert row[0] == "gateway-run"
    assert row[1] == "gateway_test_node"
    assert row[2] == "moonshotai/kimi-k2-instruct"
    assert "[system]: You are helpful." in row[3]
    assert row[4] == "gateway response"
    assert row[5] == 11
    assert row[6] == 6
    assert '"gateway_provider": "nvidia"' in row[7]
    assert upstream.last_payload["model"] == "moonshotai/kimi-k2-instruct"
    assert upstream.last_payload["messages"][1]["content"] == "Say hi from the gateway"


def test_gateway_streaming_passthrough_and_logging():
    db = _temp_db()
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=db))
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "moonshotai/kimi-k2-instruct",
            "messages": [{"role": "user", "content": "stream this"}],
            "stream": True,
        },
    ) as response:
        assert response.status_code == 200
        body = "\n".join(response.iter_text())
    assert "gateway " in body
    assert "stream" in body
    assert "[DONE]" in body

    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT response, tokens_in, tokens_out, extra_metadata FROM llm_calls").fetchone()
    assert row[0] == "gateway stream"
    assert row[1] == 10
    assert row[2] == 4
    assert '"gateway_mode": "upstream"' in row[3]


def test_gateway_metadata_overrides_header_node_name():
    db = _temp_db()
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=db))
    response = client.post(
        "/v1/chat/completions",
        headers={"x-agentshrink-node": "header_node", "x-agentshrink-run-id": "run-meta"},
        json={
            "model": "moonshotai/kimi-k2-instruct",
            "messages": [{"role": "user", "content": "Use metadata node"}],
            "metadata": {"agentshrink_node": "metadata_node"},
        },
    )
    assert response.status_code == 200
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT run_id, node_name FROM llm_calls").fetchone()
    assert row == ("run-meta", "metadata_node")


def test_gateway_multiple_calls_keep_separate_run_ids():
    db = _temp_db()
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=db))

    first = client.post(
        "/v1/chat/completions",
        headers={"x-agentshrink-node": "node_a", "x-agentshrink-run-id": "run-a"},
        json={"model": "moonshotai/kimi-k2-instruct", "messages": [{"role": "user", "content": "first"}]},
    )
    second = client.post(
        "/v1/chat/completions",
        headers={"x-agentshrink-node": "node_b", "x-agentshrink-run-id": "run-b"},
        json={"model": "moonshotai/kimi-k2-instruct", "messages": [{"role": "user", "content": "second"}]},
    )
    assert first.status_code == 200
    assert second.status_code == 200

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT run_id, node_name, prompt FROM llm_calls ORDER BY id").fetchall()
    assert rows[0][0] == "run-a"
    assert rows[0][1] == "node_a"
    assert "first" in rows[0][2]
    assert rows[1][0] == "run-b"
    assert rows[1][1] == "node_b"
    assert "second" in rows[1][2]


def test_gateway_routes_to_local_when_cluster_is_local():
    db = _temp_db()
    decision = RoutingDecision(
        cluster_id=5,
        cluster_name="format_json_output",
        provider="ollama",
        model_name="llama3.2:3b",
        model_display="Local (llama3.2:3b)",
        confidence=0.91,
        is_local=True,
        reason="cluster matched local route",
        nearest_cluster_name="format_json_output",
        nearest_similarity=0.91,
        threshold=0.75,
    )
    local = _FakeLocalExecutor()
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=db, router=_FakeRouter(decision), local_executor=local))
    response = client.post(
        "/v1/chat/completions",
        json={"model": "ignored-by-router", "messages": [{"role": "user", "content": "format this"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "local response"
    assert local.calls[0][1] == "llama3.2:3b"

    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT response, extra_metadata FROM llm_calls").fetchone()
    assert row[0] == "local response"
    assert '"gateway_mode": "local"' in row[1]
    assert '"route_cluster_name": "format_json_output"' in row[1]


def test_gateway_falls_back_to_upstream_when_local_executor_errors():
    db = _temp_db()
    decision = RoutingDecision(
        cluster_id=5,
        cluster_name="format_json_output",
        provider="ollama",
        model_name="llama3.2:3b",
        model_display="Local (llama3.2:3b)",
        confidence=0.91,
        is_local=True,
        reason="cluster matched local route",
        nearest_cluster_name="format_json_output",
        nearest_similarity=0.91,
        threshold=0.75,
    )
    local = _FakeLocalExecutor(should_fail=True)
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=db, router=_FakeRouter(decision), local_executor=local))
    response = client.post(
        "/v1/chat/completions",
        json={"model": "ignored-by-router", "messages": [{"role": "user", "content": "format this"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "gateway response"

    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT response, extra_metadata FROM llm_calls").fetchone()
    assert row[0] == "gateway response"
    assert '"gateway_mode": "fallback_after_error"' in row[1]
    assert 'local execution failed' in row[1]


def test_gateway_uses_upstream_for_unmatched_route():
    db = _temp_db()
    decision = RoutingDecision(
        cluster_id=-1,
        cluster_name="unknown",
        provider="nvidia",
        model_name="moonshotai/kimi-k2-instruct",
        model_display="NVIDIA (moonshotai/kimi-k2-instruct)",
        confidence=0.0,
        is_local=False,
        reason="low confidence",
        nearest_cluster_name="format_json_output",
        nearest_similarity=0.41,
        threshold=0.75,
    )
    client = TestClient(create_gateway_app(upstream=_FakeUpstream(), db_path=db, router=_FakeRouter(decision), local_executor=_FakeLocalExecutor()))
    response = client.post(
        "/v1/chat/completions",
        json={"model": "moonshotai/kimi-k2-instruct", "messages": [{"role": "user", "content": "hard prompt"}]},
    )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "gateway response"

    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT extra_metadata FROM llm_calls").fetchone()
    assert '"gateway_mode": "upstream"' in row[0]


def test_mock_upstream_runs_without_network():
    db = _temp_db()
    client = TestClient(create_gateway_app(upstream=OpenAICompatibleUpstream(provider="mock"), db_path=db))
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "mock-model",
            "messages": [{"role": "user", "content": "free local test"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"].startswith("[mock:mock-model]")

    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT response, extra_metadata FROM llm_calls").fetchone()
    assert "free local test" in row[0]
    assert '"gateway_provider": "mock"' in row[1]
    assert '"route_cluster_name": "unknown"' in row[1]


if __name__ == "__main__":
    test_gateway_health()
    test_gateway_chat_completion_passthrough_and_logging()
    test_gateway_streaming_passthrough_and_logging()
    test_gateway_metadata_overrides_header_node_name()
    test_gateway_multiple_calls_keep_separate_run_ids()
    test_gateway_routes_to_local_when_cluster_is_local()
    test_gateway_falls_back_to_upstream_when_local_executor_errors()
    test_gateway_uses_upstream_for_unmatched_route()
    test_mock_upstream_runs_without_network()
    print("Phase B gateway tests passed.")
