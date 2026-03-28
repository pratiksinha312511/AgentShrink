import argparse
import os

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
os.environ["TARGET_AGENT_PROVIDER"] = "ollama"

from agentshrink import AgentShrinkLogger
from target_agent.case_agent import CASE_TEST_MESSAGES, build_case_agent


def main():
    parser = argparse.ArgumentParser(description="Run the alternate case agent with logging enabled.")
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()

    console = Console()
    logger = AgentShrinkLogger()
    agent = build_case_agent(callbacks=[logger])
    messages = CASE_TEST_MESSAGES[: args.limit]

    console.print(Panel.fit(
        "[bold]Alternate Case Agent Logged Demo[/bold]\n"
        f"Messages: {len(messages)}\n"
        "This runs a different workflow shape through the same AgentShrink logger.",
        border_style="blue",
    ))

    for i, message in enumerate(messages, 1):
        console.print(f"\n[bold]Message {i}/{len(messages)}[/bold]")
        console.print(message)
        result = agent.invoke({
            "customer_message": message,
            "intent_label": "",
            "account_id": "",
            "action_plan": "",
            "internal_note": "",
            "final_packet": {},
        })
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim", width=18)
        table.add_column("Value", style="white")
        table.add_row("Intent", result["intent_label"])
        table.add_row("Identifier", result["account_id"])
        table.add_row("Action", result["action_plan"])
        table.add_row("Note", result["internal_note"][:80] + "...")
        console.print(table)

    summary = logger.get_summary()
    console.print(Panel.fit(
        "[bold green]Alternate logged run complete[/bold green]\n"
        f"Total calls captured: {summary.get('total_calls', 0)}\n"
        f"Database: {summary.get('db_path', 'unknown')}",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
