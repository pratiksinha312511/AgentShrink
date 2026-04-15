"""
target_agent/demo_phase4.py
============================
PHASE 4 DEMO SCRIPT

Shows the full AgentShrink value proposition:
  BEFORE: Agent using GPT-4o for every call → expensive
  AFTER:  Same agent using ShrinkLLM → 60-75% cheaper

Run this script to see the live routing trace during your demo.

Usage:
    # Basic demo (uses fallback only — no Ollama needed)
    python target_agent/demo_phase4.py --dry-run

    # Full demo (requires Ollama + agentshrink analyse output)
    python target_agent/demo_phase4.py

    # With visible routing trace (for recruiter demo)
    python target_agent/demo_phase4.py --trace
"""

import sys
import time
import pathlib
import argparse
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich import box

console = Console()

# The 3 test messages we'll run for the demo
DEMO_MESSAGES = [
    "My order ORD-10021 arrived completely smashed. I want a full refund immediately.",
    "Where is my package? Order ORD-10045 was supposed to arrive 3 weeks ago and still nothing.",
    "I received the wrong item in order ORD-10078. Got a blue shirt instead of red.",
]


def run_before(messages: list[str]) -> dict:
    """Run agent WITHOUT AgentShrink — all calls go to GPT-4o-mini."""
    from target_agent.agent import build_agent

    console.print(Rule("[bold red]BEFORE AgentShrink[/bold red] — GPT-4o-mini for every call"))
    agent = build_agent()

    results = []
    total_start = time.perf_counter()

    for i, msg in enumerate(messages, 1):
        console.print(f"\n[dim]Message {i}:[/dim] {msg[:60]}...")
        start = time.perf_counter()

        result = agent.invoke({
            "customer_message": msg,
            "complaint_type": "", "order_id": "",
            "policy_verdict": "", "draft_reply": "",
            "final_response": {}
        })

        elapsed = (time.perf_counter() - start) * 1000
        results.append({"result": result, "latency_ms": elapsed})
        console.print(
            f"  [red]→[/red] {result['complaint_type']} | "
            f"{result['order_id']} | "
            f"{result['policy_verdict']} | "
            f"[dim]{elapsed:.0f}ms total[/dim]"
        )

    total_ms = (time.perf_counter() - total_start) * 1000
    return {"results": results, "total_ms": total_ms}


def run_after(messages: list[str], trace: bool, dry_run: bool) -> dict:
    """Run agent WITH AgentShrink — routes simple calls to local SLMs."""
    from agentshrink.shrink_llm import ShrinkLLM
    from target_agent.agent import build_agent

    output_dir = ".agentshrink_output"
    analyse_done = (pathlib.Path(output_dir) / "centroids.npy").exists()

    if not analyse_done and not dry_run:
        console.print(
            "[yellow]⚠ agentshrink analyse hasn't been run yet.[/yellow]\n"
            "Running in dry-run mode (shows routing decisions but uses API for everything).\n"
            "Run 'agentshrink analyse' to enable real local model routing."
        )
        dry_run = True

    console.print(
        Rule(
            "[bold green]AFTER AgentShrink[/bold green] — "
            f"{'DRY-RUN: ' if dry_run else ''}"
            "Simple calls → local SLMs"
        )
    )

    if trace:
        console.print("[dim]Trace mode ON — routing decisions will appear below[/dim]\n")

    # THE ONE-WORD CHANGE
    llm = ShrinkLLM(
        output_dir=output_dir,
        trace_mode=trace,
        dry_run=dry_run,
        confidence_threshold=0.70,
    )

    agent = build_agent(callbacks=[])  # Callbacks added via ShrinkLLM internally

    # Monkey-patch the agent's LLM calls to use ShrinkLLM
    # In a real project, the developer would just change ChatOpenAI → ShrinkLLM
    # in their agent.py file directly. This patching simulates that.
    from unittest.mock import patch
    with patch("target_agent.agent.get_llm", return_value=lambda callbacks=None: llm):
        from target_agent.agent import build_agent as build_shrink_agent
        shrink_agent = build_shrink_agent()

    results = []
    total_start = time.perf_counter()

    for i, msg in enumerate(messages, 1):
        console.print(f"\n[dim]Message {i}:[/dim] {msg[:60]}...")
        start = time.perf_counter()

        result = shrink_agent.invoke({
            "customer_message": msg,
            "complaint_type": "", "order_id": "",
            "policy_verdict": "", "draft_reply": "",
            "final_response": {}
        })

        elapsed = (time.perf_counter() - start) * 1000
        results.append({"result": result, "latency_ms": elapsed})
        console.print(
            f"  [green]→[/green] {result.get('complaint_type', '?')} | "
            f"{result.get('order_id', '?')} | "
            f"{result.get('policy_verdict', '?')} | "
            f"[dim]{elapsed:.0f}ms total[/dim]"
        )

    total_ms = (time.perf_counter() - total_start) * 1000
    routing_stats = llm.get_routing_stats()
    return {"results": results, "total_ms": total_ms, "routing_stats": routing_stats}


def print_comparison(before: dict, after: dict, dry_run: bool):
    """Print a side-by-side comparison of before vs after."""
    console.print()
    console.print(Rule("[bold]Results Comparison[/bold]"))

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold dim")
    table.add_column("Metric",        style="white",  min_width=22)
    table.add_column("Before",        style="red",    justify="right", min_width=18)
    table.add_column("After",         style="green",  justify="right", min_width=18)
    table.add_column("Improvement",   style="cyan",   justify="right", min_width=18)

    # Latency
    before_ms = before["total_ms"]
    after_ms  = after["total_ms"]
    latency_improvement = ((before_ms - after_ms) / before_ms * 100) if before_ms > 0 else 0

    table.add_row(
        "Total latency (3 messages)",
        f"{before_ms:.0f}ms",
        f"{after_ms:.0f}ms",
        f"{latency_improvement:.0f}% faster" if latency_improvement > 0 else "—",
    )

    # Cost estimate (GPT-4o-mini: $0.00015/1K in, $0.0006/1K out)
    # Each message = 5 calls × avg 100 tokens in + 20 tokens out
    cost_per_call_before = (100 * 0.00015 + 20 * 0.0006) / 1000  # ~$0.000027
    cost_per_message_before = cost_per_call_before * 5
    cost_3_messages_before = cost_per_message_before * 3

    if not dry_run and "routing_stats" in after:
        stats = after["routing_stats"]
        local_pct = stats.get("local_pct", 0) / 100
        cost_3_messages_after = cost_3_messages_before * (1 - local_pct)
        cost_saving_pct = local_pct * 100
    else:
        cost_3_messages_after = cost_3_messages_before
        cost_saving_pct = 0

    table.add_row(
        "Est. API cost (3 messages)",
        f"${cost_3_messages_before:.5f}",
        f"${cost_3_messages_after:.5f}",
        f"{cost_saving_pct:.0f}% saved" if cost_saving_pct > 0 else "run analyse first",
    )

    # Routing stats
    if "routing_stats" in after:
        stats = after["routing_stats"]
        table.add_row(
            "Calls routed to local SLMs",
            "0%",
            f"{stats['local_pct']:.0f}%",
            f"{stats['local_calls']} / {stats['total_calls']} calls",
        )
        table.add_row(
            "Fallback calls (API)",
            f"15 / 15 calls",
            f"{stats['fallback_calls']} / {stats['total_calls']} calls",
            f"↓ {15 - stats['fallback_calls']} fewer API calls",
        )

    console.print(table)

    if dry_run:
        console.print(
            "\n[yellow]ℹ DRY-RUN MODE:[/yellow] Routing decisions shown but all calls used API.\n"
            "To enable real local model routing:\n"
            "  1. agentshrink analyse\n"
            "  2. python target_agent/demo_phase4.py --trace\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentShrink Phase 4 Demo")
    parser.add_argument("--trace",   action="store_true", help="Show live routing trace")
    parser.add_argument("--dry-run", action="store_true", help="Use API for all calls but show routing decisions")
    parser.add_argument("--before-only", action="store_true", help="Only run the BEFORE version")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold]AgentShrink — Phase 4 Demo[/bold]\n"
        "Showing before vs after AgentShrink on a customer support agent.\n"
        "Watch how simple calls route to local SLMs automatically.",
        border_style="blue"
    ))

    before_results = run_before(DEMO_MESSAGES)

    if args.before_only:
        sys.exit(0)

    console.print()
    after_results = run_after(DEMO_MESSAGES, trace=args.trace, dry_run=args.dry_run)

    print_comparison(before_results, after_results, dry_run=args.dry_run)

    console.print(Panel.fit(
        "[bold green]Demo complete ✓[/bold green]\n\n"
        "The developer changed ONE word in their agent:\n"
        "  [red]ChatOpenAI[/red] → [green]ShrinkLLM[/green]\n\n"
        "Everything else stayed exactly the same.\n"
        "AgentShrink handled the rest automatically.",
        border_style="green"
    ))
