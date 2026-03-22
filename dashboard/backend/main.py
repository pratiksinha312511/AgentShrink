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

        # Clustering readiness
        analysis_done = (OUTPUT_DIR / "cluster_info.json").exists()
        report_done   = (OUTPUT_DIR / "replaceability_report.json").exists()

    return {
        "total_calls":   total_calls,
        "total_runs":    total_runs,
        "total_tokens":  total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "nodes":         nodes,
        "daily_counts":  daily_counts,
        "db_path":       str(DB_PATH),
        "has_data":      total_calls > 0,
        "analysis_done": analysis_done,
        "report_done":   report_done,
        "ready_for_analysis": total_calls >= 50,
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
        raise HTTPException(
            status_code=404,
            detail="No report found. Run: agentshrink analyse"
        )

    with open(report_path) as f:
        report = json.load(f)

    return report


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
