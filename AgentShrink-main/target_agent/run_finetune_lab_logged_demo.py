import argparse
import os

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
os.environ["TARGET_AGENT_PROVIDER"] = "ollama"

from agentshrink import AgentShrinkLogger
from target_agent.agent import build_agent
from target_agent.finetune_lab import generate_finetune_lab_messages


def main():
    parser = argparse.ArgumentParser(description="Run a larger, fine-tune-focused logging demo.")
    parser.add_argument("--count", type=int, default=72)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    console = Console()
    messages = generate_finetune_lab_messages(args.count)

    console.print(Panel.fit(
        "[bold]Fine-tune Lab Logged Demo[/bold]\n"
        f"Messages: {len(messages)}\n"
        f"Provider: {os.getenv('TARGET_AGENT_PROVIDER', 'ollama')}\n"
        "This run is designed to create a clear fine-tune candidate for the dashboard.",
        border_style="blue",
    ))

    if args.preview:
        for idx, message in enumerate(messages[:12], 1):
            console.print(f"{idx}. {message}")
        return

    logger = AgentShrinkLogger()
    agent = build_agent(callbacks=[logger])

    for idx, message in enumerate(messages, 1):
        console.print(f"\n[bold]Message {idx}/{len(messages)}[/bold]")
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
        "[bold green]Fine-tune lab logging complete[/bold green]\n"
        f"Total calls captured: {summary.get('total_calls', 0)}\n"
        f"Database: {summary.get('db_path', 'unknown')}",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
