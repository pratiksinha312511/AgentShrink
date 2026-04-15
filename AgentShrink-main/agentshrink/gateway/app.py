"""FastAPI gateway skeleton with an OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from agentshrink.gateway.local import LocalOllamaExecutor
from agentshrink.gateway.router import GatewayRouter
from agentshrink.gateway.schemas import ChatCompletionsRequest
from agentshrink.gateway.upstream import OpenAICompatibleUpstream
from agentshrink.tracing.core import TraceStore, extract_prompt_text


def _build_routing_metadata(decision: Any, body: ChatCompletionsRequest, execution_provider: str, route_mode: str, route_reason: str) -> dict[str, Any]:
    return {
        "gateway_provider": execution_provider,
        "gateway_mode": route_mode,
        "route_cluster_name": getattr(decision, "cluster_name", "unknown"),
        "route_model_name": getattr(decision, "model_name", body.model),
        "route_model_display": getattr(decision, "model_display", body.model),
        "route_confidence": round(float(getattr(decision, "confidence", 0.0)), 4),
        "route_is_local": bool(getattr(decision, "is_local", False)),
        "route_reason": route_reason,
        "nearest_cluster_name": getattr(decision, "nearest_cluster_name", None),
        "nearest_similarity": round(float(getattr(decision, "nearest_similarity", 0.0)), 4),
        "threshold": round(float(getattr(decision, "threshold", 0.0)), 4),
    }


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def _write_gateway_record(
    *,
    store: TraceStore,
    call_id: str,
    prompt: str,
    response: dict[str, Any],
    body: ChatCompletionsRequest,
    node_name: str,
    latency_ms: int,
    metadata: dict[str, Any],
):
    usage = response.get("usage") or {}
    content = ""
    choices = response.get("choices") or []
    if choices:
        content = ((choices[0].get("message") or {}).get("content")) or ""

    record = store.default_record(
        call_id=call_id,
        prompt=prompt,
        model_name=response.get("model") or body.model,
        node_name=node_name,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        response=content,
        latency_ms=latency_ms,
        tokens_in=int(usage.get("prompt_tokens", 0) or 0),
        tokens_out=int(usage.get("completion_tokens", 0) or 0),
        extra_metadata=metadata,
    )
    store.write_record(record)


def create_gateway_app(
    upstream: Any | None = None,
    db_path=None,
    router: Any | None = None,
    local_executor: Any | None = None,
    expected_api_key: str | None = None,
) -> FastAPI:
    app = FastAPI(title="AgentShrink Gateway", version="0.1.0")
    app.state.upstream = upstream or OpenAICompatibleUpstream()
    app.state.router = router or GatewayRouter()
    app.state.local_executor = local_executor or LocalOllamaExecutor()
    app.state.trace_store = TraceStore(db_path=db_path)
    app.state.expected_api_key = (expected_api_key or "").strip()

    if not app.state.expected_api_key:
        import logging as _logging
        _logging.getLogger("agentshrink.gateway").warning(
            "Gateway started without a project token. All requests will require a Bearer token. "
            "Run 'agentshrink init' to generate one, or set it in the project config."
        )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def root():
        return JSONResponse(
            {
                "name": "AgentShrink Gateway",
                "status": "ok",
                "message": "OpenAI-compatible gateway is running.",
                "endpoints": {
                    "health": "/health",
                    "chat_completions": "/v1/chat/completions",
                },
                "auth": {
                    "scheme": "Bearer",
                    "credential": "project token",
                },
                "usage": {
                    "python_example": (
                        "from openai import OpenAI; "
                        "client = OpenAI(base_url='http://127.0.0.1:8100/v1', api_key='your_project_token')"
                    ),
                },
            }
        )

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    @app.post("/v1/chat/completions")
    async def chat_completions(
        body: ChatCompletionsRequest,
        authorization: str | None = Header(default=None),
        x_agentshrink_node: str | None = Header(default=None),
        x_agentshrink_run_id: str | None = Header(default=None),
    ):
        expected_api_key = app.state.expected_api_key
        actual_token = _extract_bearer_token(authorization)
        if expected_api_key:
            if actual_token != expected_api_key:
                raise HTTPException(status_code=401, detail="Invalid or missing AgentShrink project token.")
        elif not actual_token:
            raise HTTPException(
                status_code=401,
                detail="Bearer token required. No project token is configured — run 'agentshrink init' to generate one.",
            )

        call_id = str(uuid.uuid4())
        started = time.perf_counter()
        store = app.state.trace_store
        if x_agentshrink_run_id:
            store.run_id = x_agentshrink_run_id

        payload = body.model_dump(exclude_none=True)
        metadata = payload.get("metadata") or {}
        node_name = metadata.get("agentshrink_node") or metadata.get("langgraph_node") or x_agentshrink_node or "gateway"
        prompt = extract_prompt_text([m.model_dump() for m in body.messages])

        decision = app.state.router.route_prompt(prompt)
        route_mode = "upstream"
        route_reason = getattr(decision, "reason", "")
        execution_provider = getattr(app.state.upstream, "provider", "unknown")
        routed_model_name = getattr(decision, "model_name", body.model)
        routing_metadata = _build_routing_metadata(decision, body, execution_provider, route_mode, route_reason)

        if body.stream:
            async def stream_response():
                nonlocal route_mode, route_reason, execution_provider, routing_metadata

                chunks: list[str] = []
                final_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                model_name = body.model

                try:
                    if getattr(decision, "is_local", False):
                        route_mode = "local"
                        execution_provider = "ollama"
                        iterator = app.state.local_executor.iter_chat_completions(payload, routed_model_name)
                        model_name = routed_model_name
                    else:
                        iterator = app.state.upstream.iter_chat_completions(payload)
                except Exception as exc:
                    route_mode = "fallback_after_error"
                    route_reason = f"{route_reason}; local execution failed" if route_reason else "local execution failed"
                    execution_provider = getattr(app.state.upstream, "provider", "unknown")
                    iterator = app.state.upstream.iter_chat_completions(payload)

                routing_metadata = _build_routing_metadata(decision, body, execution_provider, route_mode, route_reason)

                for chunk in iterator:
                    choices = chunk.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        piece = delta.get("content") or ""
                        if piece:
                            chunks.append(piece)
                        if choices[0].get("finish_reason"):
                            final_usage = chunk.get("usage") or final_usage
                    model_name = chunk.get("model", model_name)
                    yield f"data: {json.dumps(chunk)}\n\n"

                response_payload = {
                    "id": f"chatcmpl-stream-final-{int(time.time())}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(chunks)}, "finish_reason": "stop"}],
                    "usage": final_usage,
                }
                latency_ms = int((time.perf_counter() - started) * 1000)
                _write_gateway_record(
                    store=store,
                    call_id=call_id,
                    prompt=prompt,
                    response=response_payload,
                    body=body,
                    node_name=node_name,
                    latency_ms=latency_ms,
                    metadata=routing_metadata,
                )
                yield "data: [DONE]\n\n"

            return StreamingResponse(stream_response(), media_type="text/event-stream")

        try:
            if getattr(decision, "is_local", False):
                route_mode = "local"
                execution_provider = "ollama"
                response = app.state.local_executor.chat_completions_create(
                    payload,
                    routed_model_name,
                )
            else:
                response = app.state.upstream.chat_completions_create(payload)
        except Exception as exc:
            route_mode = "fallback_after_error"
            route_reason = f"{route_reason}; local execution failed" if route_reason else "local execution failed"
            execution_provider = getattr(app.state.upstream, "provider", "unknown")
            response = app.state.upstream.chat_completions_create(payload)

        latency_ms = int((time.perf_counter() - started) * 1000)
        routing_metadata = _build_routing_metadata(decision, body, execution_provider, route_mode, route_reason)
        _write_gateway_record(
            store=store,
            call_id=call_id,
            prompt=prompt,
            response=response,
            body=body,
            node_name=node_name,
            latency_ms=latency_ms,
            metadata=routing_metadata,
        )
        return response

    return app
