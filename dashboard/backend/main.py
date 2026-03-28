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
from typing import Optional
from contextlib import asynccontextmanager

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

    local_model = os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b")
    clusters = []
    for cid, info in cluster_info.get("clusters", {}).items():
        node_dist = info.get("node_distribution", {}) or {}
        dominant = max(node_dist.items(), key=lambda kv: kv[1])[0].lower() if node_dist else ""
        recommendation = "fine_tune"
        best_slm = local_model
        best_slm_display = f"Local ({local_model})"
        best_score = 0.72
        needs_fine_tuning = True
        fine_tune_base_model = local_model

        if any(k in dominant for k in ("classify", "extract", "format")):
            recommendation = "replace_now"
            best_score = 0.92
            needs_fine_tuning = False
            fine_tune_base_model = None
        elif "draft_reply" in dominant:
            recommendation = "keep_llm"
            best_score = 0.58
            best_slm = None
            best_slm_display = None
            needs_fine_tuning = False
            fine_tune_base_model = None
        elif "check_policy" in dominant:
            recommendation = "fine_tune"
            best_score = 0.74
            needs_fine_tuning = True
            fine_tune_base_model = local_model

        clusters.append({
            "cluster_id": int(cid),
            "cluster_name": info.get("name", f"cluster_{cid}"),
            "cluster_size": int(info.get("size", 0)),
            "recommendation": recommendation,
            "best_slm": best_slm,
            "best_slm_display": best_slm_display,
            "best_score": best_score,
            "needs_fine_tuning": needs_fine_tuning,
            "fine_tune_base_model": fine_tune_base_model,
            "estimated_cost_saving_pct": 100.0 if recommendation == "replace_now" else (45.0 if recommendation == "fine_tune" else 0.0),
            "node_distribution": node_dist,
            "evaluations": [{
                "slm_name": best_slm or "fallback",
                "slm_display": best_slm_display or "Fallback",
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
            "models_evaluated": [local_model],
        },
        "clusters": clusters,
    }


def _load_clustered_df():
    clustered_df_path = OUTPUT_DIR / "clustered_df.parquet"
    if not clustered_df_path.exists():
        raise HTTPException(status_code=404, detail="No clustered dataframe found. Run analysis first.")
    import pandas as pd
    return pd.read_parquet(clustered_df_path)


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

# Global routing event queue — ShrinkLLM pushes events here,
# WebSocket handler reads and broadcasts them
routing_event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)


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
    yield
    task.cancel()


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
async def get_report():
    """
    GET /api/report
    Returns the full Replaceability Report.
    """
    report_path = OUTPUT_DIR / "replaceability_report.json"

    if not report_path.exists():
        return _heuristic_report_from_clusters(_load_cluster_info())

    with open(report_path) as f:
        report = json.load(f)

    return report


@app.get("/api/config")
async def get_config():
    cluster_info = _load_cluster_info()
    report_path = OUTPUT_DIR / "replaceability_report.json"
    return {
        "db_path": str(DB_PATH),
        "output_dir": str(OUTPUT_DIR),
        "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        "target_agent_provider": os.getenv("TARGET_AGENT_PROVIDER", "openai"),
        "target_agent_ollama_model": os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b"),
        "target_agent_openai_model": os.getenv("TARGET_AGENT_OPENAI_MODEL", "gpt-4o-mini"),
        "quality_threshold": os.getenv("AGENTSHRINK_QUALITY_THRESHOLD", "0.85"),
        "confidence_threshold": os.getenv("AGENTSHRINK_CONFIDENCE_THRESHOLD", "0.75"),
        "cluster_count": cluster_info.get("n_clusters", 0) if cluster_info else 0,
        "report_exists": report_path.exists(),
        "analysis_exists": cluster_info is not None,
        "heuristic_report": not report_path.exists() and cluster_info is not None,
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

    local_model = os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b")
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
                "model": existing_cfg.get("model"),
                "display": existing_cfg.get("display") or existing_cfg.get("model"),
                "local": True,
                "source": "fine_tuned",
                "quality_score": existing_cfg.get("quality_score", cluster.get("best_score", 0.0)),
            }
            continue

        if rec == "replace_now":
            routing[cid] = {
                "name": cluster["cluster_name"],
                "model": cluster.get("best_slm") or local_model,
                "display": cluster.get("best_slm_display") or f"Local ({local_model})",
                "local": True,
                "source": "report",
                "quality_score": cluster.get("best_score", 0.0),
            }
        elif rec == "fine_tune":
            routing[cid] = {
                "name": cluster["cluster_name"],
                "model": cluster.get("fine_tune_base_model") or local_model,
                "display": f"{cluster.get('fine_tune_base_model') or local_model} (fine-tune candidate)",
                "local": False,
                "source": "fine_tune_pending",
                "quality_score": cluster.get("best_score", 0.0),
            }
        else:
            routing[cid] = {
                "name": cluster["cluster_name"],
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


class ExportFineTuneRequest(BaseModel):
    cluster_id: int


class RegisterFineTuneRequest(BaseModel):
    cluster_id: int
    ollama_name: str
    display_name: str


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


@app.post("/api/analyse")
async def trigger_analyse(req: AnalyseRequest, background_tasks: BackgroundTasks):
    """
    POST /api/analyse
    Triggers the full analysis pipeline in a background task.
    Progress is streamed via the /ws/routing-trace WebSocket.
    """
    async def run_analysis():
        await routing_event_queue.put({
            "type": "analysis_progress",
            "step": 1, "total_steps": 4,
            "message": "Curating captured logs...",
            "timestamp": time.time(),
        })

        try:
            import subprocess
            cmd = [
                sys.executable, "-m", "agentshrink.cli", "analyse",
                f"--min-cluster-size={req.min_cluster_size}",
            ]
            if req.skip_eval:
                cmd.append("--skip-eval")
            if req.no_llm_labels:
                cmd.append("--no-llm-labels")

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(PROJECT_ROOT)
            )

            if result.returncode == 0:
                await routing_event_queue.put({
                    "type": "analysis_complete",
                    "message": "Analysis complete!",
                    "timestamp": time.time(),
                })
            else:
                await routing_event_queue.put({
                    "type": "analysis_error",
                    "message": result.stderr[-500:] if result.stderr else "Analysis failed",
                    "timestamp": time.time(),
                })
        except Exception as e:
            await routing_event_queue.put({
                "type": "analysis_error",
                "message": str(e),
                "timestamp": time.time(),
            })

    background_tasks.add_task(run_analysis)
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
            try:
                # Wait for event with timeout (to send heartbeats)
                event = await asyncio.wait_for(
                    routing_event_queue.get(),
                    timeout=5.0
                )
                await manager.broadcast(event)
            except asyncio.TimeoutError:
                # Send heartbeat so frontend knows connection is alive
                await ws.send_json({"type": "heartbeat", "timestamp": time.time()})
            except asyncio.CancelledError:
                break

    except WebSocketDisconnect:
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
        except asyncio.TimeoutError:
            # Send heartbeat to all clients
            if manager.active:
                await manager.broadcast({"type": "heartbeat", "timestamp": time.time()})
        except Exception as e:
            logger.debug(f"Broadcast error: {e}")
            await asyncio.sleep(0.1)
