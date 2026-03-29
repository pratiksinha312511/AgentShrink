"""
agentshrink/cli.py - CLI interface for AgentShrink.

Commands:
  agentshrink status     -> Show captured call summary (Phase 1)
  agentshrink analyse    -> Run clustering + report (Phase 2+3)
  agentshrink shrink     -> Apply routing (Phase 4 - coming soon)
  agentshrink monitor    -> Quality check (Phase 4+ - coming soon)
"""

import sys
import pathlib
import json
import os
import time

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentshrink.project_config import get_eval_samples_per_cluster
from agentshrink.project_config import get_judge_min_interval_s, get_remote_min_interval_s

console = Console()


def _dominant_node(cluster_info: dict) -> str:
    node_dist = cluster_info.get("node_distribution", {}) or {}
    if not node_dist:
        return ""
    return max(node_dist.items(), key=lambda kv: kv[1])[0]


def _build_heuristic_report(cluster_result: dict) -> dict:
    """Create a local-only heuristic report when full evaluator is skipped."""
    local_model = os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b")
    local_display = f"Local ({local_model})"
    clusters = []

    for cluster_id, info in cluster_result["cluster_info"].items():
        dominant = _dominant_node(info).lower()
        recommendation = "fine_tune"
        best_score = 0.72
        best_slm = local_model
        best_slm_display = local_display
        needs_fine_tuning = True
        fine_tune_base_model = local_model

        if any(key in dominant for key in ("classify", "extract", "format")):
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
            "cluster_id": int(cluster_id),
            "cluster_name": info["name"],
            "cluster_size": int(info["size"]),
            "recommendation": recommendation,
            "best_slm": best_slm,
            "best_slm_display": best_slm_display,
            "best_score": best_score,
            "needs_fine_tuning": needs_fine_tuning,
            "fine_tune_base_model": fine_tune_base_model,
            "estimated_cost_saving_pct": 100.0 if recommendation == "replace_now" else (45.0 if recommendation == "fine_tune" else 0.0),
            "node_distribution": info.get("node_distribution", {}),
            "evaluations": [{
                "slm_name": best_slm or "fallback",
                "slm_display": best_slm_display or "Fallback",
                "correctness_score": best_score,
                "format_score": best_score,
                "completeness_score": max(best_score - 0.05, 0.0),
                "composite_score": best_score,
                "avg_latency_ms": round(info.get("avg_latency_ms", 0), 1),
                "p95_latency_ms": round(info.get("avg_latency_ms", 0) * 1.15, 1),
                "n_evaluated": min(info.get("size", 0), 20),
                "sample_comparisons": [{
                    "prompt": (info.get("sample_prompts") or [""])[0][:180],
                    "reference": "Original response captured in logs.",
                    "candidate": f"Heuristic local recommendation for {info['name']}.",
                }],
            }],
        })

    total_clusters = len(clusters)
    replace_now = [c for c in clusters if c["recommendation"] == "replace_now"]
    fine_tune = [c for c in clusters if c["recommendation"] == "fine_tune"]
    keep_llm = [c for c in clusters if c["recommendation"] == "keep_llm"]
    total_calls = sum(c["cluster_size"] for c in clusters) or 1
    replace_calls = sum(c["cluster_size"] for c in replace_now)
    finetune_calls = sum(c["cluster_size"] for c in fine_tune)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "heuristic": True,
        "summary": {
            "total_clusters": total_clusters,
            "replace_now_count": len(replace_now),
            "fine_tune_count": len(fine_tune),
            "keep_llm_count": len(keep_llm),
            "pct_calls_replaceable_now": round(replace_calls / total_calls * 100, 1),
            "pct_calls_replaceable_with_finetune": round((replace_calls + finetune_calls) / total_calls * 100, 1),
            "models_evaluated": [local_model],
        },
        "clusters": clusters,
    }


@click.group()
def cli():
    """AgentShrink - Automatically convert LLM agents to use cheaper local SLMs.
    Based on NVIDIA arXiv:2506.02153 (June 2025)."""
    pass


@cli.command()
@click.option("--db", default=None, help="Path to logs.db")
def status(db):
    """Show summary of captured LLM calls."""
    from agentshrink.logger import AgentShrinkLogger

    db_path = pathlib.Path(db).expanduser() if db else None
    logger_instance = AgentShrinkLogger.from_db(db_path=db_path)
    summary = logger_instance.get_summary()

    if "error" in summary:
        console.print(f"[red]{summary['error']}[/red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold]AgentShrink Status[/bold]\nDB: {summary['db_path']}",
        border_style="blue",
    ))
    console.print(f"  Total calls:  [bold]{summary['total_calls']}[/bold]")
    console.print(f"  Unique runs:  [bold]{summary['total_runs']}[/bold]")
    console.print(f"  Total tokens: [bold]{summary['total_tokens']:,}[/bold]")
    console.print(f"  Est. cost:    [bold]${summary['total_cost_usd']:.4f}[/bold]")

    total = summary["total_calls"]
    if total < 50:
        console.print(f"\n  [yellow]! Need 100+ calls for clustering. Have {total}.[/yellow]")
    elif total < 200:
        console.print(f"\n  [yellow]i {total} calls - 200+ gives better clusters.[/yellow]")
    else:
        console.print("\n  [green]OK Ready for: agentshrink analyse[/green]")

    if summary["nodes"]:
        table = Table(title="Calls per Node", box=box.ROUNDED, header_style="bold dim")
        table.add_column("Node", style="white", min_width=20)
        table.add_column("Calls", style="cyan", justify="right")
        table.add_column("Avg Latency", style="yellow", justify="right")
        for node in summary["nodes"]:
            table.add_row(node["name"], str(node["count"]), f"{node['avg_latency_ms']}ms")
        console.print(table)


@cli.command()
@click.option("--db", default=None, help="Path to logs.db")
@click.option("--output-dir", default=".agentshrink_output", help="Where to save results")
@click.option("--no-llm-labels", is_flag=True, default=False, help="Use heuristic labels")
@click.option("--skip-eval", is_flag=True, default=False, help="Only cluster, skip SLM evaluation")
@click.option("--min-cluster-size", default=5, type=int, help="HDBSCAN min_cluster_size")
@click.option("--cluster-id", "cluster_ids", multiple=True, type=int, help="Evaluate/report only the specified cluster_id. Can be passed multiple times.")
def analyse(db, output_dir, no_llm_labels, skip_eval, min_cluster_size, cluster_ids):
    """[Phase 2+3] Cluster captured calls and generate Replaceability Report."""
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    output_path = pathlib.Path(output_dir)
    db_path = pathlib.Path(db).expanduser() if db else None

    console.print(Panel.fit(
        "[bold]AgentShrink - Analysis Pipeline[/bold]\n"
        "curate -> cluster -> evaluate -> report",
        border_style="blue",
    ))

    console.print("\n[bold]Step 1/4[/bold] Curating logs...")
    from agentshrink.curator import CuratorConfig, DataCurator

    curator = DataCurator(db_path=db_path, config=CuratorConfig())
    try:
        df, embeddings = curator.curate(source="db")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if len(df) < 20:
        console.print(f"[red]Only {len(df)} entries after curation - need 20+.[/red]")
        sys.exit(1)
    console.print(f"  [green]OK[/green] {len(df)} clean entries")

    console.print("\n[bold]Step 2/4[/bold] Discovering task clusters...")
    from agentshrink.clusterer import ClusterConfig, TaskClusterer

    clusterer = TaskClusterer(config=ClusterConfig(
        min_cluster_size=min_cluster_size,
        umap_n_neighbours=min(10, len(df) - 1),
    ))

    with console.status("UMAP + HDBSCAN running..."):
        cluster_result = clusterer.fit(df, embeddings, use_llm_labels=not no_llm_labels)

    if cluster_result["n_clusters"] == 0:
        console.print("[red]0 clusters found. Try: --min-cluster-size 3[/red]")
        sys.exit(1)

    console.print(f"  [green]OK[/green] Found {cluster_result['n_clusters']} clusters:")
    for cid, info in cluster_result["cluster_info"].items():
        console.print(f"    {cid}: '{info['name']}' ({info['size']} entries)")

    if cluster_ids:
        console.print(
            f"  [cyan]Targeted evaluation enabled for cluster_id(s): {', '.join(str(cid) for cid in cluster_ids)}[/cyan]"
        )

    clusterer.save_results(cluster_result, output_path)

    # Persist TF-IDF vectorizer when sentence-transformers is unavailable.
    if hasattr(curator, "_embedder") and hasattr(curator._embedder, "vectorizer"):
        import joblib
        joblib.dump(curator._embedder.vectorizer, output_path / "tfidf_vectorizer.joblib")
        with open(output_path / "embedder_info.json", "w", encoding="utf-8") as f:
            json.dump({"type": "tfidf"}, f, indent=2)

    if skip_eval:
        heuristic_report = _build_heuristic_report(cluster_result)
        with open(output_path / "replaceability_report.json", "w", encoding="utf-8") as f:
            json.dump(heuristic_report, f, indent=2)
        console.print("\n[yellow]Skipped SLM evaluation (--skip-eval)[/yellow]")
        console.print("[green]OK Heuristic local report generated[/green]")
        console.print(f"[green]OK Results saved to {output_path}[/green]")
        return

    console.print("\n[bold]Step 3/4[/bold] Evaluating clusters against local SLMs...")
    console.print("  [dim]Loading models one at a time - safe for 8GB RAM[/dim]")

    from agentshrink.evaluator import EvaluatorConfig, SLMEvaluator

    evaluator = SLMEvaluator(
        config=EvaluatorConfig(
            n_samples_per_cluster=get_eval_samples_per_cluster(),
            remote_min_interval_s=get_remote_min_interval_s(),
            judge_min_interval_s=get_judge_min_interval_s(),
            verbose=True,
        )
    )

    try:
        with console.status("Evaluating... (~5-15 minutes)"):
            reports = evaluator.evaluate_all_clusters(cluster_result, cluster_ids=list(cluster_ids))
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Fix: ollama serve && ollama pull gemma2:2b")
        console.print("Or skip: agentshrink analyse --skip-eval")
        sys.exit(1)

    console.print("\n[bold]Step 4/4[/bold] Generating report...")
    report_filename = (
        f"replaceability_report_cluster_{cluster_ids[0]}.json"
        if len(cluster_ids) == 1 else
        "replaceability_report.json"
    )
    if len(cluster_ids) > 1:
        joined = "_".join(str(cid) for cid in cluster_ids)
        report_filename = f"replaceability_report_clusters_{joined}.json"
    report_path = evaluator.save_report(reports, output_path, filename=report_filename)
    evaluator.print_report(reports)

    console.print(f"\n[green]OK Report: {report_path}[/green]")
    console.print("Next: [bold]agentshrink shrink[/bold] (Phase 4 - coming soon)")


@cli.command()
@click.option("--apply-report", default=None)
@click.option("--dry-run", is_flag=True, default=False)
def shrink(apply_report, dry_run):
    """[Phase 4] Apply routing config - replace LLM calls with SLMs. Coming soon."""
    console.print("[yellow]Phase 4 (ShrinkLLM router) coming next.[/yellow]")


@cli.command()
def monitor():
    """[Phase 4+] Weekly quality check. Coming soon."""
    console.print("[yellow]Phase 4+ (monitor) coming next.[/yellow]")


if __name__ == "__main__":
    cli()
