import argparse
import os

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
os.environ["TARGET_AGENT_PROVIDER"] = "shrink"
os.environ.setdefault("SHRINKLLM_FALLBACK_PROVIDER", "ollama")

from target_agent.case_agent import CASE_TEST_MESSAGES, build_case_agent


def main():
    parser = argparse.ArgumentParser(description="Run the alternate case agent with ShrinkLLM routing enabled.")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    args = parser.parse_args()

    os.environ["AGENTSHRINK_CONFIDENCE_THRESHOLD"] = str(args.confidence_threshold)
    console = Console()
    agent = build_case_agent()
    messages = CASE_TEST_MESSAGES[: args.limit]

    console.print(Panel.fit(
        "[bold]Alternate Case Agent Shrink Demo[/bold]\n"
        f"Messages: {len(messages)}\n"
        f"Confidence threshold: {args.confidence_threshold}\n"
        "This runs a second workflow shape through the same ShrinkLLM router.",
        border_style="green",
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

    console.print(Panel.fit(
        "[bold green]Alternate shrink demo complete[/bold green]\n"
        "Check Cluster Map, Report, and Live Routing for the new node names.",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
