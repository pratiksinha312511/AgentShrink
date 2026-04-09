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
import urllib.request
import urllib.error
import urllib.parse
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
DB_PATH       = pathlib.Path(os.getenv("AGENTSHRINK_DB_PATH", "~/.agentshrink/logs.db")).expanduser()
OUTPUT_DIR    = PROJECT_ROOT / ".agentshrink_output"
SYS_PATH_ROOT = str(PROJECT_ROOT)
ROUTING_CONFIG_PATH = OUTPUT_DIR / "routing_config.json"
ROUTING_HISTORY_DIR = OUTPUT_DIR / "routing_history"
ANALYSIS_READY_CALL_THRESHOLD = 25

import sys
sys.path.insert(0, SYS_PATH_ROOT)

from agentshrink.logger import _estimate_cost
from agentshrink.app_setup import (
    accept_team_invite,
    activate_product_project,
    clear_session,
    consume_magic_link,
    create_product_project,
    create_session,
    create_team,
    generate_project_token,
    get_team_membership,
    invite_team_member,
    list_pending_invites,
    load_hosted_config,
    load_product_config,
    load_project_registry,
    load_runtime_state,
    load_session,
    record_tenant_billing_snapshot,
    request_magic_link,
    role_meets_minimum,
    run_doctor_checks,
    save_product_config,
    save_session,
    save_hosted_config,
    sync_active_project_to_registry,
    update_team_member_role,
    user_team_memberships,
)
from agentshrink.model_catalog import (
    active_gateway_defaults,
    choose_best_model,
    choose_fine_tune_base_model,
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
    lookup_backend_model,
    write_training_artifacts,
)
from agentshrink.hosted_providers import AuthProviderError, get_auth_provider, get_billing_provider
from agentshrink.provider_registry import (
    delete_provider_config,
    get_provider_config,
    list_provider_configs,
    upsert_provider_config,
)
from agentshrink.provider_runtime import (
    ALLOWED_PROVIDER_ADAPTERS,
    PROVIDER_PRESETS,
    discover_provider_models,
    test_provider_connection,
)

OUTPUT_DIR = pathlib.Path((load_product_config().get("output_dir") or str(OUTPUT_DIR))).expanduser()
ROUTING_CONFIG_PATH = OUTPUT_DIR / "routing_config.json"
ROUTING_HISTORY_DIR = OUTPUT_DIR / "routing_history"

product_config = load_product_config()
frontend_port = int((product_config.get("dashboard_frontend") or {}).get("port", 3000))
allowed_origins = [
    f"http://localhost:{frontend_port}",
    f"http://127.0.0.1:{frontend_port}",
]


def _load_cluster_info() -> dict | None:
    cluster_info_path = OUTPUT_DIR / "cluster_info.json"
    if not cluster_info_path.exists():
        return None
    with open(cluster_info_path, encoding="utf-8") as f:
        return json.load(f)


def _load_existing_routing_config() -> dict:
    if not ROUTING_CONFIG_PATH.exists():
        return {}
    with open(ROUTING_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _active_provider_context() -> dict:
    defaults = active_gateway_defaults()
    provider_config = get_provider_config(defaults["provider_id"]) or {}
    return {
        "provider_id": defaults["provider_id"],
        "provider_name": defaults["provider_name"],
        "gateway_model": defaults["gateway_model"],
        "local_model": defaults["local_model"],
        "provider_config": provider_config,
    }


def _score_pct(value: float | int | None) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{round(numeric * 100)}%"


def _route_label(route: dict | None) -> str:
    if not route:
        return "none"
    provider = route.get("provider") or "unknown"
    display = route.get("display") or route.get("model") or "unknown"
    source = route.get("source")
    if source == "fine_tuned":
        return f"{display} on {provider} (fine-tuned)"
    if source == "fine_tune_pending":
        return f"{display} on {provider} (fine-tune pending)"
    if route.get("local"):
        return f"{display} on {provider} (local)"
    return f"{display} on {provider}"


def _cluster_recommendation_explanation(cluster: dict, route: dict | None = None) -> str:
    recommendation = str(cluster.get("recommendation") or "keep_llm")
    best_score = cluster.get("best_score")
    incumbent_score = cluster.get("incumbent_score")
    best_model = cluster.get("best_slm_display") or cluster.get("best_slm") or "the proposed model"
    best_provider = cluster.get("best_provider") or route.get("provider") if route else cluster.get("best_provider")
    best_provider = best_provider or "the selected provider"
    cluster_size = int(cluster.get("cluster_size") or 0)
    size_text = f" across {cluster_size} logged calls" if cluster_size else ""

    if recommendation == "replace_now":
        if incumbent_score is not None:
            return (
                f"Replace now because {best_model} on {best_provider} scored {_score_pct(best_score)}"
                f" versus the incumbent at {_score_pct(incumbent_score)}{size_text}."
            )
        return (
            f"Replace now because {best_model} on {best_provider} was the strongest safe local option"
            f"{size_text}."
        )

    if recommendation == "fine_tune":
        base_model = cluster.get("fine_tune_base_model") or cluster.get("best_slm_display") or cluster.get("best_slm") or "the selected base model"
        if incumbent_score is not None:
            return (
                f"Fine-tune instead of replacing immediately because {base_model} is promising at {_score_pct(best_score)},"
                f" but the incumbent is still at {_score_pct(incumbent_score)}{size_text}."
            )
        return (
            f"Fine-tune because the current best local base, {base_model}, looks close but not safe enough"
            f" to replace production traffic yet{size_text}."
        )

    if cluster.get("best_slm_display") and cluster.get("best_provider") not in {None, "", "ollama"}:
        return (
            f"Keep on API because the best-scoring candidate is still remote ({cluster.get('best_slm_display')} on"
            f" {cluster.get('best_provider')}), so AgentShrink avoids calling this a local replacement."
        )

    if incumbent_score is not None and best_score is not None:
        return (
            f"Keep on API because the current route still looks safer: incumbent {_score_pct(incumbent_score)}"
            f" versus proposed {_score_pct(best_score)}{size_text}."
        )

    return "Keep on API because no local candidate has cleared the confidence bar strongly enough yet."


def _routing_change_explanation(*, change_type: str, cluster: dict | None, before: dict | None, after: dict | None) -> str:
    cluster = cluster or {}
    recommendation = str(cluster.get("recommendation") or "")
    cluster_reason = _cluster_recommendation_explanation(cluster, after or before)

    if after and after.get("source") == "fine_tuned":
        if change_type == "unchanged":
            return f"Keeping the existing fine-tuned route: {_route_label(after)} remains assigned to this cluster."
        return f"Preserving the fine-tuned route {_route_label(after)} instead of replacing it with a generic report route."

    if after and after.get("source") == "fine_tune_pending":
        return (
            f"Pointing this cluster at {_route_label(after)} as a temporary fine-tune candidate."
            f" {cluster_reason}"
        )

    if change_type == "added":
        return f"Adding a new route to {_route_label(after)}. {cluster_reason}"

    if change_type == "removed":
        return f"Removing the existing route {_route_label(before)} because the current report no longer proposes it."

    if change_type == "changed":
        return (
            f"Changing the route from {_route_label(before)} to {_route_label(after)}."
            f" {cluster_reason}"
        )

    if recommendation:
        return f"No change needed. {cluster_reason}"

    return "No change needed because the current routing config already matches the proposed report."


def _enrich_report_payload(report: dict) -> dict:
    clusters = report.get("clusters") or []
    enriched_clusters = []
    for cluster in clusters:
        cluster_copy = dict(cluster)
        preview_route = None
        if cluster_copy.get("recommendation") in {"replace_now", "fine_tune"}:
            preview_route = {
                "provider": cluster_copy.get("best_provider"),
                "model": cluster_copy.get("best_slm"),
                "display": cluster_copy.get("best_slm_display"),
                "local": cluster_copy.get("best_provider") == "ollama",
            }
        cluster_copy["recommendation_explanation"] = _cluster_recommendation_explanation(cluster_copy, preview_route)
        enriched_clusters.append(cluster_copy)

    report_copy = dict(report)
    report_copy["clusters"] = enriched_clusters
    return report_copy


def _save_routing_backup(payload: dict, *, reason: str) -> pathlib.Path:
    ROUTING_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = ROUTING_HISTORY_DIR / f"routing_config_{stamp}_{reason}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def _latest_routing_backup() -> pathlib.Path | None:
    if not ROUTING_HISTORY_DIR.exists():
        return None
    backups = sorted(ROUTING_HISTORY_DIR.glob("routing_config_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


def _load_report_for_apply() -> tuple[dict, dict]:
    report_path = OUTPUT_DIR / "replaceability_report.json"
    cluster_info = _load_cluster_info()
    if not cluster_info:
        raise HTTPException(status_code=400, detail="No analysis output found yet.")

    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    else:
        report = _heuristic_report_from_clusters(cluster_info)
    return report, cluster_info


def _build_routing_payload(report: dict) -> dict:
    catalog = load_model_catalog(OUTPUT_DIR)
    active_provider = _active_provider_context()
    existing = _load_existing_routing_config()
    existing_routing = existing.get("routing", existing)
    routing = {}
    for cluster in report.get("clusters", []):
        rec = cluster.get("recommendation")
        cid = str(cluster["cluster_id"])
        existing_cfg = existing_routing.get(cid, {})

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
                "provider": cluster.get("best_provider", "ollama"),
                "model": cluster.get("fine_tune_base_model") or cluster.get("best_slm") or active_provider["local_model"],
                "display": f"{cluster.get('best_slm_display') or cluster.get('fine_tune_base_model') or active_provider['local_model']} (fine-tune candidate)",
                "local": True,
                "source": "fine_tune_pending",
                "quality_score": cluster.get("best_score", 0.0),
            }
        else:
            routing[cid] = {
                "name": cluster["cluster_name"],
                "provider": active_provider["provider_id"],
                "model": "fallback",
                "display": "Fallback (kept on strong model)",
                "local": False,
                "source": "report",
                "quality_score": cluster.get("best_score", 0.0),
            }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cluster_count": len(routing),
        "routing": routing,
        "manual_change_required": True,
        "manual_integration": {
            "replace_chat_model_with": "ShrinkLLM",
            "example_provider": "shrink",
            "demo_script": "venv\\Scripts\\python.exe target_agent\\run_shrink_demo.py",
        },
        "models_evaluated": [model["model_name"] for model in catalog.get("models", []) if model.get("enabled")],
    }


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
    active_provider = _active_provider_context()
    fallback_provider = active_provider["provider_id"]
    clusters = []
    for cid, info in cluster_info.get("clusters", {}).items():
        node_dist = info.get("node_distribution", {}) or {}
        task_kind = cluster_task_kind(info)
        chosen_model = choose_best_model(info, catalog)
        fine_tune_candidate = choose_fine_tune_base_model(info, catalog)
        best_score = 0.92 if task_kind == "simple" else (0.82 if task_kind == "general" else 0.72)
        recommendation = "keep_llm"
        best_slm = None
        best_slm_display = None
        best_provider = fallback_provider
        needs_fine_tuning = False
        fine_tune_base_model = None

        if chosen_model:
            chosen_is_local = bool(chosen_model.get("local"))

            # Only local candidates should appear as replace/fine-tune targets.
            # If the best available candidate is still a remote/cloud model
            # (for example NVIDIA), the cluster should stay on the incumbent LLM.
            if chosen_is_local:
                best_slm = chosen_model["model_name"]
                best_slm_display = chosen_model["display_name"]
                best_provider = chosen_model["provider"]
                if task_kind == "simple":
                    recommendation = "replace_now"
                    needs_fine_tuning = False
                else:
                    recommendation = "fine_tune"
                    needs_fine_tuning = True
                    fine_tune_base_model = chosen_model["model_name"]
            else:
                recommendation = "keep_llm"
                best_slm = None
                best_slm_display = None
                best_provider = fallback_provider

        if recommendation == "keep_llm" and fine_tune_candidate and task_kind in {"general", "writing", "reasoning"}:
            recommendation = "fine_tune"
            best_slm = fine_tune_candidate["model_name"]
            best_slm_display = fine_tune_candidate["display_name"]
            best_provider = fine_tune_candidate["provider"]
            needs_fine_tuning = True
            fine_tune_base_model = fine_tune_candidate["model_name"]

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


def _load_saved_cluster_snapshot_from(output_dir: pathlib.Path) -> dict:
    cluster_info_payload = _load_cluster_info_from(output_dir)
    if not cluster_info_payload:
        raise HTTPException(status_code=404, detail="No saved cluster snapshot found. Run analysis first.")

    clustered_df_path = output_dir / "clustered_df.parquet"
    if not clustered_df_path.exists():
        raise HTTPException(status_code=404, detail="No clustered dataframe found. Run analysis first.")

    import pandas as pd

    clustered_df = pd.read_parquet(clustered_df_path)
    cluster_info = {
        int(cid): info
        for cid, info in (cluster_info_payload.get("clusters") or {}).items()
    }

    centroids = {}
    centroids_path = output_dir / "centroids.npy"
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


def _validate_model_access(*, backend: str, model_id: str, hf_token: str | None) -> None:
    model_info = lookup_backend_model(backend, model_id)
    if not model_info:
        raise HTTPException(status_code=400, detail=f"Model '{model_id}' is not available for backend '{backend}'.")

    needs_hf = bool(model_info.get("requires_hf_token"))
    token = (hf_token or os.getenv("HF_TOKEN", "")).strip()
    if needs_hf and not token:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Model '{model_id}' requires Hugging Face gated access. "
                "Add HF_TOKEN in Settings/.env and make sure that account has accepted the model license. "
                "A local Ollama install alone is not enough to train this Llama family model, because the training backends need the original base weights."
            ),
        )

    if needs_hf:
        try:
            from huggingface_hub import HfApi

            HfApi().model_info(model_id, token=token)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Could not validate Hugging Face access for '{model_id}'. "
                    "Make sure your HF token is valid and that the account has access to the gated repo. "
                    f"Details: {exc}"
                ),
            ) from exc


def _run_finetune_job(job_id: str, backend: str, config: dict, training_rows: list[dict], hf_token: str | None = None):
    from agentshrink.finetuner import FineTuner
    from agentshrink.finetune.hf_trainer import run_hf_training
    from agentshrink.finetune.local_trainer import run_local_training
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

        if backend == "local":
            result = run_local_training(
                run_config,
                training_rows,
                hf_token=hf_token,
                on_status=on_status,
                on_log=on_log,
                on_metric=on_metric,
                should_stop=stop_event.is_set,
            )
        elif backend == "modal":
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
    allow_origins=allowed_origins,
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
            "successful_call_count": 0,
            "gateway_event_count": 0,
            "latest_timestamp": None,
            "source_of_truth": "sqlite:llm_calls",
        }

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Summary stats
        c.execute("SELECT COUNT(*) as n FROM llm_calls")
        total_calls = c.fetchone()["n"]

        c.execute("SELECT COUNT(*) as n FROM llm_calls WHERE workflow_success=1")
        successful_calls = c.fetchone()["n"]

        c.execute("SELECT COUNT(DISTINCT run_id) as n FROM llm_calls")
        total_runs = c.fetchone()["n"]

        c.execute("SELECT COALESCE(SUM(tokens_in+tokens_out),0) as n FROM llm_calls")
        total_tokens = c.fetchone()["n"]

        c.execute("SELECT COALESCE(SUM(cost_usd),0) as n FROM llm_calls")
        total_cost = c.fetchone()["n"]

        c.execute("""
            SELECT prompt, response, tokens_in, tokens_out, model_name
            FROM llm_calls
        """)
        rows = c.fetchall()

        active_provider = _active_provider_context()
        baseline_model = os.getenv("AGENTSHRINK_ESTIMATE_MODEL") or active_provider["gateway_model"] or "gpt-4o-mini"
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
            FROM llm_calls
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

        c.execute("""
            SELECT COUNT(*) as n
            FROM llm_calls
            WHERE extra_metadata LIKE '%"gateway_mode"%'
        """)
        gateway_event_count = c.fetchone()["n"]

        c.execute("SELECT MAX(timestamp) as latest_timestamp FROM llm_calls")
        latest_timestamp = c.fetchone()["latest_timestamp"]

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
        "successful_call_count": successful_calls,
        "gateway_event_count": gateway_event_count,
        "latest_timestamp": latest_timestamp,
        "source_of_truth": "sqlite:llm_calls",
        "nodes":         nodes,
        "daily_counts":  daily_counts,
        "db_path":       str(DB_PATH),
        "has_data":      total_calls > 0,
        "analysis_done": analysis_done,
        "report_done":   report_done,
        "ready_for_analysis": total_calls >= ANALYSIS_READY_CALL_THRESHOLD,
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
        return _enrich_report_payload(_heuristic_report_from_clusters(_load_cluster_info()))

    with open(report_path) as f:
        report = json.load(f)

    return _enrich_report_payload(report)


@app.get("/api/config")
async def get_config():
    cluster_info = _load_cluster_info()
    report_path = OUTPUT_DIR / "replaceability_report.json"
    model_catalog = load_model_catalog(OUTPUT_DIR)
    active_provider = _active_provider_context()
    return {
        "db_path": str(DB_PATH),
        "output_dir": str(OUTPUT_DIR),
        "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        "target_agent_provider": active_provider["provider_id"],
        "target_agent_provider_name": active_provider["provider_name"],
        "target_agent_ollama_model": active_provider["local_model"],
        "target_agent_openai_model": active_provider["gateway_model"],
        "active_gateway_model": active_provider["gateway_model"],
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
    _require_active_project_role("member")
    report, _cluster_info = _load_report_for_apply()
    config_payload = _build_routing_payload(report)
    existing = _load_existing_routing_config()
    if existing:
        _save_routing_backup(existing, reason="preapply")

    with open(ROUTING_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_payload, f, indent=2)

    return {
        "status": "ok",
        "message": "Report applied. routing_config.json saved.",
        "cluster_count": len(config_payload.get("routing", {})),
        "manual_change_required": True,
    }


@app.get("/api/routing/simulate")
async def simulate_routing_apply():
    report, _cluster_info = _load_report_for_apply()
    report = _enrich_report_payload(report)
    proposed = _build_routing_payload(report)
    current = _load_existing_routing_config()
    current_routing = current.get("routing", current) if isinstance(current, dict) else {}
    proposed_routing = proposed.get("routing", {})
    report_clusters = {
        str(cluster.get("cluster_id")): cluster
        for cluster in (report.get("clusters") or [])
    }

    all_ids = sorted(set(current_routing.keys()) | set(proposed_routing.keys()), key=lambda cid: int(cid))
    changes = []
    added = removed = changed = unchanged = 0
    for cid in all_ids:
        before = current_routing.get(cid)
        after = proposed_routing.get(cid)
        cluster = report_clusters.get(str(cid))
        if before is None and after is not None:
            change_type = "added"
            added += 1
        elif before is not None and after is None:
            change_type = "removed"
            removed += 1
        elif before == after:
            change_type = "unchanged"
            unchanged += 1
        else:
            change_type = "changed"
            changed += 1
        changes.append({
            "cluster_id": cid,
            "cluster_name": (after or before or cluster or {}).get("name") or (cluster or {}).get("cluster_name") or f"cluster_{cid}",
            "change_type": change_type,
            "before": before,
            "after": after,
            "recommendation": (cluster or {}).get("recommendation"),
            "recommendation_explanation": (cluster or {}).get("recommendation_explanation"),
            "explanation": _routing_change_explanation(
                change_type=change_type,
                cluster=cluster,
                before=before,
                after=after,
            ),
        })

    return {
        "status": "ok",
        "summary": {
            "current_cluster_count": len(current_routing),
            "proposed_cluster_count": len(proposed_routing),
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
        },
        "changes": changes,
        "has_backup": _latest_routing_backup() is not None,
    }


@app.post("/api/routing/rollback")
async def rollback_routing_config():
    _require_active_project_role("member")
    backup = _latest_routing_backup()
    if backup is None:
        raise HTTPException(status_code=404, detail="No routing backup found yet.")

    current = _load_existing_routing_config()
    if current:
        _save_routing_backup(current, reason="prerollback")

    with open(backup, encoding="utf-8") as f:
        payload = json.load(f)
    with open(ROUTING_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return {
        "status": "ok",
        "message": f"Rolled back routing config using {backup.name}.",
        "backup_path": str(backup),
        "cluster_count": len((payload.get('routing') or {})),
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


class ProductGatewayConfigRequest(BaseModel):
    host: str
    port: int
    upstream_provider: str


class ProductAccountConfigRequest(BaseModel):
    id: Optional[str] = None
    name: str
    slug: str


class ProductProjectMetaConfigRequest(BaseModel):
    id: Optional[str] = None
    name: str
    slug: str
    environment: str = "local"


class ProductBackendConfigRequest(BaseModel):
    host: str
    port: int


class ProductFrontendConfigRequest(BaseModel):
    port: int


class ProductDefaultsConfigRequest(BaseModel):
    gateway_model: str
    gateway_api_key: str
    confidence_threshold: float


class ProductConfigRequest(BaseModel):
    account: Optional[ProductAccountConfigRequest] = None
    project: Optional[ProductProjectMetaConfigRequest] = None
    project_name: str
    db_path: str
    output_dir: str
    gateway: ProductGatewayConfigRequest
    dashboard_backend: ProductBackendConfigRequest
    dashboard_frontend: ProductFrontendConfigRequest
    defaults: ProductDefaultsConfigRequest


class CreateHostedProjectRequest(BaseModel):
    name: str
    environment: str = "local"
    upstream_provider: str = "mock"


class CreateTeamRequest(BaseModel):
    name: str
    slug: Optional[str] = None


class InviteTeamMemberRequest(BaseModel):
    user_name: str
    user_email: str
    role: str = "member"


class UpdateTeamMemberRoleRequest(BaseModel):
    role: str


class SessionLoginRequest(BaseModel):
    user_name: str
    user_email: str


class MagicLinkRequest(BaseModel):
    user_email: str
    user_name: Optional[str] = None


class MagicLinkConsumeRequest(BaseModel):
    token: str


class AcceptInviteRequest(BaseModel):
    user_name: Optional[str] = None
    user_email: Optional[str] = None


class HostedConfigRequest(BaseModel):
    config: dict


class ProviderConfigRequest(BaseModel):
    id: str
    name: str
    adapter: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    api_key_env: str = ""
    base_url_env: str = ""
    default_model: str = ""
    description: str = ""
    enabled: bool = True
    extra_headers: dict = {}


class ExternalAuthStartRequest(BaseModel):
    redirect_uri: Optional[str] = None


class ExternalAuthCallbackRequest(BaseModel):
    code: str
    redirect_uri: Optional[str] = None


class BillingCheckoutRequest(BaseModel):
    return_url: Optional[str] = None


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


@app.get("/api/gateway/activity")
async def get_gateway_activity(limit: int = 50):
    if not DB_PATH.exists():
        return {"events": []}

    limit = max(1, min(limit, 200))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT timestamp, node_name, model_name, prompt, response, latency_ms, extra_metadata
            FROM llm_calls
            WHERE extra_metadata LIKE '%"gateway_mode"%'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    events = []
    for row in rows:
        try:
            metadata = json.loads(row["extra_metadata"] or "{}")
        except Exception:
            metadata = {}
        events.append({
            "timestamp": row["timestamp"],
            "node_name": row["node_name"],
            "model_name": row["model_name"],
            "model_display": metadata.get("route_model_display") or row["model_name"],
            "cluster_name": metadata.get("route_cluster_name") or "unknown",
            "confidence": float(metadata.get("route_confidence") or 0.0),
            "is_local": bool(metadata.get("route_is_local")),
            "nearest_cluster_name": metadata.get("nearest_cluster_name"),
            "nearest_similarity": float(metadata.get("nearest_similarity") or 0.0),
            "threshold": float(metadata.get("threshold") or 0.0),
            "reason": metadata.get("route_reason") or "",
            "gateway_mode": metadata.get("gateway_mode") or "upstream",
            "provider": metadata.get("gateway_provider") or "unknown",
            "latency_ms": row["latency_ms"],
            "prompt_preview": (row["prompt"] or "")[:160],
        })

    return {"events": events}


@app.get("/api/models")
async def get_models():
    catalog = load_model_catalog(OUTPUT_DIR)
    provider_ids = [provider.get("id") for provider in list_provider_configs(include_disabled=False) if provider.get("id")]
    return {
        "models": catalog.get("models", []),
        "judge_model_id": get_judge_model_id(),
        "available_providers": provider_ids or ["ollama", "openai", "nvidia", "gemini", "anthropic"],
        "ollama_models": _ollama_model_names(),
    }


@app.post("/api/models")
async def save_model(req: ModelConfigRequest):
    _require_active_project_role("admin")
    catalog = upsert_model(OUTPUT_DIR, req.model_dump())
    return {"status": "ok", "models": catalog.get("models", [])}


@app.delete("/api/models/{model_id}")
async def remove_model(model_id: str):
    _require_active_project_role("admin")
    catalog = load_model_catalog(OUTPUT_DIR)
    existing = next((model for model in catalog.get("models", []) if model.get("id") == model_id), None)
    if existing and existing.get("source") == "default":
        raise HTTPException(status_code=400, detail="Default catalog models cannot be removed. Disable or edit them instead.")
    catalog = delete_model(OUTPUT_DIR, model_id)
    return {"status": "ok", "models": catalog.get("models", [])}


@app.post("/api/models/judge")
async def set_judge_model(req: JudgeModelRequest):
    _require_active_project_role("admin")
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
    _require_active_project_role("member")
    config = load_product_config()
    active_output_dir = pathlib.Path((config.get("output_dir") or str(OUTPUT_DIR))).expanduser()
    active_db_path = pathlib.Path((config.get("db_path") or str(DB_PATH))).expanduser()
    use_saved_snapshot = bool(req.cluster_ids) and not req.skip_eval and (active_output_dir / "cluster_info.json").exists()

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
                    f"Using saved cluster snapshot from {active_output_dir}",
                    stream="meta",
                ))

                from agentshrink.evaluator import EvaluatorConfig, SLMEvaluator

                previous_output_dir = os.environ.get("AGENTSHRINK_OUTPUT_DIR")
                os.environ["AGENTSHRINK_OUTPUT_DIR"] = str(active_output_dir)
                try:
                    cluster_result = await asyncio.to_thread(_load_saved_cluster_snapshot_from, active_output_dir)
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
                        active_output_dir,
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
                "--db", str(active_db_path),
                "--output-dir", str(active_output_dir),
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
    _require_active_project_role("viewer")
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
    _require_active_project_role("viewer")
    return {"backends": backend_statuses()}


@app.get("/api/finetune/jobs")
async def finetune_jobs():
    _require_active_project_role("viewer")
    jobs = [_reconcile_finetune_job(job) for job in job_store.list_jobs()]
    return {"jobs": jobs}


@app.get("/api/finetune/jobs/{job_id}")
async def finetune_job(job_id: str):
    _require_active_project_role("viewer")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Fine-tune job not found.")
    return _reconcile_finetune_job(job)


@app.post("/api/finetune/start")
async def finetune_start(req: StartFineTuneRequest):
    _require_active_project_role("member")
    if req.backend not in {"local", "modal", "huggingface"}:
        raise HTTPException(status_code=400, detail="Choose a supported backend before starting training.")

    prepared = _prepare_finetune_payload(req.cluster_id)
    cluster_name = prepared["cluster_meta"]["name"]
    default_model = choose_default_model(req.backend)
    selected_model_id = req.config.get("base_model") or default_model["id"]
    _validate_model_access(
        backend=req.backend,
        model_id=selected_model_id,
        hf_token=req.hf_token or os.getenv("HF_TOKEN"),
    )
    selected_model = lookup_backend_model(req.backend, selected_model_id) or default_model
    config = {
        "cluster_id": req.cluster_id,
        "cluster_name": cluster_name,
        "base_model": selected_model["id"],
        "deploy_base_model": req.config.get("deploy_base_model") or selected_model["deploy_base_model"],
        "epochs": int(req.config.get("epochs", 2)),
        "batch_size": int(req.config.get("batch_size", 2 if req.backend == "modal" else 1)),
        "learning_rate": float(req.config.get("learning_rate", 2e-4)),
        "lora_r": int(req.config.get("lora_r", 16)),
        "gradient_accumulation_steps": int(req.config.get("gradient_accumulation_steps", 8)),
        "max_seq_length": int(req.config.get("max_seq_length", 512)),
        "hf_token": req.hf_token or os.getenv("HF_TOKEN"),
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
    _require_active_project_role("member")
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
    _require_active_project_role("member")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Fine-tune job not found.")
    deployable_statuses = {"completed", "stopped"}
    if job.get("status") not in deployable_statuses or not job.get("can_register") or not job.get("artifacts"):
        raise HTTPException(
            status_code=400,
            detail="Training must finish with deployable artifacts before deployment.",
        )
    if job_id in finetune_deploy_threads:
        return {"status": "started", "job": job}

    updated = job_store.update_job(job_id, status="deploying", phase="Preparing local deployment", progress=8, error=None)
    worker = threading.Thread(target=_run_deploy_job, args=(job_id,), daemon=True)
    finetune_deploy_threads[job_id] = worker
    worker.start()
    return {"status": "started", "job": updated}


@app.post("/api/finetune/export")
async def finetune_export(req: ExportFineTuneRequest):
    _require_active_project_role("member")
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
    _require_active_project_role("member")
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


@app.get("/api/product/config")
async def product_config():
    return load_product_config()


@app.get("/api/product/providers")
async def product_providers():
    return {
        "providers": list_provider_configs(),
        "presets": PROVIDER_PRESETS,
    }


@app.post("/api/product/providers")
async def upsert_product_provider(req: ProviderConfigRequest):
    _require_active_project_role("owner")
    payload = req.model_dump()
    payload["id"] = payload["id"].strip().lower()
    payload["name"] = payload["name"].strip() or payload["id"].replace("-", " ").title()
    payload["adapter"] = payload["adapter"].strip().lower() or "openai_compatible"
    payload["base_url"] = payload["base_url"].strip()
    payload["api_key"] = payload["api_key"].strip()
    payload["api_key_env"] = payload["api_key_env"].strip()
    payload["base_url_env"] = payload["base_url_env"].strip()
    payload["default_model"] = payload["default_model"].strip()
    payload["description"] = payload["description"].strip()
    if not payload["id"]:
        raise HTTPException(status_code=400, detail="Provider id is required.")
    if payload["adapter"] not in ALLOWED_PROVIDER_ADAPTERS:
        raise HTTPException(status_code=400, detail="Unsupported provider adapter.")
    provider = upsert_provider_config(payload)
    return {
        "provider": provider,
        "providers": list_provider_configs(),
        "presets": PROVIDER_PRESETS,
    }


@app.delete("/api/product/providers/{provider_id}")
async def remove_product_provider(provider_id: str):
    _require_active_project_role("owner")
    try:
        registry = delete_provider_config(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return registry


@app.get("/api/product/provider-presets")
async def product_provider_presets():
    return {
        "presets": PROVIDER_PRESETS,
    }


@app.post("/api/product/providers/{provider_id}/test")
async def test_product_provider(provider_id: str):
    _require_active_project_role("owner")
    provider = get_provider_config(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_id}'.")
    try:
        return test_provider_connection(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/product/providers/{provider_id}/models")
async def product_provider_models(provider_id: str):
    _require_active_project_role("viewer")
    provider = get_provider_config(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_id}'.")
    try:
        return discover_provider_models(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/product/config")
async def update_product_config(req: ProductConfigRequest):
    _require_active_project_role("owner")
    payload = req.model_dump()
    payload["account"] = payload.get("account") or {}
    payload["project"] = payload.get("project") or {}
    payload["project_name"] = payload["project_name"].strip() or "AgentShrink Project"
    payload["account"]["name"] = (payload["account"].get("name") or "Local AgentShrink Workspace").strip() or "Local AgentShrink Workspace"
    payload["account"]["slug"] = (payload["account"].get("slug") or "local-workspace").strip() or "local-workspace"
    payload["project"]["name"] = (payload["project"].get("name") or payload["project_name"]).strip() or payload["project_name"]
    payload["project"]["slug"] = (payload["project"].get("slug") or "agentshrink-project").strip() or "agentshrink-project"
    payload["project"]["environment"] = (payload["project"].get("environment") or "local").strip() or "local"
    payload["db_path"] = str(pathlib.Path(payload["db_path"]).expanduser().resolve())
    payload["output_dir"] = str(pathlib.Path(payload["output_dir"]).expanduser().resolve())
    payload["gateway"]["host"] = payload["gateway"]["host"].strip() or "127.0.0.1"
    payload["dashboard_backend"]["host"] = payload["dashboard_backend"]["host"].strip() or "127.0.0.1"
    payload["gateway"]["upstream_provider"] = payload["gateway"]["upstream_provider"].strip().lower() or "mock"
    if get_provider_config(payload["gateway"]["upstream_provider"]) is None:
        raise HTTPException(status_code=400, detail=f"Unknown upstream provider '{payload['gateway']['upstream_provider']}'.")
    payload["defaults"]["gateway_model"] = payload["defaults"]["gateway_model"].strip() or "mock-model"
    payload["defaults"]["gateway_api_key"] = payload["defaults"]["gateway_api_key"].strip() or "agentshrink-local"
    pathlib.Path(payload["db_path"]).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(payload["output_dir"]).mkdir(parents=True, exist_ok=True)
    saved = save_product_config(payload)
    sync_active_project_to_registry(saved)
    return saved


@app.get("/api/public/identity")
async def public_identity():
    session = _require_authenticated_session()
    config = load_product_config()
    sync_active_project_to_registry(config)
    account = config.get("account") or {}
    project = config.get("project") or {}
    hosted = load_hosted_config()
    visible = _visible_registry_for_session(session)
    token = ((config.get("defaults") or {}).get("gateway_api_key") or "").strip()
    gateway_url = f"http://{config['gateway']['host']}:{config['gateway']['port']}/v1"
    frontend_url = f"http://localhost:{config['dashboard_frontend']['port']}"
    return {
        "account": account,
        "project": project,
        "project_name": config.get("project_name"),
        "project_token_preview": f"{token[:14]}..." if len(token) > 14 else token,
        "gateway_url": gateway_url,
        "docs_url": f"{frontend_url}/site/docs",
        "dashboard_url": frontend_url,
        "environment": project.get("environment") or "local",
        "session": session,
        "memberships": visible.get("memberships") or [],
        "pending_invites": visible.get("invites") or [],
        "hosted": hosted,
    }


@app.get("/api/public/projects")
async def public_projects():
    session = _require_authenticated_session()
    config = load_product_config()
    sync_active_project_to_registry(config)
    registry = _visible_registry_for_session(session)
    projects = []
    for project in registry.get("projects") or []:
        project_copy = dict(project)
        project_copy["usage"] = _project_usage_summary(project)
        projects.append(project_copy)
    registry["projects"] = projects
    return registry


@app.get("/api/public/session")
async def public_session():
    session = load_session()
    email = _session_user_email(session)
    session["memberships"] = user_team_memberships(email) if email else []
    session["pending_invites"] = list_pending_invites(user_email=email) if email else []
    return session


@app.post("/api/public/session/login")
async def public_session_login(req: SessionLoginRequest):
    user_name = req.user_name.strip()
    user_email = req.user_email.strip()
    if not user_name or not user_email:
        raise HTTPException(status_code=400, detail="Both user name and user email are required.")
    return create_session(user_name=user_name, user_email=user_email)


@app.post("/api/public/session/magic-link/request")
async def public_session_magic_link_request(req: MagicLinkRequest):
    user_email = req.user_email.strip().lower()
    user_name = (req.user_name or "").strip() or None
    if not user_email:
        raise HTTPException(status_code=400, detail="User email is required.")
    return request_magic_link(user_email=user_email, user_name=user_name)


@app.post("/api/public/session/magic-link/consume")
async def public_session_magic_link_consume(req: MagicLinkConsumeRequest):
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Magic-link token is required.")
    try:
        return consume_magic_link(token=token)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Magic link not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/public/auth/providers")
async def public_auth_providers():
    auth_provider = get_auth_provider()
    billing_provider = get_billing_provider()
    hosted = load_hosted_config()
    return {
        "auth": auth_provider.describe(),
        "billing": billing_provider.describe(),
        "hosted": hosted,
    }


@app.post("/api/public/auth/start")
async def public_auth_start(req: ExternalAuthStartRequest):
    provider = get_auth_provider()
    if not hasattr(provider, "start"):
        raise HTTPException(status_code=400, detail="External auth is not enabled for the current provider.")
    hosted = load_hosted_config()
    public_app_url = ((hosted.get("deployment") or {}).get("public_app_url") or "http://localhost:3000").rstrip("/")
    redirect_uri = (req.redirect_uri or f"{public_app_url}/auth").strip()
    try:
        return provider.start(redirect_uri=redirect_uri)
    except AuthProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/public/auth/callback")
async def public_auth_callback(req: ExternalAuthCallbackRequest):
    provider = get_auth_provider()
    if not hasattr(provider, "callback"):
        raise HTTPException(status_code=400, detail="External auth callback is not enabled for the current provider.")
    hosted = load_hosted_config()
    public_app_url = ((hosted.get("deployment") or {}).get("public_app_url") or "http://localhost:3000").rstrip("/")
    redirect_uri = (req.redirect_uri or f"{public_app_url}/auth").strip()
    try:
        return provider.callback(code=req.code.strip(), redirect_uri=redirect_uri)
    except AuthProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/public/session/logout")
async def public_session_logout():
    return clear_session()


@app.get("/api/public/invites")
async def public_invites():
    session = _require_authenticated_session()
    return {
        "invites": list_pending_invites(user_email=_session_user_email(session)),
        "session": session,
    }


@app.post("/api/public/invites/{token}/accept")
async def public_accept_invite(token: str, req: AcceptInviteRequest):
    session = _require_authenticated_session()
    user = session.get("user") or {}
    user_name = (req.user_name or user.get("name") or "").strip()
    user_email = (req.user_email or user.get("email") or "").strip().lower()
    if not user_name or not user_email:
        raise HTTPException(status_code=400, detail="A signed-in user name and email are required to accept an invite.")
    try:
        result = accept_team_invite(token=token, user_name=user_name, user_email=user_email)
        _sync_tenant_billing_snapshot(load_project_registry())
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Invite not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/public/projects")
async def create_public_project(req: CreateHostedProjectRequest):
    session = _require_authenticated_session()
    active_team_id = session.get("active_team_id") or "team_local_default"
    _require_team_role(active_team_id, "member", session=session)
    name = req.name.strip()
    upstream_provider = req.upstream_provider.strip().lower() or "mock"
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required.")
    if get_provider_config(upstream_provider) is None:
        raise HTTPException(status_code=400, detail=f"Unknown upstream provider '{upstream_provider}'.")
    result = create_product_project(
        project_name=name,
        environment=req.environment.strip() or "local",
        upstream_provider=upstream_provider,
        team_id=active_team_id,
    )
    _sync_tenant_billing_snapshot(load_project_registry())
    return result


@app.post("/api/public/projects/{project_id}/activate")
async def activate_public_project(project_id: str):
    try:
        session = _require_authenticated_session()
        project = _require_project_access(project_id, "viewer", session=session)
        session["active_team_id"] = project.get("team_id") or session.get("active_team_id")
        save_session(session)
        return activate_product_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


@app.get("/api/public/teams")
async def public_teams():
    registry = _visible_registry_for_session(_require_authenticated_session())
    return {
        "account": registry.get("account") or {},
        "teams": registry.get("teams") or [],
        "memberships": registry.get("memberships") or [],
        "invites": registry.get("invites") or [],
        "projects": [
            {
                "id": project.get("id"),
                "name": project.get("name"),
                "team_id": project.get("team_id"),
                "environment": project.get("environment"),
            }
            for project in (registry.get("projects") or [])
        ],
    }


@app.post("/api/public/teams")
async def public_create_team(req: CreateTeamRequest):
    _require_authenticated_session()
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required.")
    result = create_team(name=name, slug=(req.slug or "").strip() or None)
    _sync_tenant_billing_snapshot(load_project_registry())
    return result


@app.post("/api/public/teams/{team_id}/invite")
async def public_invite_team_member(team_id: str, req: InviteTeamMemberRequest):
    session = _require_authenticated_session()
    _require_team_role(team_id, "admin", session=session)
    if not req.user_email.strip():
        raise HTTPException(status_code=400, detail="Invitee email is required.")
    if not req.user_name.strip():
        raise HTTPException(status_code=400, detail="Invitee name is required.")
    result = invite_team_member(
        team_id=team_id,
        user_name=req.user_name.strip(),
        user_email=req.user_email.strip(),
        role=req.role.strip() or "member",
    )
    _sync_tenant_billing_snapshot(load_project_registry())
    return result


@app.post("/api/public/teams/{team_id}/members/{user_email}/role")
async def public_update_team_member_role(team_id: str, user_email: str, req: UpdateTeamMemberRoleRequest):
    try:
        session = _require_authenticated_session()
        current_membership = _require_team_role(team_id, "owner", session=session)
        next_role = req.role.strip() or "member"
        if next_role == "owner" and (current_membership.get("role") or "") != "owner":
            raise HTTPException(status_code=403, detail="Only owners can grant owner access.")
        return update_team_member_role(team_id=team_id, user_email=user_email, role=req.role.strip() or "member")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Team member not found.") from exc


@app.get("/api/public/projects/{project_id}/activity")
async def public_project_activity(project_id: str, limit: int = 20):
    project = _require_project_access(project_id, "viewer")

    config = project.get("config") or {}
    db_path = pathlib.Path((config.get("db_path") or "")).expanduser()
    usage = _project_usage_summary(project)
    if not db_path.exists():
        return {
            "project": {
                "id": project.get("id"),
                "name": project.get("name"),
                "slug": project.get("slug"),
                "environment": project.get("environment"),
                "team_id": project.get("team_id"),
            },
            "usage": usage,
            "recent_calls": [],
        }

    limit = max(1, min(limit, 100))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT timestamp, node_name, model_name, prompt, latency_ms, extra_metadata
            FROM llm_calls
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    recent_calls = []
    for row in rows:
        try:
            metadata = json.loads(row["extra_metadata"] or "{}")
        except Exception:
            metadata = {}
        recent_calls.append({
            "timestamp": row["timestamp"],
            "node_name": row["node_name"],
            "model_name": row["model_name"],
            "prompt_preview": (row["prompt"] or "")[:140],
            "latency_ms": row["latency_ms"],
            "gateway_mode": metadata.get("gateway_mode"),
            "provider": metadata.get("gateway_provider"),
        })

    return {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "slug": project.get("slug"),
            "environment": project.get("environment"),
            "team_id": project.get("team_id"),
        },
        "usage": usage,
        "recent_calls": recent_calls,
    }


@app.get("/api/public/projects/{project_id}/routing")
async def public_project_routing(project_id: str, limit: int = 50):
    project = _require_project_access(project_id, "viewer")
    return {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "slug": project.get("slug"),
            "environment": project.get("environment"),
            "team_id": project.get("team_id"),
        },
        "stats": _project_routing_stats(project),
        "events": _project_gateway_activity(project, limit),
    }


@app.get("/api/public/projects/{project_id}/report")
async def public_project_report(project_id: str):
    project = _require_project_access(project_id, "viewer")
    return {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "slug": project.get("slug"),
            "environment": project.get("environment"),
            "team_id": project.get("team_id"),
        },
        "report": _project_report_payload(project),
    }


@app.get("/api/public/projects/{project_id}/summary")
async def public_project_summary(project_id: str):
    project = _require_project_access(project_id, "viewer")
    config = project.get("config") or {}
    db_path = pathlib.Path((config.get("db_path") or "")).expanduser()
    output_dir = _project_output_dir(project)
    status = _status_payload_for(db_path, output_dir)
    registry = load_project_registry()
    routing_stats = _project_routing_stats(project)
    return {
        "status": status,
        "sources": {
            "traffic": {
                "kind": "sqlite:llm_calls",
                "ready": bool(status.get("has_data")),
                "call_count": status.get("total_calls", 0),
                "gateway_event_count": status.get("gateway_event_count", 0),
                "latest_timestamp": status.get("latest_timestamp"),
            },
            "analysis": {
                "kind": "analysis-output",
                "ready": bool(status.get("analysis_done")),
                "cluster_count": len((_load_cluster_info_from(output_dir) or {}).get("clusters", {})),
            },
            "report": {
                "kind": "replaceability-report",
                "ready": bool(status.get("report_done")),
            },
            "routing": {
                "kind": "routing-config",
                "ready": bool(routing_stats.get("configured")),
                "cluster_count": int(routing_stats.get("cluster_count", 0) or 0),
            },
        },
        "account": registry.get("account") or {},
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "slug": project.get("slug"),
            "environment": project.get("environment"),
            "team_id": project.get("team_id"),
        },
    }


@app.get("/api/public/projects/{project_id}/clusters")
async def public_project_clusters(project_id: str):
    project = _require_project_access(project_id, "viewer")
    return _cluster_payload_for(_project_output_dir(project))


@app.get("/api/public/hosted/config")
async def public_hosted_config():
    _require_authenticated_session()
    return load_hosted_config()


@app.put("/api/public/hosted/config")
async def public_update_hosted_config(req: HostedConfigRequest):
    session = _require_authenticated_session()
    active_team_id = session.get("active_team_id") or "team_local_default"
    _require_team_role(active_team_id, "owner", session=session)
    return save_hosted_config(req.config)


@app.get("/api/public/billing")
async def public_billing():
    session = _require_authenticated_session()
    registry = _visible_registry_for_session(session)
    hosted = load_hosted_config()
    ledger = _sync_tenant_billing_snapshot(load_project_registry())
    total_calls = 0
    total_runs = 0
    for project in registry.get("projects") or []:
        usage = _project_usage_summary(project)
        total_calls += int(usage.get("total_calls") or 0)
        total_runs += int(usage.get("total_runs") or 0)
    return {
        "account": registry.get("account") or {},
        "billing": registry.get("billing") or {},
        "hosted": hosted.get("billing") or {},
        "ledger": ledger,
        "metrics": {
            "projects": len(registry.get("projects") or []),
            "teams": len(registry.get("teams") or []),
            "members": len(registry.get("memberships") or []),
            "total_calls": total_calls,
            "total_runs": total_runs,
        },
    }


@app.post("/api/public/billing/checkout")
async def public_billing_checkout(req: BillingCheckoutRequest):
    session = _require_authenticated_session()
    active_team_id = session.get("active_team_id") or "team_local_default"
    _require_team_role(active_team_id, "owner", session=session)
    registry = load_project_registry()
    account = registry.get("account") or {}
    hosted = load_hosted_config()
    public_app_url = (req.return_url or ((hosted.get("deployment") or {}).get("public_app_url") or "http://localhost:3000")).rstrip("/")
    provider = get_billing_provider()
    if not hasattr(provider, "checkout"):
        raise HTTPException(status_code=400, detail="Hosted billing checkout is not enabled for the current provider.")
    try:
        result = provider.checkout(
            public_app_url=public_app_url,
            tenant_id=account.get("tenant_id") or "tenant_local_default",
            account_id=account.get("id") or "acct_local_default",
            account_name=account.get("name") or "AgentShrink Workspace",
        )
    except AuthProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "provider": result.get("object") or getattr(provider, "name", "stripe"),
        "checkout_url": result.get("url"),
        "raw": result,
    }


@app.post("/api/product/token/rotate")
async def rotate_product_token():
    _require_active_project_role("owner")
    config = load_product_config()
    config.setdefault("defaults", {})
    config["defaults"]["gateway_api_key"] = generate_project_token()
    saved = save_product_config(config)
    sync_active_project_to_registry(saved)
    return {
        "status": "ok",
        "message": "Project token rotated. Restart the gateway/stack so new clients use the updated token.",
        "project_token": saved["defaults"]["gateway_api_key"],
        "config": saved,
    }


@app.get("/api/product/doctor")
async def product_doctor():
    checks = run_doctor_checks()
    return {
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "detail": check.detail,
                "remedy": check.remedy,
                "category": check.category,
                "severity": check.severity,
                "commands": check.commands or [],
            }
            for check in checks
        ]
    }


def _probe_http(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            return 200 <= getattr(response, "status", 0) < 500
    except Exception:
        return False


def _recommended_stack_actions(stack: dict) -> list[dict]:
    all_healthy = bool(stack.get("all_healthy"))
    any_running = bool(stack.get("any_running"))

    if all_healthy:
        return [
            {
                "id": "inspect-status",
                "label": "Inspect stack status",
                "command": "venv\\Scripts\\python.exe -m agentshrink.cli stack status",
                "kind": "inspect",
                "risk": "safe",
                "reason": "All services are healthy. No restart is needed right now.",
            }
        ]

    if any_running:
        dead_services = [
            name for name in ("gateway", "backend", "frontend")
            if not (stack.get(name) or {}).get("healthy")
        ]
        return [
            {
                "id": "inspect-status",
                "label": "Inspect stack status",
                "command": "venv\\Scripts\\python.exe -m agentshrink.cli stack status",
                "kind": "inspect",
                "risk": "safe",
                "reason": "One or more services are unhealthy. Inspect before taking action.",
            },
            {
                "id": "graceful-restart",
                "label": "Restart the stack cleanly",
                "command": "venv\\Scripts\\python.exe -m agentshrink.cli stack down\nvenv\\Scripts\\python.exe -m agentshrink.cli stack up",
                "kind": "restart",
                "risk": "caution",
                "reason": (
                    "Recommended because these services are not healthy: "
                    f"{', '.join(dead_services) if dead_services else 'unknown'}."
                ),
            },
        ]

    return [
        {
            "id": "start-stack",
            "label": "Start the local stack",
            "command": "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
            "kind": "start",
            "risk": "safe",
            "reason": "No running services were detected, so the next safe step is to start the stack.",
        }
    ]


def _session_user_email(session: dict | None = None) -> str:
    session = session or load_session()
    return ((session.get("user") or {}).get("email") or "").strip().lower()


def _single_user_workspace() -> bool:
    hosted = load_hosted_config()
    deployment_mode = str(((hosted.get("deployment") or {}).get("mode") or "local-hosted")).strip().lower()
    return deployment_mode in {"local-hosted", "local", ""}


def _require_authenticated_session() -> dict:
    session = load_session()
    if _single_user_workspace() and not session.get("authenticated"):
        create_session(user_name="Local Owner", user_email="local-owner@agentshrink.local")
        session = load_session()
    if not session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Sign in first to access the hosted workspace.")
    email = _session_user_email(session)
    if not email:
        raise HTTPException(status_code=401, detail="A valid session email is required.")
    return session


def _team_record(team_id: str) -> dict | None:
    registry = load_project_registry()
    return next((team for team in (registry.get("teams") or []) if team.get("id") == team_id), None)


def _require_team_role(team_id: str, minimum_role: str, *, session: dict | None = None) -> dict:
    session = session or _require_authenticated_session()
    if _single_user_workspace():
        return {
            "team_id": team_id or "team_local_default",
            "user_name": ((session.get("user") or {}).get("name") or "Local Owner"),
            "user_email": _session_user_email(session) or "local-owner@agentshrink.local",
            "role": "owner",
        }
    membership = get_team_membership(team_id, _session_user_email(session))
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this team.")
    if not role_meets_minimum(membership.get("role") or "viewer", minimum_role):
        raise HTTPException(status_code=403, detail=f"This action requires at least {minimum_role} access.")
    return membership


def _require_project_access(project_id: str, minimum_role: str = "viewer", *, session: dict | None = None) -> dict:
    session = session or _require_authenticated_session()
    project = _find_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_team_role(project.get("team_id") or "team_local_default", minimum_role, session=session)
    return project


def _require_active_project_role(minimum_role: str = "viewer", *, session: dict | None = None) -> tuple[dict, dict]:
    session = session or _require_authenticated_session()
    config = load_product_config()
    project = config.get("project") or {}
    project_id = project.get("id") or (session.get("active_project_id") or "")
    if not project_id:
        raise HTTPException(status_code=400, detail="No active project is configured.")
    return _require_project_access(project_id, minimum_role, session=session), session


def _visible_registry_for_session(session: dict | None = None) -> dict:
    session = session or _require_authenticated_session()
    registry = load_project_registry()
    if _single_user_workspace():
        synthetic_membership = {
            "team_id": (session.get("active_team_id") or "team_local_default"),
            "user_name": ((session.get("user") or {}).get("name") or "Local Owner"),
            "user_email": _session_user_email(session) or "local-owner@agentshrink.local",
            "role": "owner",
        }
        return {
            "account": registry.get("account") or {},
            "users": registry.get("users") or [],
            "teams": registry.get("teams") or [],
            "memberships": [synthetic_membership],
            "projects": registry.get("projects") or [],
            "active_project_id": registry.get("active_project_id"),
            "invites": [],
            "billing": registry.get("billing") or {},
        }
    email = _session_user_email(session)
    memberships = user_team_memberships(email)
    team_ids = {membership.get("team_id") for membership in memberships}
    visible_teams = [team for team in (registry.get("teams") or []) if team.get("id") in team_ids]
    visible_projects = [project for project in (registry.get("projects") or []) if project.get("team_id") in team_ids]
    return {
        "account": registry.get("account") or {},
        "users": registry.get("users") or [],
        "teams": visible_teams,
        "memberships": memberships,
        "projects": visible_projects,
        "active_project_id": registry.get("active_project_id"),
        "invites": list_pending_invites(user_email=email),
        "billing": registry.get("billing") or {},
    }


def _load_cluster_info_from(output_dir: pathlib.Path) -> dict | None:
    cluster_info_path = output_dir / "cluster_info.json"
    if not cluster_info_path.exists():
        return None
    with open(cluster_info_path, encoding="utf-8") as f:
        return json.load(f)


def _status_payload_for(db_path: pathlib.Path, output_dir: pathlib.Path) -> dict:
    if not db_path.exists():
        return {
            "total_calls": 0,
            "total_runs": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "nodes": [],
            "daily_counts": [],
            "db_path": str(db_path),
            "has_data": False,
            "successful_call_count": 0,
            "gateway_event_count": 0,
            "latest_timestamp": None,
            "source_of_truth": "sqlite:llm_calls",
            "analysis_done": False,
            "report_done": False,
            "ready_for_analysis": False,
            "node_statuses": {},
        }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as n FROM llm_calls")
        total_calls = int(c.fetchone()["n"] or 0)
        c.execute("SELECT COUNT(*) as n FROM llm_calls WHERE workflow_success=1")
        successful_calls = int(c.fetchone()["n"] or 0)
        c.execute("SELECT COUNT(DISTINCT run_id) as n FROM llm_calls")
        total_runs = int(c.fetchone()["n"] or 0)
        c.execute("SELECT COALESCE(SUM(tokens_in+tokens_out),0) as n FROM llm_calls")
        total_tokens = int(c.fetchone()["n"] or 0)
        c.execute("SELECT COALESCE(SUM(cost_usd),0) as n FROM llm_calls")
        total_cost = float(c.fetchone()["n"] or 0.0)
        c.execute("SELECT prompt, response, tokens_in, tokens_out, model_name FROM llm_calls")
        rows = c.fetchall()
        c.execute(
            """
            SELECT node_name, COUNT(*) as count,
                   AVG(latency_ms) as avg_latency,
                   AVG(cost_usd) as avg_cost
            FROM llm_calls
            GROUP BY node_name ORDER BY count DESC
            """
        )
        nodes = [dict(row) for row in c.fetchall()]
        c.execute(
            """
            SELECT DATE(timestamp) as day, COUNT(*) as count
            FROM llm_calls
            WHERE timestamp >= DATE('now', '-14 days')
            GROUP BY day ORDER BY day ASC
            """
        )
        daily_counts = [dict(row) for row in c.fetchall()]
        c.execute(
            """
            SELECT COUNT(*) as n
            FROM llm_calls
            WHERE extra_metadata LIKE '%"gateway_mode"%'
            """
        )
        gateway_event_count = int(c.fetchone()["n"] or 0)
        c.execute("SELECT MAX(timestamp) as latest_timestamp FROM llm_calls")
        latest_timestamp = c.fetchone()["latest_timestamp"]

    active_provider = _active_provider_context()
    baseline_model = os.getenv("AGENTSHRINK_ESTIMATE_MODEL") or active_provider["gateway_model"] or "gpt-4o-mini"
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

    cluster_info = _load_cluster_info_from(output_dir)
    analysis_done = cluster_info is not None
    report_done = (output_dir / "replaceability_report.json").exists()
    return {
        "total_calls": total_calls,
        "total_runs": total_runs,
        "total_tokens": total_tokens,
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
        "successful_call_count": successful_calls,
        "gateway_event_count": gateway_event_count,
        "latest_timestamp": latest_timestamp,
        "source_of_truth": "sqlite:llm_calls",
        "nodes": nodes,
        "daily_counts": daily_counts,
        "db_path": str(db_path),
        "has_data": total_calls > 0,
        "analysis_done": analysis_done,
        "report_done": report_done,
        "ready_for_analysis": total_calls >= ANALYSIS_READY_CALL_THRESHOLD,
        "node_statuses": _build_node_statuses(cluster_info),
    }


def _cluster_payload_for(output_dir: pathlib.Path) -> dict:
    cluster_info_path = output_dir / "cluster_info.json"
    clustered_df_path = output_dir / "clustered_df.parquet"
    if not cluster_info_path.exists():
        raise HTTPException(status_code=404, detail="No cluster data found. Run: agentshrink analyse")

    with open(cluster_info_path, encoding="utf-8") as f:
        cluster_info = json.load(f)

    points = []
    if clustered_df_path.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(clustered_df_path)
            palette = ["#1D9E75", "#7F77DD", "#EF9F27", "#D85A30", "#185FA5", "#9F3F7A", "#5D8A1A", "#C44B4B", "#2B8B8B"]
            for _, row in df.iterrows():
                cid = int(row.get("cluster_id", -1))
                if cid == -1:
                    continue
                points.append({
                    "x": float(row.get("umap_x", 0)),
                    "y": float(row.get("umap_y", 0)),
                    "cluster_id": cid,
                    "cluster_name": str(row.get("cluster_name", f"cluster_{cid}")),
                    "color": row.get("cluster_color", palette[cid % len(palette)]),
                    "prompt_preview": str(row.get("prompt", ""))[:80],
                    "node_name": str(row.get("node_name", "")),
                })
        except Exception as exc:
            logger.warning(f"Could not load cluster points from {output_dir}: {exc}")

    return {
        "n_clusters": cluster_info.get("n_clusters", 0),
        "n_noise": cluster_info.get("n_noise", 0),
        "cluster_names": cluster_info.get("cluster_names", {}),
        "clusters": cluster_info.get("clusters", {}),
        "points": points,
    }


def _project_usage_summary(project: dict) -> dict:
    config = project.get("config") or {}
    db_path = pathlib.Path((config.get("db_path") or "")).expanduser()
    if not db_path.exists():
        return {
            "db_path": str(db_path),
            "has_data": False,
            "total_calls": 0,
            "total_runs": 0,
            "latest_timestamp": None,
            "gateway_event_count": 0,
        }

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as n FROM llm_calls")
        total_calls = int(c.fetchone()["n"] or 0)
        c.execute("SELECT COUNT(DISTINCT run_id) as n FROM llm_calls")
        total_runs = int(c.fetchone()["n"] or 0)
        c.execute("SELECT MAX(timestamp) as ts FROM llm_calls")
        latest_timestamp = c.fetchone()["ts"]
        c.execute("""
            SELECT COUNT(*) as n
            FROM llm_calls
            WHERE extra_metadata LIKE '%"gateway_mode"%'
        """)
        gateway_event_count = int(c.fetchone()["n"] or 0)

    return {
        "db_path": str(db_path),
        "has_data": total_calls > 0,
        "total_calls": total_calls,
        "total_runs": total_runs,
        "latest_timestamp": latest_timestamp,
        "gateway_event_count": gateway_event_count,
    }


def _find_project(project_id: str) -> dict | None:
    registry = load_project_registry()
    return next((project for project in (registry.get("projects") or []) if project.get("id") == project_id), None)


def _project_output_dir(project: dict) -> pathlib.Path:
    config = project.get("config") or {}
    return pathlib.Path((config.get("output_dir") or str(OUTPUT_DIR))).expanduser()


def _sync_tenant_billing_snapshot(registry: dict | None = None) -> dict:
    registry = registry or load_project_registry()
    account = registry.get("account") or {}
    tenant_id = (account.get("tenant_id") or "tenant_local_default").strip()
    snapshot = {
        "account_id": account.get("id"),
        "tenant_id": tenant_id,
        "plan": (registry.get("billing") or {}).get("plan", "beta"),
        "projects": len(registry.get("projects") or []),
        "memberships": len(registry.get("memberships") or []),
        "total_calls": 0,
        "total_runs": 0,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for project in registry.get("projects") or []:
        usage = _project_usage_summary(project)
        snapshot["total_calls"] += int(usage.get("total_calls") or 0)
        snapshot["total_runs"] += int(usage.get("total_runs") or 0)
    return record_tenant_billing_snapshot(tenant_id, snapshot)


def _project_report_payload(project: dict) -> dict:
    output_dir = _project_output_dir(project)
    report_path = output_dir / "replaceability_report.json"
    cluster_info_path = output_dir / "cluster_info.json"
    cluster_info = None
    if cluster_info_path.exists():
        with open(cluster_info_path, encoding="utf-8") as f:
            cluster_info = json.load(f)
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            return _enrich_report_payload(json.load(f))
    return _enrich_report_payload(_heuristic_report_from_clusters(cluster_info))


def _project_gateway_activity(project: dict, limit: int) -> list[dict]:
    config = project.get("config") or {}
    db_path = pathlib.Path((config.get("db_path") or "")).expanduser()
    if not db_path.exists():
        return []
    limit = max(1, min(limit, 200))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT timestamp, node_name, model_name, prompt, response, latency_ms, extra_metadata
            FROM llm_calls
            WHERE extra_metadata LIKE '%"gateway_mode"%'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    events = []
    for row in rows:
        try:
            metadata = json.loads(row["extra_metadata"] or "{}")
        except Exception:
            metadata = {}
        events.append({
            "timestamp": row["timestamp"],
            "node_name": row["node_name"],
            "model_name": row["model_name"],
            "model_display": metadata.get("route_model_display") or row["model_name"],
            "cluster_name": metadata.get("route_cluster_name") or "unknown",
            "confidence": float(metadata.get("route_confidence") or 0.0),
            "is_local": bool(metadata.get("route_is_local")),
            "nearest_cluster_name": metadata.get("nearest_cluster_name"),
            "nearest_similarity": float(metadata.get("nearest_similarity") or 0.0),
            "threshold": float(metadata.get("threshold") or 0.0),
            "reason": metadata.get("route_reason") or "",
            "gateway_mode": metadata.get("gateway_mode") or "upstream",
            "provider": metadata.get("gateway_provider") or "unknown",
            "latency_ms": row["latency_ms"],
            "prompt_preview": (row["prompt"] or "")[:160],
        })
    return events


def _project_routing_stats(project: dict) -> dict:
    output_dir = _project_output_dir(project)
    if not (output_dir / "centroids.npy").exists():
        return {"configured": False, "message": "Run agentshrink analyse to configure routing"}
    try:
        from agentshrink.centroid_index import CentroidIndex
        index = CentroidIndex.from_output_dir(output_dir)
        stats = index.get_stats()
        return {"configured": True, **stats}
    except Exception as exc:
        return {"configured": False, "error": str(exc)}


@app.get("/api/product/stack")
async def product_stack():
    config = load_product_config()
    runtime = load_runtime_state()
    services = runtime.get("services", {}) or {}

    gateway_url = f"http://{config['gateway']['host']}:{config['gateway']['port']}"
    backend_url = f"http://{config['dashboard_backend']['host']}:{config['dashboard_backend']['port']}"
    frontend_url = f"http://127.0.0.1:{config['dashboard_frontend']['port']}"
    gateway_health_url = f"{gateway_url}/health"
    backend_health_url = f"{backend_url}/api/health"
    frontend_health_url = f"{frontend_url}/"

    stack = {
        "gateway": {
            "configured_url": gateway_health_url,
            "process_recorded": bool(services.get("gateway")),
            "healthy": _probe_http(gateway_health_url),
        },
        "backend": {
            "configured_url": backend_health_url,
            "process_recorded": bool(services.get("backend")),
            # If this handler is responding, the backend is already healthy.
            # Avoid probing the same server over HTTP from inside this request.
            "healthy": True,
        },
        "frontend": {
            "configured_url": frontend_health_url,
            "process_recorded": bool(services.get("frontend")),
            "healthy": _probe_http(frontend_health_url),
        },
    }

    stack["all_healthy"] = all(service["healthy"] for service in stack.values())
    stack["any_running"] = any(service["healthy"] or service["process_recorded"] for service in stack.values())
    stack["port_conflicts"] = [
        {
            "service": name,
            "configured_url": service["configured_url"],
            "busy": _probe_http(service["configured_url"]) or service["process_recorded"],
        }
        for name, service in stack.items()
        if isinstance(service, dict) and "configured_url" in service and not service["healthy"]
    ]
    stack["recommended_actions"] = _recommended_stack_actions(stack)
    return stack


@app.get("/api/dashboard/summary")
async def dashboard_summary():
    status = await get_status()
    config = load_product_config()
    cluster_info = _load_cluster_info()
    current_routing = _load_existing_routing_config()
    routing_payload = current_routing.get("routing", current_routing) if isinstance(current_routing, dict) else {}
    return {
        "status": status,
        "sources": {
            "traffic": {
                "kind": "sqlite_llm_calls",
                "ready": bool(status.get("has_data")),
                "call_count": int(status.get("total_calls") or 0),
                "gateway_event_count": int(status.get("gateway_event_count") or 0),
                "latest_timestamp": status.get("latest_timestamp"),
            },
            "analysis": {
                "kind": "cluster_info.json",
                "ready": cluster_info is not None,
                "cluster_count": int((cluster_info or {}).get("n_clusters") or 0),
            },
            "report": {
                "kind": "replaceability_report.json",
                "ready": bool(status.get("report_done")),
            },
            "routing": {
                "kind": "routing_config.json",
                "ready": bool(routing_payload),
                "cluster_count": len(routing_payload),
            },
        },
        "quickstart": {
            "start_stack": "agentshrink stack up",
            "open_dashboard": f"http://localhost:{config['dashboard_frontend']['port']}/welcome",
            "gateway_url": f"http://{config['gateway']['host']}:{config['gateway']['port']}/v1",
        },
        "account": config.get("account") or {},
        "project": config.get("project") or {},
    }


@app.get("/api/product/logs")
async def product_logs(service: str, stream: str = "stdout", lines: int = 80):
    runtime = load_runtime_state()
    services = runtime.get("services", {}) or {}
    svc = services.get(service)
    if not svc:
        raise HTTPException(status_code=404, detail=f"No runtime service recorded for '{service}'.")

    key = "stderr_log" if stream == "stderr" else "stdout_log"
    log_path = pathlib.Path(svc.get(key, ""))
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"No {stream} log found for '{service}'.")

    max_lines = max(1, min(int(lines), 400))
    with open(log_path, encoding="utf-8", errors="replace") as f:
        content_lines = f.readlines()

    return {
        "service": service,
        "stream": stream,
        "path": str(log_path),
        "lines": [line.rstrip("\n") for line in content_lines[-max_lines:]],
    }


@app.post("/api/product/test-gateway")
async def product_test_gateway():
    _require_active_project_role("viewer")
    config = load_product_config()
    gateway_base = f"http://{config['gateway']['host']}:{config['gateway']['port']}/v1/chat/completions"
    upstream_provider = ((config.get("gateway") or {}).get("upstream_provider") or "").strip().lower()
    provider_config = get_provider_config(upstream_provider)
    configured_model = ((config.get("defaults") or {}).get("gateway_model") or "").strip()
    provider_default_model = str((provider_config or {}).get("default_model") or "").strip()
    selected_model = configured_model
    if upstream_provider != "mock" and (not selected_model or selected_model == "mock-model") and provider_default_model:
        selected_model = provider_default_model
    payload = {
        "model": selected_model or config["defaults"]["gateway_model"],
        "messages": [
            {"role": "system", "content": "You are a short onboarding assistant."},
            {"role": "user", "content": "Reply in one short sentence that confirms the AgentShrink gateway is working."},
        ],
        "metadata": {
            "agentshrink_node": "welcome_gateway_probe",
        },
    }
    req = urllib.request.Request(
        gateway_base,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['defaults']['gateway_api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        message = (
            (((body.get("choices") or [{}])[0]).get("message") or {}).get("content")
            or ""
        )
        if upstream_provider == "mock":
            message = "AgentShrink gateway is working and ready to receive your app traffic."
        return {
            "status": "ok",
            "gateway_url": gateway_base,
            "model": payload["model"],
            "message": message,
        }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=400, detail=f"Gateway test failed: {detail}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Gateway test failed: {exc}") from exc


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
