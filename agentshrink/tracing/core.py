"""Core tracing primitives shared by callbacks and SDK wrappers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = pathlib.Path(
    os.getenv("AGENTSHRINK_DB_PATH", "~/.agentshrink/logs.db")
).expanduser()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id     TEXT NOT NULL UNIQUE,
    run_id      TEXT,
    timestamp   TEXT NOT NULL,
    latency_ms  INTEGER,
    prompt      TEXT NOT NULL,
    response    TEXT,
    prompt_hash TEXT,
    model_name  TEXT,
    node_name   TEXT,
    tokens_in   INTEGER DEFAULT 0,
    tokens_out  INTEGER DEFAULT 0,
    cost_usd    REAL DEFAULT 0.0,
    cluster_id  INTEGER DEFAULT -1,
    workflow_success  INTEGER DEFAULT 1,
    extra_metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_run_id       ON llm_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_node_name    ON llm_calls(node_name);
CREATE INDEX IF NOT EXISTS idx_prompt_hash  ON llm_calls(prompt_hash);
CREATE INDEX IF NOT EXISTS idx_cluster_id   ON llm_calls(cluster_id);
CREATE INDEX IF NOT EXISTS idx_timestamp    ON llm_calls(timestamp);
"""

TOKEN_PRICES = {
    "moonshotai/kimi-k2-instruct": {"in": 0.00014, "out": 0.00056},
    "gpt-4o": {"in": 0.0025, "out": 0.010},
    "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
    "gpt-4-turbo": {"in": 0.010, "out": 0.030},
    "gpt-3.5-turbo": {"in": 0.0005, "out": 0.0015},
    "claude-3-5-sonnet": {"in": 0.003, "out": 0.015},
    "gemini-2.0-flash": {"in": 0.0001, "out": 0.0004},
    "gemini-2.0-flash-lite": {"in": 0.000075, "out": 0.0003},
    "gemini-2.5-flash": {"in": 0.0003, "out": 0.0025},
}


def _custom_token_prices(model: str) -> Optional[dict]:
    override_model = os.getenv("AGENTSHRINK_PRICE_MODEL", "").strip()
    override_in = os.getenv("AGENTSHRINK_PRICE_IN_PER_1K", "").strip()
    override_out = os.getenv("AGENTSHRINK_PRICE_OUT_PER_1K", "").strip()
    if not (override_model and override_in and override_out):
        return None
    if model != override_model:
        return None
    try:
        return {"in": float(override_in), "out": float(override_out)}
    except ValueError:
        logger.warning("Invalid AGENTSHRINK custom price override; ignoring it.")
        return None


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    prices = _custom_token_prices(model) or TOKEN_PRICES.get(model, {"in": 0.001, "out": 0.002})
    cost = (tokens_in / 1000 * prices["in"]) + (tokens_out / 1000 * prices["out"])
    return round(cost, 6)


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def extract_prompt_text(prompts: Any) -> str:
    if isinstance(prompts, list):
        parts = []
        for p in prompts:
            if isinstance(p, list):
                for msg in p:
                    if hasattr(msg, "content"):
                        if isinstance(msg.content, str):
                            role = getattr(msg, "type", "user")
                            parts.append(f"[{role}]: {msg.content}")
                        elif isinstance(msg.content, list):
                            for chunk in msg.content:
                                if isinstance(chunk, dict) and chunk.get("type") == "text":
                                    parts.append(chunk.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                role = p.get("role", "user")
                content = p.get("content", "")
                if isinstance(content, str):
                    parts.append(f"[{role}]: {content}")
        return "\n".join(parts)
    if isinstance(prompts, str):
        return prompts
    return str(prompts)


class TraceStore:
    """Small helper around the shared SQLite trace schema."""

    def __init__(self, db_path: Optional[pathlib.Path] = None, run_id: Optional[str] = None):
        self.db_path = pathlib.Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or str(uuid.uuid4())
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(CREATE_TABLE_SQL)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def default_record(
        self,
        *,
        call_id: str,
        prompt: str,
        model_name: str,
        node_name: str = "unknown",
        timestamp: Optional[str] = None,
        response: str = "",
        latency_ms: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        workflow_success: int = 1,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "call_id": call_id,
            "run_id": self.run_id,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency_ms,
            "prompt": prompt,
            "response": response,
            "prompt_hash": hash_prompt(prompt),
            "model_name": model_name,
            "node_name": node_name,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": estimate_cost(model_name, tokens_in, tokens_out),
            "cluster_id": -1,
            "workflow_success": workflow_success,
            "extra_metadata": "{}" if extra_metadata is None else json.dumps(extra_metadata, sort_keys=True),
        }

    def write_record(self, record: Dict[str, Any]):
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO llm_calls
                (call_id, run_id, timestamp, latency_ms, prompt, response,
                 prompt_hash, model_name, node_name, tokens_in, tokens_out,
                 cost_usd, cluster_id, workflow_success, extra_metadata)
                VALUES
                (:call_id, :run_id, :timestamp, :latency_ms, :prompt, :response,
                 :prompt_hash, :model_name, :node_name, :tokens_in, :tokens_out,
                 :cost_usd, :cluster_id, :workflow_success, :extra_metadata)
                """,
                record,
            )
            conn.commit()

    def mark_run_failed(self):
        with self._get_conn() as conn:
            conn.execute("UPDATE llm_calls SET workflow_success=0 WHERE run_id=?", (self.run_id,))
            conn.commit()

    def get_summary(self) -> Dict[str, Any]:
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM llm_calls")
                total_calls = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(DISTINCT run_id) FROM llm_calls")
                total_runs = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT node_name, COUNT(*) as count, AVG(latency_ms) as avg_latency
                    FROM llm_calls
                    GROUP BY node_name
                    ORDER BY count DESC
                    """
                )
                nodes = cursor.fetchall()
                cursor.execute("SELECT SUM(cost_usd) FROM llm_calls")
                total_cost = cursor.fetchone()[0] or 0.0
                cursor.execute("SELECT SUM(tokens_in + tokens_out) FROM llm_calls")
                total_tokens = cursor.fetchone()[0] or 0
                return {
                    "total_calls": total_calls,
                    "total_runs": total_runs,
                    "nodes": [{"name": n[0], "count": n[1], "avg_latency_ms": round(n[2] or 0)} for n in nodes],
                    "total_cost_usd": round(total_cost, 4),
                    "total_tokens": total_tokens,
                    "db_path": str(self.db_path),
                }
        except sqlite3.Error as e:
            return {"error": str(e)}
