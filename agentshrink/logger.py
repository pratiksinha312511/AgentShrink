"""
agentshrink/logger.py
=====================
PHASE 1 — The Instrumentation Layer

This is the most important file in the entire project.
Everything AgentShrink does depends on this being correct.

HOW IT WORKS:
  LangChain has a "callbacks" system — hooks that fire
  before and after every LLM call. We implement two hooks:
    - on_llm_start:  fires BEFORE the LLM is called
    - on_llm_end:    fires AFTER the LLM responds

  Between these two hooks, we capture everything:
  the prompt, the response, the latency, the token count,
  which node fired it, and whether the workflow succeeded.

  All data is written to a local SQLite database.
  Nothing leaves your machine. Everything is private.

USAGE (you'll use this in Phase 1 testing):
  from agentshrink.logger import AgentShrinkLogger
  from target_agent.agent import build_agent

  logger = AgentShrinkLogger()
  agent = build_agent(callbacks=[logger])
  agent.invoke({"customer_message": "I need a refund..."})
  # → Check ~/.agentshrink/logs.db for the captured data
"""

import os
import time
import uuid
import json
import sqlite3
import hashlib
import logging
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import BaseMessage

load_dotenv()

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# DATABASE SETUP
# SQLite is perfect here: local, fast, queryable,
# no server needed, single file you can inspect directly.
# ─────────────────────────────────────────────

DEFAULT_DB_PATH = pathlib.Path(
    os.getenv("AGENTSHRINK_DB_PATH", "~/.agentshrink/logs.db")
).expanduser()

# This is the schema for every captured LLM call.
# Every column is here for a specific reason — explained inline.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS llm_calls (

    -- Identity
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id     TEXT NOT NULL UNIQUE,  -- UUID for this specific call
    run_id      TEXT,                  -- UUID for the agent workflow run
                                       -- All 5 nodes in one agent.invoke()
                                       -- share the same run_id.
                                       -- This is how we group calls per run.

    -- Timing
    timestamp   TEXT NOT NULL,         -- ISO format UTC
    latency_ms  INTEGER,               -- How long the LLM took to respond

    -- What was sent and received
    prompt      TEXT NOT NULL,         -- The full prompt sent to the LLM
    response    TEXT,                  -- The LLM's response
    prompt_hash TEXT,                  -- SHA256 of prompt for deduplication
                                       -- Two identical prompts → same hash
                                       -- We use this in Phase 2 to dedup

    -- Model info
    model_name  TEXT,                  -- "gpt-4o", "gpt-4o-mini", etc.
    node_name   TEXT,                  -- Which LangGraph node fired this call
                                       -- "classify", "extract", "draft_reply"
                                       -- etc. This maps calls to agent nodes.

    -- Token counts (used for cost calculation)
    tokens_in   INTEGER DEFAULT 0,     -- Prompt tokens
    tokens_out  INTEGER DEFAULT 0,     -- Completion tokens
    cost_usd    REAL DEFAULT 0.0,      -- Estimated cost in USD

    -- Quality tracking (filled in later by AgentShrink)
    cluster_id  INTEGER DEFAULT -1,    -- Which cluster this call belongs to
                                       -- -1 means "not clustered yet"
                                       -- Set during Phase 2 (clustering)

    -- Outcome tracking
    workflow_success  INTEGER DEFAULT 1,  -- 1=success, 0=failure
                                          -- We mark this after the full
                                          -- agent.invoke() completes.
                                          -- Failed runs produce lower quality
                                          -- training data, so we filter them.

    -- Metadata
    extra_metadata TEXT DEFAULT '{}'   -- JSON string for any extra info
);

-- Indexes for fast querying in Phase 2
CREATE INDEX IF NOT EXISTS idx_run_id       ON llm_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_node_name    ON llm_calls(node_name);
CREATE INDEX IF NOT EXISTS idx_prompt_hash  ON llm_calls(prompt_hash);
CREATE INDEX IF NOT EXISTS idx_cluster_id   ON llm_calls(cluster_id);
CREATE INDEX IF NOT EXISTS idx_timestamp    ON llm_calls(timestamp);
"""

# GPT token prices as of 2025 (USD per 1000 tokens)
# Used to calculate cost savings when we replace calls with free local SLMs
TOKEN_PRICES = {
    "gpt-4o":           {"in": 0.0025, "out": 0.010},
    "gpt-4o-mini":      {"in": 0.00015, "out": 0.0006},
    "gpt-4-turbo":      {"in": 0.010,  "out": 0.030},
    "gpt-3.5-turbo":    {"in": 0.0005, "out": 0.0015},
    "claude-3-5-sonnet": {"in": 0.003, "out": 0.015},
}


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate the USD cost of a single LLM call."""
    prices = TOKEN_PRICES.get(model, {"in": 0.001, "out": 0.002})
    cost = (tokens_in / 1000 * prices["in"]) + (tokens_out / 1000 * prices["out"])
    return round(cost, 6)


def _hash_prompt(prompt: str) -> str:
    """
    Create a short hash of the prompt for deduplication.
    We use the first 16 chars of SHA256 — collision-resistant enough
    for our purposes and readable in the database.
    """
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def _extract_prompt_text(prompts: Any) -> str:
    """
    LangChain passes prompts in different formats depending on
    whether it's a completion model or a chat model.
    We handle both and return clean plain text.
    """
    if isinstance(prompts, list):
        parts = []
        for p in prompts:
            if isinstance(p, list):
                # Chat model: list of BaseMessage objects
                for msg in p:
                    if hasattr(msg, 'content'):
                        if isinstance(msg.content, str):
                            role = getattr(msg, 'type', 'user')
                            parts.append(f"[{role}]: {msg.content}")
                        elif isinstance(msg.content, list):
                            for chunk in msg.content:
                                if isinstance(chunk, dict) and chunk.get('type') == 'text':
                                    parts.append(chunk.get('text', ''))
            elif isinstance(p, str):
                parts.append(p)
        return "\n".join(parts)
    elif isinstance(prompts, str):
        return prompts
    return str(prompts)


# ─────────────────────────────────────────────
# THE LOGGER CLASS
# This is the main component of Phase 1.
# ─────────────────────────────────────────────

class AgentShrinkLogger(BaseCallbackHandler):
    """
    Drop-in LangChain callback that captures every LLM call to SQLite.

    Add this to any LangChain/LangGraph agent with ONE LINE:
        llm = ChatOpenAI(..., callbacks=[AgentShrinkLogger()])

    That's it. Your agent works exactly as before.
    Every LLM call is now silently recorded to ~/.agentshrink/logs.db

    The logger adds under 5ms latency per call (just a SQLite write).
    """

    def __init__(
        self,
        db_path: Optional[pathlib.Path] = None,
        run_id: Optional[str] = None,
    ):
        super().__init__()

        self.db_path = pathlib.Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Each AgentShrinkLogger instance gets a unique run_id.
        # Create a new AgentShrinkLogger() per agent.invoke() call
        # if you want to track which run each call came from.
        # Or share one instance if you don't need run-level grouping.
        self.run_id = run_id or str(uuid.uuid4())

        # Track in-progress calls: call_id → start_time + metadata
        # We need this because on_llm_start and on_llm_end are separate.
        self._in_flight: Dict[str, Dict] = {}

        # Set up SQLite connection
        self._init_db()

        logger.debug(f"AgentShrinkLogger initialized. DB: {self.db_path}, Run: {self.run_id[:8]}")

    def _init_db(self):
        """Create the database and table if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(CREATE_TABLE_SQL)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection. Always use as context manager."""
        return sqlite3.connect(self.db_path)

    # ─────────────────────────────────
    # HOOK 1: on_llm_start
    # Fires BEFORE the LLM call is made.
    # We record: when it started, what was sent, which model.
    # ─────────────────────────────────

    def on_llm_start(
        self,
        serialized: Dict[str, Any],   # Info about the LLM being called
        prompts: List[str],            # The prompts being sent
        *,
        run_id: uuid.UUID,             # LangChain's internal run ID for THIS call
        parent_run_id: Optional[uuid.UUID] = None,  # Parent run (the agent workflow)
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Called before each LLM invocation.
        We record the start time and prompt here.
        """
        call_id = str(run_id)
        start_time = time.perf_counter()

        # Extract the model name from the serialized LLM info
        # The path depends on the LLM class — we try multiple locations
        model_name = (
            serialized.get("kwargs", {}).get("model_name") or
            serialized.get("kwargs", {}).get("model") or
            serialized.get("name", "unknown")
        )

        # Extract the node name from LangGraph metadata
        # LangGraph passes the node name in the metadata dict
        node_name = "unknown"
        if metadata and "langgraph_node" in metadata:
            node_name = metadata["langgraph_node"]
        elif tags:
            # Sometimes node name is in tags
            for tag in tags:
                if tag.startswith("seq:step:") is False:
                    node_name = tag
                    break

        # Store everything we'll need when on_llm_end fires
        self._in_flight[call_id] = {
            "call_id":   call_id,
            "start_time": start_time,
            "prompt":    _extract_prompt_text(prompts),
            "model_name": model_name,
            "node_name":  node_name,
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
        """
        Same as on_llm_start but for chat models (ChatOpenAI, ChatAnthropic).
        LangChain calls this instead of on_llm_start for chat models.
        We flatten the messages into a single prompt string.
        """
        # Flatten chat messages into a string for storage
        flat_prompts = []
        for message_list in messages:
            for msg in message_list:
                if hasattr(msg, 'content'):
                    content = msg.content
                    if isinstance(content, str):
                        role = getattr(msg, 'type', 'user')
                        flat_prompts.append(f"[{role}]: {content}")
        flat_prompt = "\n".join(flat_prompts)

        call_id = str(run_id)
        start_time = time.perf_counter()

        model_name = (
            serialized.get("kwargs", {}).get("model_name") or
            serialized.get("kwargs", {}).get("model") or
            serialized.get("name", "unknown")
        )

        node_name = "unknown"
        if metadata and "langgraph_node" in metadata:
            node_name = metadata["langgraph_node"]

        self._in_flight[call_id] = {
            "call_id":    call_id,
            "start_time": start_time,
            "prompt":     flat_prompt,
            "model_name": model_name,
            "node_name":  node_name,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────────────────────────
    # HOOK 2: on_llm_end
    # Fires AFTER the LLM responds.
    # We calculate latency, extract tokens, and write to SQLite.
    # ─────────────────────────────────

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        parent_run_id: Optional[uuid.UUID] = None,
        **kwargs: Any,
    ) -> None:
        """
        Called after each LLM response arrives.
        This is where we complete the record and write to the database.
        """
        call_id = str(run_id)

        if call_id not in self._in_flight:
            # This can happen if the callback was attached after the call started
            logger.warning(f"on_llm_end called for unknown call_id: {call_id[:8]}")
            return

        in_flight = self._in_flight.pop(call_id)

        # Calculate latency
        latency_ms = int((time.perf_counter() - in_flight["start_time"]) * 1000)

        # Extract the response text
        response_text = ""
        try:
            if response.generations:
                gen = response.generations[0]
                if gen:
                    response_text = getattr(gen[0], "text", "") or \
                                    getattr(getattr(gen[0], "message", None), "content", "") or ""
        except (IndexError, AttributeError):
            pass

        # Extract token usage
        tokens_in = tokens_out = 0
        if response.llm_output:
            usage = response.llm_output.get("token_usage") or \
                    response.llm_output.get("usage", {})
            tokens_in  = usage.get("prompt_tokens", 0) or \
                         usage.get("input_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0) or \
                         usage.get("output_tokens", 0)

        model_name = in_flight["model_name"]
        cost_usd = _estimate_cost(model_name, tokens_in, tokens_out)

        # Write to SQLite
        record = {
            "call_id":         call_id,
            "run_id":          self.run_id,
            "timestamp":       in_flight["timestamp"],
            "latency_ms":      latency_ms,
            "prompt":          in_flight["prompt"],
            "response":        response_text,
            "prompt_hash":     _hash_prompt(in_flight["prompt"]),
            "model_name":      model_name,
            "node_name":       in_flight["node_name"],
            "tokens_in":       tokens_in,
            "tokens_out":      tokens_out,
            "cost_usd":        cost_usd,
            "workflow_success": 1,      # Default to success; mark failures separately
            "cluster_id":      -1,      # Not clustered yet
            "extra_metadata":  "{}",
        }

        self._write_record(record)

        logger.debug(
            f"Captured call: node={record['node_name']}, "
            f"model={record['model_name']}, "
            f"latency={latency_ms}ms, "
            f"tokens={tokens_in}+{tokens_out}"
        )

    def _write_record(self, record: Dict[str, Any]):
        """Write a single call record to SQLite."""
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO llm_calls
                    (call_id, run_id, timestamp, latency_ms, prompt, response,
                     prompt_hash, model_name, node_name, tokens_in, tokens_out,
                     cost_usd, cluster_id, workflow_success, extra_metadata)
                    VALUES
                    (:call_id, :run_id, :timestamp, :latency_ms, :prompt, :response,
                     :prompt_hash, :model_name, :node_name, :tokens_in, :tokens_out,
                     :cost_usd, :cluster_id, :workflow_success, :extra_metadata)
                """, record)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to write call record: {e}")

    def mark_run_failed(self):
        """
        Call this if the agent workflow fails.
        Marks all calls from this run as workflow_success=0.
        Failed-run calls are filtered out during Phase 2 curation
        because they produce unreliable training examples.
        """
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE llm_calls SET workflow_success=0 WHERE run_id=?",
                    (self.run_id,)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to mark run as failed: {e}")

    def on_llm_error(self, error: Exception, *, run_id: uuid.UUID, **kwargs):
        """If a single LLM call errors, mark it but don't crash."""
        call_id = str(run_id)
        self._in_flight.pop(call_id, None)  # Clean up in-flight tracker
        logger.warning(f"LLM error on call {call_id[:8]}: {error}")

    # ─────────────────────────────────
    # CONVENIENCE METHODS
    # Useful for building the status command in Phase 1
    # ─────────────────────────────────

    def get_summary(self) -> Dict[str, Any]:
        """
        Returns a summary of what's been captured so far.
        Used by the CLI: agentshrink status
        """
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()

                # Total calls
                cursor.execute("SELECT COUNT(*) FROM llm_calls")
                total_calls = cursor.fetchone()[0]

                # Unique runs
                cursor.execute("SELECT COUNT(DISTINCT run_id) FROM llm_calls")
                total_runs = cursor.fetchone()[0]

                # Calls per node
                cursor.execute("""
                    SELECT node_name, COUNT(*) as count, AVG(latency_ms) as avg_latency
                    FROM llm_calls
                    GROUP BY node_name
                    ORDER BY count DESC
                """)
                nodes = cursor.fetchall()

                # Total estimated cost
                cursor.execute("SELECT SUM(cost_usd) FROM llm_calls")
                total_cost = cursor.fetchone()[0] or 0.0

                # Total tokens
                cursor.execute("SELECT SUM(tokens_in + tokens_out) FROM llm_calls")
                total_tokens = cursor.fetchone()[0] or 0

                return {
                    "total_calls":  total_calls,
                    "total_runs":   total_runs,
                    "nodes":        [{"name": n[0], "count": n[1], "avg_latency_ms": round(n[2] or 0)} for n in nodes],
                    "total_cost_usd": round(total_cost, 4),
                    "total_tokens": total_tokens,
                    "db_path":      str(self.db_path),
                }
        except sqlite3.Error as e:
            return {"error": str(e)}

    @classmethod
    def from_db(cls, db_path: Optional[pathlib.Path] = None) -> "AgentShrinkLogger":
        """
        Create a logger instance connected to an existing database.
        Used when you want to inspect logs from a previous session.
        """
        return cls(db_path=db_path)
