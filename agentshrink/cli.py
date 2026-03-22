"""
agentshrink/cli.py — CLI interface for AgentShrink.

Commands:
  agentshrink status     → Show captured call summary (Phase 1)
  agentshrink analyse    → Run clustering + report (Phase 2+3)
  agentshrink shrink     → Apply routing (Phase 4 — coming soon)
  agentshrink monitor    → Quality check (Phase 4+ — coming soon)
"""

import sys
import pathlib
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


@click.group()
def cli():
    """AgentShrink — Automatically convert LLM agents to use cheaper local SLMs.
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
        border_style="blue"
    ))
    console.print(f"  Total calls:  [bold]{summary['total_calls']}[/bold]")
    console.print(f"  Unique runs:  [bold]{summary['total_runs']}[/bold]")
    console.print(f"  Total tokens: [bold]{summary['total_tokens']:,}[/bold]")
    console.print(f"  Est. cost:    [bold]${summary['total_cost_usd']:.4f}[/bold]")

    total = summary["total_calls"]
    if total < 50:
        console.print(f"\n  [yellow]⚠ Need 100+ calls for clustering. Have {total}.[/yellow]")
    elif total < 200:
        console.print(f"\n  [yellow]ℹ {total} calls — 200+ gives better clusters.[/yellow]")
    else:
        console.print(f"\n  [green]✓ Ready for: agentshrink analyse[/green]")

    if summary["nodes"]:
        table = Table(title="Calls per Node", box=box.ROUNDED, header_style="bold dim")
        table.add_column("Node", style="white", min_width=20)
        table.add_column("Calls", style="cyan", justify="right")
        table.add_column("Avg Latency", style="yellow", justify="right")
        for node in summary["nodes"]:
            table.add_row(node["name"], str(node["count"]), f"{node['avg_latency_ms']}ms")
        console.print(table)


@cli.command()
@click.option("--db",               default=None,             help="Path to logs.db")
@click.option("--output-dir",       default=".agentshrink_output", help="Where to save results")
@click.option("--no-llm-labels",    is_flag=True, default=False, help="Use heuristic labels (saves ~$0.01)")
@click.option("--skip-eval",        is_flag=True, default=False, help="Only cluster, skip SLM evaluation")
@click.option("--min-cluster-size", default=5, type=int,      help="HDBSCAN min_cluster_size")
def analyse(db, output_dir, no_llm_labels, skip_eval, min_cluster_size):
    """[Phase 2+3] Cluster captured calls and generate Replaceability Report."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    output_path = pathlib.Path(output_dir)
    db_path = pathlib.Path(db).expanduser() if db else None

    console.print(Panel.fit(
        "[bold]AgentShrink — Analysis Pipeline[/bold]\n"
        "curate → cluster → evaluate → report",
        border_style="blue"
    ))

    # Step 1: Curate
    console.print("\n[bold]Step 1/4[/bold] Curating logs...")
    from agentshrink.curator import DataCurator, CuratorConfig
    curator = DataCurator(db_path=db_path, config=CuratorConfig())
    try:
        df, embeddings = curator.curate(source="db")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if len(df) < 20:
        console.print(f"[red]Only {len(df)} entries after curation — need 20+.[/red]")
        sys.exit(1)
    console.print(f"  [green]✓[/green] {len(df)} clean entries")

    # Step 2: Cluster
    console.print("\n[bold]Step 2/4[/bold] Discovering task clusters...")
    from agentshrink.clusterer import TaskClusterer, ClusterConfig
    clusterer = TaskClusterer(config=ClusterConfig(
        min_cluster_size=min_cluster_size,
        umap_n_neighbours=min(10, len(df) - 1),
    ))

    with console.status("UMAP + HDBSCAN running..."):
        cluster_result = clusterer.fit(df, embeddings, use_llm_labels=not no_llm_labels)

    if cluster_result["n_clusters"] == 0:
        console.print(f"[red]0 clusters found. Try: --min-cluster-size 3[/red]")
        sys.exit(1)

    console.print(f"  [green]✓[/green] Found {cluster_result['n_clusters']} clusters:")
    for cid, info in cluster_result["cluster_info"].items():
        console.print(f"    {cid}: '{info['name']}' ({info['size']} entries)")

    clusterer.save_results(cluster_result, output_path)

    if skip_eval:
        console.print("\n[yellow]Skipped SLM evaluation (--skip-eval)[/yellow]")
        console.print(f"[green]✓ Results saved to {output_path}[/green]")
        return

    # Step 3: Evaluate
    console.print("\n[bold]Step 3/4[/bold] Evaluating clusters against local SLMs...")
    console.print("  [dim]Loading models one at a time — safe for 8GB RAM[/dim]")

    from agentshrink.evaluator import SLMEvaluator, EvaluatorConfig
    evaluator = SLMEvaluator(config=EvaluatorConfig(n_samples_per_cluster=20, verbose=True))

    try:
        with console.status("Evaluating... (~5-15 minutes)"):
            reports = evaluator.evaluate_all_clusters(cluster_result)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Fix: ollama serve && ollama pull gemma2:2b")
        console.print("Or skip: agentshrink analyse --skip-eval")
        sys.exit(1)

    # Step 4: Report
    console.print("\n[bold]Step 4/4[/bold] Generating report...")
    report_path = evaluator.save_report(reports, output_path)
    evaluator.print_report(reports)

    console.print(f"\n[green]✓ Report: {report_path}[/green]")
    console.print(f"Next: [bold]agentshrink shrink[/bold] (Phase 4 — coming soon)")


@cli.command()
@click.option("--apply-report", default=None)
@click.option("--dry-run", is_flag=True, default=False)
def shrink(apply_report, dry_run):
    """[Phase 4] Apply routing config — replace LLM calls with SLMs. Coming soon."""
    console.print("[yellow]Phase 4 (ShrinkLLM router) coming next.[/yellow]")


@cli.command()
def monitor():
    """[Phase 4+] Weekly quality check. Coming soon."""
    console.print("[yellow]Phase 4+ (monitor) coming next.[/yellow]")


if __name__ == "__main__":
    cli()
