"""
Run the target agent with AgentShrinkLogger attached.

This is the easiest way to generate real dashboard data from the demo agent
without writing custom glue code in the terminal.
"""

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentshrink import AgentShrinkLogger
from target_agent.agent import (
    TEST_MESSAGES,
    _target_agent_model,
    _target_agent_provider,
    build_agent,
)


def _load_messages(prompt_file: str | None):
    """Use built-in prompts by default, or load one prompt per line from a file."""
    if not prompt_file:
        return TEST_MESSAGES

    path = Path(prompt_file).expanduser()
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    messages = [line for line in lines if line]
    if not messages:
        raise ValueError(f"No prompts found in {path}")
    return messages


def main():
    parser = argparse.ArgumentParser(
        description="Run the target agent with AgentShrink logging enabled."
    )
    parser.add_argument(
        "--prompt-file",
        help="Optional text file containing one customer prompt per line.",
    )
    args = parser.parse_args()

    console = Console()
    provider = _target_agent_provider()
    model = _target_agent_model(provider)
    messages = _load_messages(args.prompt_file)
    logger = AgentShrinkLogger()
    agent = build_agent(callbacks=[logger])

    console.print(Panel.fit(
        "[bold]Target Agent Logged Demo[/bold]\n"
        f"Provider: {provider} ({model})\n"
        "Logger: enabled\n"
        f"Prompt source: {'custom file' if args.prompt_file else 'built-in TEST_MESSAGES'}\n"
        f"Messages to run: {len(messages)}\n"
        "This run will populate ~/.agentshrink/logs.db for the dashboard.",
        border_style="blue",
    ))

    console.print("[bold]Prompts to be tested:[/bold]")
    for i, message in enumerate(messages, 1):
        console.print(f"{i}. {message}")

    for i, message in enumerate(messages, 1):
        console.print(f"\n[bold]Message {i}/{len(messages)}[/bold]")
        console.print(message)

        result = agent.invoke({
            "customer_message": message,
            "complaint_type": "",
            "order_id": "",
            "policy_verdict": "",
            "draft_reply": "",
            "final_response": {},
        })

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim", width=18)
        table.add_column("Value", style="white")
        table.add_row("Complaint type", result["complaint_type"])
        table.add_row("Order ID", result["order_id"])
        table.add_row("Verdict", result["policy_verdict"])
        table.add_row("Reply preview", result["draft_reply"][:80] + "...")
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
