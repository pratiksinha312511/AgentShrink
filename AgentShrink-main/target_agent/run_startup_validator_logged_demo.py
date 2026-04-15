"""
Run the startup validator agent with AgentShrinkLogger attached.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

from agentshrink import AgentShrinkLogger
from target_agent.agent import _target_agent_model, _target_agent_provider
from target_agent.startup_validator_agent import TEST_IDEAS, build_startup_validator_agent


def _load_ideas(prompt_file: Optional[str]):
    if not prompt_file:
        return TEST_IDEAS
    path = Path(prompt_file).expanduser()
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    ideas = [line for line in lines if line]
    if not ideas:
        raise ValueError(f"No ideas found in {path}")
    return ideas


def _preview(value, limit: int = 90) -> str:
    if isinstance(value, list):
        text = "; ".join(str(item) for item in value)
    else:
        text = str(value)
    return text[:limit]


def main():
    parser = argparse.ArgumentParser(description="Run the startup validator with AgentShrink logging enabled.")
    parser.add_argument("--prompt-file", help="Optional text file containing one startup idea per line.")
    args = parser.parse_args()

    console = Console()
    provider = _target_agent_provider()
    model = _target_agent_model(provider)
    ideas = _load_ideas(args.prompt_file)
    logger = AgentShrinkLogger()
    agent = build_startup_validator_agent(callbacks=[logger])

    console.print(Panel.fit(
        "[bold]Startup Validator Logged Demo[/bold]\n"
        f"Provider: {provider} ({model})\n"
        "Logger: enabled\n"
        f"Ideas to run: {len(ideas)}\n"
        "This run will populate ~/.agentshrink/logs.db for the dashboard.",
        border_style="blue",
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
        table.add_row("Mission", _preview(result["clarified_idea"].get("mission", "")))
        table.add_row("Segments", _preview(result["market_research"].get("target_customer_segments", "")))
        table.add_row("Positioning", _preview(result["competitor_analysis"].get("positioning", "")))
        table.add_row("Summary", _preview(result["final_summary"]) + "...")
        console.print(table)

    summary = logger.get_summary()
    console.print(Panel.fit(
        "[bold green]Logged run complete[/bold green]\n"
        f"Total calls captured: {summary.get('total_calls', 0)}\n"
        f"Database: {summary.get('db_path', 'unknown')}",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
