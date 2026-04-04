"""
Run the startup validator with ShrinkLLM enabled so Live Routing updates.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
os.environ["TARGET_AGENT_PROVIDER"] = "shrink"
os.environ.setdefault("SHRINKLLM_FALLBACK_PROVIDER", "ollama")

from target_agent.startup_validator_agent import TEST_IDEAS, build_startup_validator_agent


def _load_ideas(prompt_file: str | None):
    if not prompt_file:
        return None
    path = Path(prompt_file).expanduser()
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    ideas = [line for line in lines if line]
    if not ideas:
        raise ValueError(f"No ideas found in {path}")
    return ideas


def main():
    parser = argparse.ArgumentParser(description="Run startup validator with ShrinkLLM enabled.")
    parser.add_argument("--limit", type=int, default=3, help="How many ideas to run.")
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.55,
        help="Routing threshold for this demo.",
    )
    parser.add_argument("--prompt-file", help="Optional text file containing one startup idea per line.")
    args = parser.parse_args()

    console = Console()
    os.environ["AGENTSHRINK_CONFIDENCE_THRESHOLD"] = str(args.confidence_threshold)
    agent = build_startup_validator_agent()
    ideas = (_load_ideas(args.prompt_file) or TEST_IDEAS)[: args.limit]

    console.print(Panel.fit(
        "[bold]Startup Validator Shrink Demo[/bold]\n"
        "Provider: shrink\n"
        f"Ideas: {len(ideas)}\n"
        f"Confidence threshold: {args.confidence_threshold}\n"
        "This run should emit routing events to the dashboard live feed.",
        border_style="green",
    ))

    for i, idea in enumerate(ideas, 1):
        console.print(f"\n[bold]Idea {i}/{len(ideas)}[/bold]")
        console.print(idea)
        result = agent.invoke({
            "idea": idea,
            "clarified_idea": {},
            "market_research": {},
            "competitor_analysis": {},
            "validation_report": {},
            "final_summary": "",
        })

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim", width=22)
        table.add_column("Value", style="white")
        table.add_row("Mission", result["clarified_idea"].get("mission", "")[:90])
        table.add_row("Segments", result["market_research"].get("target_customer_segments", "")[:90])
        table.add_row("Positioning", result["competitor_analysis"].get("positioning", "")[:90])
        table.add_row("Summary", result["final_summary"][:90] + "...")
        console.print(table)

    console.print(Panel.fit(
        "[bold green]Demo complete[/bold green]\n"
        "Check the Live Routing page for startup validation routing events.",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
