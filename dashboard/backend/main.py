"""
dashboard/backend/main.py
==========================
PHASE 5 — FastAPI Backend

Serves all AgentShrink data to the Next.js frontend via:
  REST API   → static data (clusters, report, status)
  WebSocket  → live routing trace (real-time streaming)

Endpoints:
  GET  /api/status              → call summary from SQLite
  GET  /api/clusters            → cluster info + UMAP coords
  GET  /api/report              → replaceability report
  GET  /api/routing/stats       → current routing statistics
  POST /api/analyse             → trigger full analysis pipeline
  WS   /ws/routing-trace        → live routing decisions stream

Start with:
    cd dashboard/backend
    uvicorn main:app --reload --port 8000
"""

import json
import time
import asyncio
import pathlib
import sqlite3
import logging
import os
from collections import deque
import threading
from typing import Optional
from contextlib import asynccontextmanager
from contextlib import suppress

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths — relative to project root
PROJECT_ROOT  = pathlib.Path(__file__).parent.parent.parent
DB_PATH       = pathlib.Path.home() / ".agentshrink" / "logs.db"
OUTPUT_DIR    = PROJECT_ROOT / ".agentshrink_output"
SYS_PATH_ROOT = str(PROJECT_ROOT)

import sys
sys.path.insert(0, SYS_PATH_ROOT)

from agentshrink.logger import _estimate_cost
from agentshrink.model_catalog import (
    choose_best_model,
    cluster_task_kind,
    delete_model,
    load_model_catalog,
    save_model_catalog,
    upsert_model,
)
from agentshrink.project_config import (
    get_eval_samples_per_cluster,
    get_judge_min_interval_s,
    get_judge_model_id,
    get_remote_min_interval_s,
    save_project_config,
)
from agentshrink.finetune.jobs import FineTuneJobStore
from agentshrink.finetune.runtime import (
    backend_statuses,
    choose_default_model,
    deploy_to_ollama,
    evaluate_deployed_model,
    write_training_artifacts,
)


def _load_cluster_info() -> dict | None:
    cluster_info_path = OUTPUT_DIR / "cluster_info.json"
    if not cluster_info_path.exists():
        return None
    with open(cluster_info_path, encoding="utf-8") as f:
        return json.load(f)


def _load_existing_routing_config() -> dict:
    path = OUTPUT_DIR / "routing_config.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _estimate_tokens_from_text(text: str) -> int:
    """
    Lightweight token estimate for local-only logs where providers do not
    return usage metadata. This keeps cost-savings demos meaningful.
    """
    if not text:
        return 0
    # Rough heuristic: ~4 chars per token for English support text.
    return max(1, round(len(text) / 4))


def _build_node_statuses(cluster_info: dict | None) -> dict:
    if not cluster_info:
        return {}
    node_statuses = {}
    for cid, info in cluster_info.get("clusters", {}).items():
        for node_name, count in (info.get("node_distribution") or {}).items():
            current = node_statuses.setdefault(node_name, {
                "status": "clustered",
                "cluster_count": 0,
                "prompt_count": 0,
                "cluster_names": [],
            })
            current["cluster_count"] += 1
            current["prompt_count"] += int(count)
            current["cluster_names"].append(info.get("name", f"cluster_{cid}"))
    return node_statuses


def _heuristic_report_from_clusters(cluster_info: dict | None) -> dict:
    if not cluster_info:
        raise HTTPException(status_code=404, detail="No cluster data found. Run analysis first.")

    catalog = load_model_catalog(OUTPUT_DIR)
    fallback_provider = os.getenv("TARGET_AGENT_PROVIDER", "openai").strip().lower()
    clusters = []
    for cid, info in cluster_info.get("clusters", {}).items():
        node_dist = info.get("node_distribution", {}) or {}
        task_kind = cluster_task_kind(info)
        chosen_model = choose_best_model(info, catalog)
        best_score = 0.92 if task_kind == "simple" else (0.82 if task_kind == "general" else 0.72)
        recommendation = "keep_llm"
        best_slm = None
        best_slm_display = None
        best_provider = fallback_provider
        needs_fine_tuning = False
        fine_tune_base_model = None

        if chosen_model:
            best_slm = chosen_model["model_name"]
            best_slm_display = chosen_model["display_name"]
            best_provider = chosen_model["provider"]
            if task_kind == "simple":
                recommendation = "replace_now"
                needs_fine_tuning = False
            elif chosen_model.get("local"):
                recommendation = "fine_tune"
                needs_fine_tuning = True
                fine_tune_base_model = chosen_model["model_name"]
            else:
                recommendation = "keep_llm" if int(chosen_model.get("quality_tier", 0)) < 4 else "replace_now"

        clusters.append({
            "cluster_id": int(cid),
            "cluster_name": info.get("name", f"cluster_{cid}"),
            "cluster_size": int(info.get("size", 0)),
            "recommendation": recommendation,
            "best_slm": best_slm,
            "best_slm_display": best_slm_display,
            "best_provider": best_provider,
            "best_score": best_score,
            "needs_fine_tuning": needs_fine_tuning,
            "fine_tune_base_model": fine_tune_base_model,
            "estimated_cost_saving_pct": 100.0 if recommendation == "replace_now" else (45.0 if recommendation == "fine_tune" else 0.0),
            "node_distribution": node_dist,
            "evaluations": [{
                "slm_name": best_slm or "fallback",
                "slm_display": best_slm_display or "Fallback",
                "provider": best_provider,
                "correctness_score": best_score,
                "format_score": best_score,
                "completeness_score": max(best_score - 0.05, 0.0),
                "composite_score": best_score,
                "avg_latency_ms": round(info.get("avg_latency_ms", 0.0), 1),
                "p95_latency_ms": round(info.get("avg_latency_ms", 0.0) * 1.15, 1),
                "n_evaluated": min(int(info.get("size", 0)), 20),
                "sample_comparisons": [{
                    "prompt": (info.get("sample_prompts") or [""])[0][:160],
                    "reference": "Original logged reference response.",
                    "candidate": f"Heuristic recommendation for cluster {info.get('name', cid)}.",
                }],
            }],
        })

    total_calls = sum(c["cluster_size"] for c in clusters) or 1
    replace_now = [c for c in clusters if c["recommendation"] == "replace_now"]
    fine_tune = [c for c in clusters if c["recommendation"] == "fine_tune"]
    keep_llm = [c for c in clusters if c["recommendation"] == "keep_llm"]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "heuristic": True,
        "summary": {
            "total_clusters": len(clusters),
            "replace_now_count": len(replace_now),
            "fine_tune_count": len(fine_tune),
            "keep_llm_count": len(keep_llm),
            "pct_calls_replaceable_now": round(sum(c["cluster_size"] for c in replace_now) / total_calls * 100, 1),
            "pct_calls_replaceable_with_finetune": round((sum(c["cluster_size"] for c in replace_now) + sum(c["cluster_size"] for c in fine_tune)) / total_calls * 100, 1),
            "models_evaluated": [model["model_name"] for model in catalog.get("models", []) if model.get("enabled")],
        },
        "clusters": clusters,
    }


def _load_clustered_df():
    clustered_df_path = OUTPUT_DIR / "clustered_df.parquet"
    if not clustered_df_path.exists():
        raise HTTPException(status_code=404, detail="No clustered dataframe found. Run analysis first.")
    import pandas as pd
    return pd.read_parquet(clustered_df_path)


def _load_saved_cluster_snapshot() -> dict:
    cluster_info_payload = _load_cluster_info()
    if not cluster_info_payload:
        raise HTTPException(status_code=404, detail="No saved cluster snapshot found. Run analysis first.")

    clustered_df = _load_clustered_df()
    cluster_info = {
        int(cid): info
        for cid, info in (cluster_info_payload.get("clusters") or {}).items()
    }

    centroids = {}
    centroids_path = OUTPUT_DIR / "centroids.npy"
    centroid_ids = [int(cid) for cid in cluster_info_payload.get("centroid_ids", [])]
    if centroids_path.exists() and centroid_ids:
        centroid_array = np.load(centroids_path)
        for idx, cid in enumerate(centroid_ids):
            if idx < len(centroid_array):
                centroids[int(cid)] = centroid_array[idx]

    return {
        "df": clustered_df,
        "embeddings": np.empty((0, 0), dtype=np.float32),
        "centroids": centroids,
        "cluster_info": cluster_info,
    }


def _targeted_report_filename(cluster_ids: list[int]) -> str:
    if len(cluster_ids) == 1:
        return f"replaceability_report_cluster_{cluster_ids[0]}.json"
    joined = "_".join(str(cid) for cid in cluster_ids)
    return f"replaceability_report_clusters_{joined}.json"


def _prepare_finetune_payload(cluster_id: int):
    from agentshrink.finetuner import FineTuner

    df = _load_clustered_df()
    cluster_info = _load_cluster_info() or {}
    cluster_meta = (cluster_info.get("clusters") or {}).get(str(cluster_id))
    if not cluster_meta:
        raise HTTPException(status_code=404, detail="Cluster metadata not found.")

    cluster_df = df[df["cluster_id"] == cluster_id].copy()
    if len(cluster_df) == 0:
        raise HTTPException(status_code=404, detail="Cluster rows not found.")

    ft = FineTuner(output_dir=OUTPUT_DIR)
    dataset_path = ft.export_dataset(
        cluster_id=cluster_id,
        cluster_name=cluster_meta["name"],
        cluster_df=cluster_df,
        min_examples=10,
    )

    # Build prompt/completion rows without depending on notebook-only paths.
    clean_df = cluster_df[
        (cluster_df["workflow_success"] == 1) &
        (cluster_df["prompt"].notna()) &
        (cluster_df["response"].notna()) &
        (cluster_df["prompt"].str.len() > 20) &
        (cluster_df["response"].str.len() > 1)
    ].copy()
    training_rows = [
        {
            "prompt": str(row["prompt"]),
            "completion": str(row["response"]),
            "node_name": str(row.get("node_name", "")),
        }
        for _, row in clean_df.iterrows()
    ]
    if not training_rows:
        raise HTTPException(status_code=400, detail="Cluster does not have enough clean examples to train.")

    return {
        "cluster_meta": cluster_meta,
        "dataset_path": dataset_path,
        "training_rows": training_rows,
    }


def _run_finetune_job(job_id: str, backend: str, config: dict, training_rows: list[dict], hf_token: str | None = None):
    from agentshrink.finetuner import FineTuner
    from agentshrink.finetune.hf_trainer import run_hf_training
    from agentshrink.finetune.modal_trainer import run_modal_training

    stop_event = finetune_stop_events[job_id]

    def on_status(message: str, progress: int):
        job_store.update_job(job_id, status="running", phase=message, progress=progress)
        job_store.append_log(job_id, message)

    def on_log(message: str):
        job_store.append_log(job_id, message)

    def on_metric(metric: dict):
        job_store.append_metric(job_id, metric)

    try:
        job = job_store.update_job(
            job_id,
            status="running",
            phase="Preparing training job",
            progress=5,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        artifact_dir = OUTPUT_DIR / "finetuned" / job_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        run_config = dict(config)
        run_config["artifact_dir"] = str(artifact_dir)

        if backend == "modal":
            result = run_modal_training(
                run_config,
                training_rows,
                on_status=on_status,
                on_log=on_log,
                on_call=lambda call: finetune_modal_calls.__setitem__(job_id, call),
                should_stop=stop_event.is_set,
            )
        elif backend == "huggingface":
            if not hf_token:
                raise RuntimeError("HF_TOKEN is missing. Add it in .env or the request body.")
            result = run_hf_training(
                run_config,
                training_rows,
                hf_token=hf_token,
                on_status=on_status,
                on_log=on_log,
                on_metric=on_metric,
                on_process=lambda proc: finetune_processes.__setitem__(job_id, proc),
                should_stop=stop_event.is_set,
            )
        else:
            raise RuntimeError(f"Unsupported backend '{backend}'")

        if stop_event.is_set():
            job_store.update_job(
                job_id,
                status="stopped",
                phase="Stopped by user",
                progress=0,
                ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            return

        artifact_info = write_training_artifacts(result, artifact_dir)
        job_store.update_job(
            job_id,
            status="completed",
            phase="Training finished",
            progress=100,
            result={
                "artifact_kind": artifact_info["artifact_kind"],
                "deploy_base_model": result.get("deploy_base_model", config["deploy_base_model"]),
                "base_model": config["base_model"],
            },
            artifacts=artifact_info,
            can_register=True,
            ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        on_log("Training complete. Ready to deploy into Ollama.")
    except Exception as exc:
        status = "stopped" if stop_event.is_set() else "failed"
        job_store.update_job(
            job_id,
            status=status,
            phase="Training stopped" if status == "stopped" else "Training failed",
            error=None if status == "stopped" else str(exc),
            ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        if status == "stopped":
            job_store.append_log(job_id, "Training stopped by user.")
        else:
            job_store.append_log(job_id, str(exc), level="error")
    finally:
        finetune_threads.pop(job_id, None)
        finetune_stop_events.pop(job_id, None)
        finetune_processes.pop(job_id, None)
        finetune_modal_calls.pop(job_id, None)


def _reconcile_finetune_job(job: dict) -> dict:
    """
    Persisted jobs survive backend restarts, but the in-memory thread/process/call
    handles do not. If a job still says queued/running after restart and there is
    no live handle attached anymore, mark it as stopped so the UI can recover.
    """
    if not job:
        return job
    status = job.get("status")
    if status not in {"queued", "running", "deploying"}:
        return job

    job_id = job["job_id"]
    has_live_handle = any((
        job_id in finetune_threads,
        job_id in finetune_processes,
        job_id in finetune_modal_calls,
        job_id in finetune_deploy_threads,
    ))
    if has_live_handle:
        return job

    updated = job_store.update_job(
        job_id,
        status="stopped",
        phase="Stopped after backend restart",
        error=None,
        ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    job_store.append_log(job_id, "Recovered stale in-progress job after backend restart. Marked as stopped.")
    return job_store.get_job(job_id) or updated


def _run_deploy_job(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        return

    def update_deploy(phase: str, progress: int):
        job_store.update_job(job_id, status="deploying", phase=phase, progress=progress)
        job_store.append_log(job_id, phase)

    try:
        update_deploy("Preparing local deployment", 8)
        deploy_result = deploy_to_ollama(
            cluster_name=job["cluster_name"],
            cluster_id=int(job["cluster_id"]),
            artifact_info=job["artifacts"],
            deploy_base_model=job["result"].get("deploy_base_model") or job.get("deploy_base_model"),
            output_dir=OUTPUT_DIR,
            on_log=lambda message: job_store.append_log(job_id, message),
        )

        update_deploy("Running post-train accuracy check", 72)
        accuracy = evaluate_deployed_model(
            deploy_result["ollama_name"],
            _prepare_finetune_payload(int(job["cluster_id"]))["training_rows"],
            sample_size=2,
            on_log=lambda message: job_store.append_log(job_id, message),
        )

        from agentshrink.finetuner import FineTuner

        ft = FineTuner(output_dir=OUTPUT_DIR)
        update_deploy("Registering model for routing", 90)
        ok = ft.register_fine_tuned_model(
            cluster_id=int(job["cluster_id"]),
            ollama_name=deploy_result["ollama_name"],
            display_name=deploy_result["display_name"],
        )
        if not ok:
            raise RuntimeError("Model deployed locally, but AgentShrink could not register it for routing.")

        job_store.update_job(
            job_id,
            status="deployed",
            phase="Deployed and registered",
            progress=100,
            registered_model=deploy_result["ollama_name"],
            can_register=True,
            result={
                **job.get("result", {}),
                "post_train_accuracy": accuracy,
                "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        job_store.append_log(job_id, f"Deployment complete. Registered {deploy_result['ollama_name']} for routing.")
    except Exception as exc:
        job_store.update_job(job_id, status="completed", phase="Deployment failed", progress=100, error=str(exc))
        job_store.append_log(job_id, str(exc), level="error")
    finally:
        finetune_deploy_threads.pop(job_id, None)


# ─────────────────────────────────────────────
# WEBSOCKET CONNECTION MANAGER
# Broadcasts live routing events to all connected dashboard tabs
# ─────────────────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections for live routing feed."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"Dashboard connected. Total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        logger.info(f"Dashboard disconnected. Total: {len(self.active)}")

    async def broadcast(self, data: dict):
        """Send routing event to all connected dashboard tabs."""
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
job_store = FineTuneJobStore(OUTPUT_DIR)
finetune_stop_events: dict[str, threading.Event] = {}
finetune_threads: dict[str, threading.Thread] = {}
finetune_processes: dict[str, object] = {}
finetune_modal_calls: dict[str, object] = {}
finetune_deploy_threads: dict[str, threading.Thread] = {}

# Global routing event queue — ShrinkLLM pushes events here,
# WebSocket handler reads and broadcasts them
routing_event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
analysis_log_buffer: deque[dict] = deque(maxlen=400)
analysis_running: bool = False


def _record_analysis_log(line: str, stream: str = "stdout"):
    entry = {
        "type": "analysis_log",
        "line": line.rstrip("\n"),
        "stream": stream,
        "timestamp": time.time(),
    }
    analysis_log_buffer.append(entry)
    return entry


# ─────────────────────────────────────────────
# APP LIFECYCLE
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background WebSocket broadcaster on app start."""
    task = asyncio.create_task(broadcast_routing_events())
    logger.info("AgentShrink dashboard backend started")
    logger.info(f"DB: {DB_PATH}")
    logger.info(f"Output: {OUTPUT_DIR}")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="AgentShrink Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# REST ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """
    GET /api/status
    Returns call summary from SQLite — shown on Overview screen.
    """
    if not DB_PATH.exists():
        return {
            "total_calls": 0, "total_runs": 0,
            "total_tokens": 0, "total_cost_usd": 0.0,
            "nodes": [], "daily_counts": [],
            "db_path": str(DB_PATH),
            "has_data": False,
        }

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Summary stats
        c.execute("SELECT COUNT(*) as n FROM llm_calls WHERE workflow_success=1")
        total_calls = c.fetchone()["n"]

        c.execute("SELECT COUNT(DISTINCT run_id) as n FROM llm_calls")
        total_runs = c.fetchone()["n"]

        c.execute("SELECT COALESCE(SUM(tokens_in+tokens_out),0) as n FROM llm_calls")
        total_tokens = c.fetchone()["n"]

        c.execute("SELECT COALESCE(SUM(cost_usd),0) as n FROM llm_calls")
        total_cost = c.fetchone()["n"]

        c.execute("""
            SELECT prompt, response, tokens_in, tokens_out, model_name
            FROM llm_calls
            WHERE workflow_success=1
        """)
        rows = c.fetchall()

        baseline_model = (
            os.getenv("AGENTSHRINK_ESTIMATE_MODEL")
            or os.getenv("TARGET_AGENT_OPENAI_MODEL")
            or os.getenv("TARGET_AGENT_GEMINI_MODEL")
            or "gpt-4o-mini"
        )
        estimated_baseline_cost = 0.0
        local_call_count = 0
        fallback_call_count = 0

        for row in rows:
            prompt = row["prompt"] or ""
            response = row["response"] or ""
            tokens_in = int(row["tokens_in"] or 0)
            tokens_out = int(row["tokens_out"] or 0)
            if tokens_in <= 0:
                tokens_in = _estimate_tokens_from_text(prompt)
            if tokens_out <= 0 and response:
                tokens_out = _estimate_tokens_from_text(response)

            estimated_baseline_cost += _estimate_cost(baseline_model, tokens_in, tokens_out)

            model_name = (row["model_name"] or "").lower()
            if any(local_hint in model_name for local_hint in ("llama", "qwen", "mistral", "gemma", "phi", "deepseek", "agentshrink-")):
                local_call_count += 1
            else:
                fallback_call_count += 1

        # Per-node breakdown
        c.execute("""
            SELECT node_name, COUNT(*) as count,
                   AVG(latency_ms) as avg_latency,
                   AVG(cost_usd) as avg_cost
            FROM llm_calls WHERE workflow_success=1
            GROUP BY node_name ORDER BY count DESC
        """)
        nodes = [dict(row) for row in c.fetchall()]

        # Daily call counts (last 14 days) for the chart
        c.execute("""
            SELECT DATE(timestamp) as day, COUNT(*) as count
            FROM llm_calls
            WHERE timestamp >= DATE('now', '-14 days')
            GROUP BY day ORDER BY day ASC
        """)
        daily_counts = [dict(row) for row in c.fetchall()]

        cluster_info = _load_cluster_info()
        analysis_done = cluster_info is not None
        report_done   = (OUTPUT_DIR / "replaceability_report.json").exists()
        node_statuses = _build_node_statuses(cluster_info)

    return {
        "total_calls":   total_calls,
        "total_runs":    total_runs,
        "total_tokens":  total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "estimated_baseline_model": baseline_model,
        "estimated_baseline_cost_usd": round(estimated_baseline_cost, 4),
        "estimated_savings_usd": round(max(estimated_baseline_cost - total_cost, 0.0), 4),
        "estimated_savings_pct": round(
            (max(estimated_baseline_cost - total_cost, 0.0) / estimated_baseline_cost * 100)
            if estimated_baseline_cost > 0 else 0.0,
            1,
        ),
        "local_call_count": local_call_count,
        "fallback_call_count": fallback_call_count,
        "nodes":         nodes,
        "daily_counts":  daily_counts,
        "db_path":       str(DB_PATH),
        "has_data":      total_calls > 0,
        "analysis_done": analysis_done,
        "report_done":   report_done,
        "ready_for_analysis": total_calls >= 50,
        "node_statuses": node_statuses,
    }


@app.get("/api/clusters")
async def get_clusters():
    """
    GET /api/clusters
    Returns cluster info + UMAP 2D coordinates for the cluster map.
    """
    cluster_info_path = OUTPUT_DIR / "cluster_info.json"
    clustered_df_path = OUTPUT_DIR / "clustered_df.parquet"

    if not cluster_info_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No cluster data found. Run: agentshrink analyse"
        )

    with open(cluster_info_path) as f:
        cluster_info = json.load(f)

    # Load UMAP coordinates for the scatter plot
    points = []
    if clustered_df_path.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(clustered_df_path)

            # Color palette matching our design system
            palette = [
                "#1D9E75", "#7F77DD", "#EF9F27",
                "#D85A30", "#185FA5", "#9F3F7A",
                "#5D8A1A", "#C44B4B", "#2B8B8B"
            ]

            for _, row in df.iterrows():
                cid = int(row.get("cluster_id", -1))
                if cid == -1:
                    continue
                points.append({
                    "x":           float(row.get("umap_x", 0)),
                    "y":           float(row.get("umap_y", 0)),
                    "cluster_id":  cid,
                    "cluster_name": str(row.get("cluster_name", f"cluster_{cid}")),
                    "color":       row.get("cluster_color", palette[cid % len(palette)]),
                    "prompt_preview": str(row.get("prompt", ""))[:80],
                    "node_name":   str(row.get("node_name", "")),
                })
        except Exception as e:
            logger.warning(f"Could not load cluster points: {e}")

    return {
        "n_clusters":    cluster_info.get("n_clusters", 0),
        "n_noise":       cluster_info.get("n_noise", 0),
        "cluster_names": cluster_info.get("cluster_names", {}),
        "clusters":      cluster_info.get("clusters", {}),
        "points":        points,
    }


@app.get("/api/report")
async def get_report(cluster_id: int | None = None):
    """
    GET /api/report
    Returns the full Replaceability Report.
    """
    report_path = (
        OUTPUT_DIR / f"replaceability_report_cluster_{cluster_id}.json"
        if cluster_id is not None else
        OUTPUT_DIR / "replaceability_report.json"
    )

    if not report_path.exists():
        if cluster_id is not None:
            raise HTTPException(status_code=404, detail=f"No targeted report found yet for cluster {cluster_id}.")
        return _heuristic_report_from_clusters(_load_cluster_info())

    with open(report_path) as f:
        report = json.load(f)

    return report


@app.get("/api/config")
async def get_config():
    cluster_info = _load_cluster_info()
    report_path = OUTPUT_DIR / "replaceability_report.json"
    model_catalog = load_model_catalog(OUTPUT_DIR)
    return {
        "db_path": str(DB_PATH),
        "output_dir": str(OUTPUT_DIR),
        "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        "target_agent_provider": os.getenv("TARGET_AGENT_PROVIDER", "openai"),
        "target_agent_ollama_model": os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b"),
        "target_agent_openai_model": os.getenv("TARGET_AGENT_OPENAI_MODEL", "gpt-4o-mini"),
        "quality_threshold": os.getenv("AGENTSHRINK_QUALITY_THRESHOLD", "0.85"),
        "confidence_threshold": os.getenv("AGENTSHRINK_CONFIDENCE_THRESHOLD", "0.75"),
        "eval_samples_per_cluster": str(get_eval_samples_per_cluster()),
        "remote_min_interval_s": str(get_remote_min_interval_s()),
        "judge_min_interval_s": str(get_judge_min_interval_s()),
        "cluster_count": cluster_info.get("n_clusters", 0) if cluster_info else 0,
        "model_count": len(model_catalog.get("models", [])),
        "report_exists": report_path.exists(),
        "analysis_exists": cluster_info is not None,
        "heuristic_report": not report_path.exists() and cluster_info is not None,
    }


@app.get("/api/analysis/logs")
async def get_analysis_logs():
    return {
        "running": analysis_running,
        "lines": list(analysis_log_buffer),
    }


@app.post("/api/apply-report")
async def apply_report():
    """Persist an explicit routing_config.json from the current report."""
    report_path = OUTPUT_DIR / "replaceability_report.json"
    cluster_info = _load_cluster_info()
    if not cluster_info:
        raise HTTPException(status_code=400, detail="No analysis output found yet.")

    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    else:
        report = _heuristic_report_from_clusters(cluster_info)

    catalog = load_model_catalog(OUTPUT_DIR)
    existing = _load_existing_routing_config()
    existing_routing = existing.get("routing", existing)
    routing = {}
    for cluster in report.get("clusters", []):
        rec = cluster.get("recommendation")
        cid = str(cluster["cluster_id"])
        existing_cfg = existing_routing.get(cid, {})

        # Preserve previously registered fine-tuned routes across report refreshes.
        if existing_cfg.get("source") == "fine_tuned" and existing_cfg.get("model"):
            routing[cid] = {
                "name": cluster["cluster_name"],
                "provider": existing_cfg.get("provider", "ollama"),
                "model": existing_cfg.get("model"),
                "display": existing_cfg.get("display") or existing_cfg.get("model"),
                "local": True,
                "source": "fine_tuned",
                "quality_score": existing_cfg.get("quality_score", cluster.get("best_score", 0.0)),
            }
            continue

        evaluated_candidates = cluster.get("evaluations", []) or []
        if rec in {"replace_now", "fine_tune"} and evaluated_candidates:
            top_candidate = next(
                (
                    ev for ev in evaluated_candidates
                    if ev.get("provider") == cluster.get("best_provider")
                    and ev.get("slm_name") == cluster.get("best_slm")
                ),
                None,
            )
            if top_candidate is None:
                top_candidate = sorted(
                    evaluated_candidates,
                    key=lambda ev: (
                        -float(ev.get("selection_score", 0.0)),
                        -float(ev.get("composite_score", 0.0)),
                        float(ev.get("cost_in_per_1k", 0.0)) + float(ev.get("cost_out_per_1k", 0.0)),
                    ),
                )[0]
            routing[cid] = {
                "name": cluster["cluster_name"],
                "provider": top_candidate.get("provider", cluster.get("best_provider", "ollama")),
                "model": top_candidate.get("slm_name") or cluster.get("best_slm") or "fallback",
                "display": top_candidate.get("slm_display") or cluster.get("best_slm_display") or "Fallback",
                "local": bool(top_candidate.get("local", False)),
                "source": "report",
                "quality_score": top_candidate.get("composite_score", cluster.get("best_score", 0.0)),
                "selection_score": top_candidate.get("selection_score", 0.0),
            }
            continue

        if rec == "replace_now":
            routing[cid] = {
                "name": cluster["cluster_name"],
                "provider": cluster.get("best_provider", "ollama"),
                "model": cluster.get("best_slm") or "fallback",
                "display": cluster.get("best_slm_display") or cluster.get("best_slm") or "Fallback",
                "local": cluster.get("best_provider") == "ollama",
                "source": "report",
                "quality_score": cluster.get("best_score", 0.0),
            }
        elif rec == "fine_tune":
            routing[cid] = {
                "name": cluster["cluster_name"],
                "provider": "ollama",
                "model": cluster.get("fine_tune_base_model") or os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b"),
                "display": f"{cluster.get('fine_tune_base_model') or os.getenv('TARGET_AGENT_OLLAMA_MODEL', 'llama3.2:3b')} (fine-tune candidate)",
                "local": False,
                "source": "fine_tune_pending",
                "quality_score": cluster.get("best_score", 0.0),
            }
        else:
            routing[cid] = {
                "name": cluster["cluster_name"],
                "provider": os.getenv("TARGET_AGENT_PROVIDER", "openai"),
                "model": "fallback",
                "display": "Fallback (kept on strong model)",
                "local": False,
                "source": "report",
                "quality_score": cluster.get("best_score", 0.0),
            }

    config_payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cluster_count": len(routing),
        "routing": routing,
        "manual_change_required": True,
        "manual_integration": {
            "replace_chat_model_with": "ShrinkLLM",
            "example_provider": "shrink",
            "demo_script": "venv\\Scripts\\python.exe target_agent\\run_shrink_demo.py",
        },
    }

    with open(OUTPUT_DIR / "routing_config.json", "w", encoding="utf-8") as f:
        json.dump(config_payload, f, indent=2)

    return {
        "status": "ok",
        "message": "Report applied. routing_config.json saved.",
        "cluster_count": len(routing),
        "manual_change_required": True,
    }


@app.get("/api/routing/stats")
async def get_routing_stats():
    """
    GET /api/routing/stats
    Returns live routing statistics from the centroid index.
    """
    routing_config_path = OUTPUT_DIR / "routing_config.json"

    if not (OUTPUT_DIR / "centroids.npy").exists():
        return {
            "configured": False,
            "message": "Run agentshrink analyse to configure routing"
        }

    # Load centroid index to get routing config
    try:
        from agentshrink.centroid_index import CentroidIndex
        index = CentroidIndex.from_output_dir(OUTPUT_DIR)
        stats = index.get_stats()
        return {"configured": True, **stats}
    except Exception as e:
        return {"configured": False, "error": str(e)}


class AnalyseRequest(BaseModel):
    min_cluster_size: int = 5
    skip_eval:        bool = False
    no_llm_labels:    bool = False
    cluster_ids:      list[int] = []


class ExportFineTuneRequest(BaseModel):
    cluster_id: int


class RegisterFineTuneRequest(BaseModel):
    cluster_id: int
    ollama_name: str
    display_name: str


class ModelConfigRequest(BaseModel):
    id: Optional[str] = None
    provider: str
    model_name: str
    display_name: str
    enabled: bool = True
    candidate_enabled: bool = True
    judge_eligible: bool = True
    local: bool = False
    supports: list[str] = ["general"]
    quality_tier: int = 3
    cost_in_per_1k: float = 0.0
    cost_out_per_1k: float = 0.0


class JudgeModelRequest(BaseModel):
    model_id: Optional[str] = None


class StartFineTuneRequest(BaseModel):
    cluster_id: int
    backend: str
    config: dict = {}
    hf_token: Optional[str] = None


def _ollama_model_names() -> list[str]:
    try:
        import ollama
        models = ollama.list()
        if isinstance(models, dict):
            items = models.get("models", [])
            return [m.get("name") or m.get("model") for m in items if (m.get("name") or m.get("model"))]
        items = getattr(models, "models", [])
        names = []
        for m in items:
            name = getattr(m, "model", None) or getattr(m, "name", None)
            if name:
                names.append(name)
        return names
    except Exception:
        return []


@app.get("/api/models")
async def get_models():
    catalog = load_model_catalog(OUTPUT_DIR)
    return {
        "models": catalog.get("models", []),
        "judge_model_id": get_judge_model_id(),
        "available_providers": ["ollama", "openai", "nvidia", "gemini", "anthropic"],
        "ollama_models": _ollama_model_names(),
    }


@app.post("/api/models")
async def save_model(req: ModelConfigRequest):
    catalog = upsert_model(OUTPUT_DIR, req.model_dump())
    return {"status": "ok", "models": catalog.get("models", [])}


@app.delete("/api/models/{model_id}")
async def remove_model(model_id: str):
    catalog = delete_model(OUTPUT_DIR, model_id)
    return {"status": "ok", "models": catalog.get("models", [])}


@app.post("/api/models/judge")
async def set_judge_model(req: JudgeModelRequest):
    model_id = req.model_id
    if model_id:
        catalog = load_model_catalog(OUTPUT_DIR)
        selected = next((model for model in catalog.get("models", []) if model.get("id") == model_id), None)
        if not selected:
            raise HTTPException(status_code=404, detail="Judge model not found in model catalog.")
        if not selected.get("judge_eligible", True):
            raise HTTPException(status_code=400, detail="Selected model is not marked as judge-eligible.")
    config = save_project_config({"judge_model_id": model_id})
    return {"status": "ok", "judge_model_id": config.get("judge_model_id")}


@app.post("/api/analyse")
async def trigger_analyse(req: AnalyseRequest, background_tasks: BackgroundTasks):
    """
    POST /api/analyse
    Triggers the full analysis pipeline in a background task.
    Progress is streamed via the /ws/routing-trace WebSocket.
    """
    use_saved_snapshot = bool(req.cluster_ids) and not req.skip_eval and (OUTPUT_DIR / "cluster_info.json").exists()

    async def run_analysis():
        global analysis_running
        analysis_running = True
        analysis_log_buffer.clear()

        try:
            if use_saved_snapshot:
                await routing_event_queue.put({
                    "type": "analysis_progress",
                    "step": 1, "total_steps": 2,
                    "message": "Loading saved clustering snapshot...",
                    "timestamp": time.time(),
                })
                await routing_event_queue.put(_record_analysis_log(
                    f"Using saved cluster snapshot from {OUTPUT_DIR}",
                    stream="meta",
                ))

                from agentshrink.evaluator import EvaluatorConfig, SLMEvaluator

                previous_output_dir = os.environ.get("AGENTSHRINK_OUTPUT_DIR")
                os.environ["AGENTSHRINK_OUTPUT_DIR"] = str(OUTPUT_DIR)
                try:
                    cluster_result = await asyncio.to_thread(_load_saved_cluster_snapshot)
                    evaluator = SLMEvaluator(
                        config=EvaluatorConfig(
                            n_samples_per_cluster=get_eval_samples_per_cluster(),
                            remote_min_interval_s=get_remote_min_interval_s(),
                            judge_min_interval_s=get_judge_min_interval_s(),
                            verbose=True,
                        )
                    )

                    await routing_event_queue.put({
                        "type": "analysis_progress",
                        "step": 2, "total_steps": 2,
                        "message": f"Evaluating saved cluster snapshot for cluster_id(s): {', '.join(str(cid) for cid in req.cluster_ids)}",
                        "timestamp": time.time(),
                    })
                    await routing_event_queue.put(_record_analysis_log(
                        f"Evaluating cluster_id(s) {', '.join(str(cid) for cid in req.cluster_ids)} from saved snapshot without reclustering",
                        stream="meta",
                    ))

                    reports = await asyncio.to_thread(
                        evaluator.evaluate_all_clusters,
                        cluster_result,
                        True,
                        list(req.cluster_ids),
                    )
                    report_path = await asyncio.to_thread(
                        evaluator.save_report,
                        reports,
                        OUTPUT_DIR,
                        _targeted_report_filename(list(req.cluster_ids)),
                    )
                    await asyncio.to_thread(evaluator.print_report, reports)
                finally:
                    if previous_output_dir is None:
                        os.environ.pop("AGENTSHRINK_OUTPUT_DIR", None)
                    else:
                        os.environ["AGENTSHRINK_OUTPUT_DIR"] = previous_output_dir

                await routing_event_queue.put(_record_analysis_log(
                    f"Saved targeted report to {report_path}",
                    stream="meta",
                ))
                await routing_event_queue.put({
                    "type": "analysis_complete",
                    "message": "Targeted evaluation complete from saved cluster snapshot!",
                    "timestamp": time.time(),
                })
                return

            await routing_event_queue.put({
                "type": "analysis_progress",
                "step": 1, "total_steps": 4,
                "message": "Curating captured logs...",
                "timestamp": time.time(),
            })

            cmd = [
                sys.executable, "-m", "agentshrink.cli", "analyse",
                f"--min-cluster-size={req.min_cluster_size}",
            ]
            if req.skip_eval:
                cmd.append("--skip-eval")
            if req.no_llm_labels:
                cmd.append("--no-llm-labels")
            for cluster_id in req.cluster_ids:
                cmd.append(f"--cluster-id={cluster_id}")

            await routing_event_queue.put(_record_analysis_log(
                f"$ {' '.join(cmd)}",
                stream="meta",
            ))

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(PROJECT_ROOT),
            )

            async def _pump_stream(stream, stream_name: str):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    await routing_event_queue.put(
                        _record_analysis_log(
                            line.decode("utf-8", errors="replace"),
                            stream=stream_name,
                        )
                    )

            await asyncio.gather(
                _pump_stream(process.stdout, "stdout"),
                _pump_stream(process.stderr, "stderr"),
            )
            return_code = await process.wait()

            if return_code == 0:
                await routing_event_queue.put({
                    "type": "analysis_complete",
                    "message": "Analysis complete!",
                    "timestamp": time.time(),
                })
            else:
                await routing_event_queue.put({
                    "type": "analysis_error",
                    "message": f"Analysis failed with exit code {return_code}",
                    "timestamp": time.time(),
                })
        except Exception as e:
            await routing_event_queue.put({
                "type": "analysis_error",
                "message": str(e),
                "timestamp": time.time(),
            })
        finally:
            analysis_running = False

    background_tasks.add_task(run_analysis)
    if use_saved_snapshot:
        return {
            "status": "started",
            "message": "Targeted evaluation started from the saved clustering snapshot",
        }
    return {"status": "started", "message": "Analysis running in background"}


@app.post("/api/routing/event")
async def receive_routing_event(event: dict):
    """
    POST /api/routing/event
    Called by ShrinkLLM to push live routing decisions to the dashboard.

    ShrinkLLM sends events here; WebSocket broadcasts them to the frontend.
    This is how the live routing feed works.
    """
    event["timestamp"] = event.get("timestamp", time.time())
    event["type"] = "routing_decision"

    try:
        routing_event_queue.put_nowait(event)
    except asyncio.QueueFull:
        pass  # Drop oldest events if queue is full

    return {"status": "ok"}


@app.get("/api/finetune/preview/{cluster_id}")
async def finetune_preview(cluster_id: int, limit: int = 5):
    df = _load_clustered_df()
    cluster_df = df[df["cluster_id"] == cluster_id].copy()
    if len(cluster_df) == 0:
        raise HTTPException(status_code=404, detail="Cluster not found in clustered dataframe.")

    records = []
    for _, row in cluster_df.head(limit).iterrows():
        records.append({
            "prompt": str(row.get("prompt", "")),
            "response": str(row.get("response", "")),
            "node_name": str(row.get("node_name", "")),
        })
    return {"cluster_id": cluster_id, "count": len(cluster_df), "examples": records}


@app.get("/api/finetune/backends")
async def finetune_backends():
    return {"backends": backend_statuses()}


@app.get("/api/finetune/jobs")
async def finetune_jobs():
    jobs = [_reconcile_finetune_job(job) for job in job_store.list_jobs()]
    return {"jobs": jobs}


@app.get("/api/finetune/jobs/{job_id}")
async def finetune_job(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Fine-tune job not found.")
    return _reconcile_finetune_job(job)


@app.post("/api/finetune/start")
async def finetune_start(req: StartFineTuneRequest):
    if req.backend not in {"modal", "huggingface"}:
        raise HTTPException(status_code=400, detail="Choose a supported backend before starting training.")

    prepared = _prepare_finetune_payload(req.cluster_id)
    cluster_name = prepared["cluster_meta"]["name"]
    default_model = choose_default_model(req.backend)
    config = {
        "cluster_id": req.cluster_id,
        "cluster_name": cluster_name,
        "base_model": req.config.get("base_model") or default_model["id"],
        "deploy_base_model": req.config.get("deploy_base_model") or default_model["deploy_base_model"],
        "epochs": int(req.config.get("epochs", 2)),
        "batch_size": int(req.config.get("batch_size", 2 if req.backend == "modal" else 1)),
        "learning_rate": float(req.config.get("learning_rate", 2e-4)),
        "lora_r": int(req.config.get("lora_r", 16)),
        "max_seq_length": int(req.config.get("max_seq_length", 512)),
    }

    job = job_store.create_job(
        cluster_id=req.cluster_id,
        cluster_name=cluster_name,
        backend=req.backend,
        config=config,
        dataset_path=prepared["dataset_path"],
        sample_count=len(prepared["training_rows"]),
        base_model=config["base_model"],
        deploy_base_model=config["deploy_base_model"],
    )
    job_store.append_log(job["job_id"], f"Queued {req.backend} training job for cluster '{cluster_name}'")

    stop_event = threading.Event()
    finetune_stop_events[job["job_id"]] = stop_event
    worker = threading.Thread(
        target=_run_finetune_job,
        args=(job["job_id"], req.backend, config, prepared["training_rows"], req.hf_token or os.getenv("HF_TOKEN")),
        daemon=True,
    )
    finetune_threads[job["job_id"]] = worker
    worker.start()
    return {"status": "started", "job": job_store.get_job(job["job_id"])}


@app.post("/api/finetune/jobs/{job_id}/stop")
async def finetune_stop(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Fine-tune job not found.")
    if job.get("status") not in {"queued", "running"}:
        return {"status": "ignored", "message": f"Job is already {job.get('status')}."}

    stop_event = finetune_stop_events.get(job_id)
    has_live_handle = any((
        stop_event is not None,
        job_id in finetune_processes,
        job_id in finetune_modal_calls,
        job_id in finetune_threads,
    ))
    if not has_live_handle:
        updated = job_store.update_job(
            job_id,
            status="stopped",
            phase="Stopped (stale job recovered)",
            stop_requested=True,
            error=None,
            ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        job_store.append_log(job_id, "No live backend worker was attached to this job. Marked as stopped immediately.")
        return {"status": "ok", "job": updated}

    if stop_event:
        stop_event.set()
    process = finetune_processes.get(job_id)
    if process is not None:
        try:
            process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
    modal_call = finetune_modal_calls.get(job_id)
    if modal_call is not None:
        try:
            modal_call.cancel(terminate_containers=True)
        except Exception:
            pass
    updated = job_store.update_job(job_id, stop_requested=True, phase="Stop requested")
    job_store.append_log(job_id, "Stop requested. AgentShrink is cancelling the remote training job.")
    return {"status": "ok", "job": updated}


@app.post("/api/finetune/jobs/{job_id}/deploy")
async def finetune_deploy(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Fine-tune job not found.")
    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Training must complete successfully before deployment.")
    if job_id in finetune_deploy_threads:
        return {"status": "started", "job": job}

    updated = job_store.update_job(job_id, status="deploying", phase="Preparing local deployment", progress=8, error=None)
    worker = threading.Thread(target=_run_deploy_job, args=(job_id,), daemon=True)
    finetune_deploy_threads[job_id] = worker
    worker.start()
    return {"status": "started", "job": updated}


@app.post("/api/finetune/export")
async def finetune_export(req: ExportFineTuneRequest):
    from agentshrink.finetuner import FineTuner

    df = _load_clustered_df()
    cluster_info = _load_cluster_info() or {}
    cluster_meta = (cluster_info.get("clusters") or {}).get(str(req.cluster_id))
    if not cluster_meta:
        raise HTTPException(status_code=404, detail="Cluster metadata not found.")

    cluster_df = df[df["cluster_id"] == req.cluster_id].copy()
    if len(cluster_df) == 0:
        raise HTTPException(status_code=404, detail="Cluster rows not found.")

    ft = FineTuner(output_dir=OUTPUT_DIR)
    dataset_path = ft.export_dataset(
        cluster_id=req.cluster_id,
        cluster_name=cluster_meta["name"],
        cluster_df=cluster_df,
        min_examples=10,
    )
    notebook_path = ft.generate_colab_notebook(
        cluster_id=req.cluster_id,
        cluster_name=cluster_meta["name"],
        dataset_path=dataset_path,
    )
    return {
        "status": "ok",
        "cluster_id": req.cluster_id,
        "cluster_name": cluster_meta["name"],
        "dataset_path": str(dataset_path),
        "notebook_path": str(notebook_path),
        "example_count": int(len(cluster_df)),
    }


@app.post("/api/finetune/register")
async def finetune_register(req: RegisterFineTuneRequest):
    from agentshrink.finetuner import FineTuner

    available = _ollama_model_names()
    if req.ollama_name not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{req.ollama_name}' was not found in Ollama. Available models: {', '.join(available) if available else 'none'}"
        )

    ft = FineTuner(output_dir=OUTPUT_DIR)
    ok = ft.register_fine_tuned_model(
        cluster_id=req.cluster_id,
        ollama_name=req.ollama_name,
        display_name=req.display_name,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to register fine-tuned model.")
    return {
        "status": "ok",
        "message": "Fine-tuned model registered for routing.",
        "cluster_id": req.cluster_id,
        "ollama_name": req.ollama_name,
    }


@app.get("/api/ollama/models")
async def ollama_models():
    return {
        "models": _ollama_model_names(),
        "models_dir": str(pathlib.Path.home() / ".ollama" / "models"),
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "db_exists": DB_PATH.exists(),
        "output_exists": OUTPUT_DIR.exists(),
    }


# ─────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# Live routing feed — frontend connects here
# ─────────────────────────────────────────────

@app.websocket("/ws/routing-trace")
async def websocket_routing_trace(ws: WebSocket):
    """
    WebSocket /ws/routing-trace
    Streams live routing decisions to the dashboard.

    The frontend connects here and receives:
    - routing_decision: a ShrinkLLM routing event
    - analysis_progress: pipeline step updates
    - analysis_complete: analysis finished
    - heartbeat: sent every 5s to keep connection alive
    """
    await manager.connect(ws)
    try:
        # Send initial state
        await ws.send_json({"type": "connected", "message": "Live routing feed connected"})

        while True:
            await asyncio.sleep(5.0)
            await ws.send_json({"type": "heartbeat", "timestamp": time.time()})

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except asyncio.CancelledError:
        manager.disconnect(ws)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(ws)


async def broadcast_routing_events():
    """Background task: read from queue and broadcast to all WebSocket clients."""
    while True:
        try:
            event = await asyncio.wait_for(routing_event_queue.get(), timeout=5.0)
            await manager.broadcast(event)
        except asyncio.CancelledError:
            break
        except asyncio.TimeoutError:
            # Send heartbeat to all clients
            if manager.active:
                await manager.broadcast({"type": "heartbeat", "timestamp": time.time()})
        except Exception as e:
            logger.debug(f"Broadcast error: {e}")
            await asyncio.sleep(0.1)
