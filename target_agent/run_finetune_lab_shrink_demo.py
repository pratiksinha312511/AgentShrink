import argparse
import os

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
os.environ["TARGET_AGENT_PROVIDER"] = "shrink"
os.environ.setdefault("SHRINKLLM_FALLBACK_PROVIDER", "ollama")

from target_agent.agent import build_agent
from target_agent.finetune_lab import LAB_VERIFICATION_MESSAGES


def main():
    parser = argparse.ArgumentParser(description="Run the fine-tune lab through ShrinkLLM routing.")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--confidence-threshold", type=float, default=0.5)
    args = parser.parse_args()

    os.environ["AGENTSHRINK_CONFIDENCE_THRESHOLD"] = str(args.confidence_threshold)
    console = Console()
    agent = build_agent()
    messages = LAB_VERIFICATION_MESSAGES[: args.limit]

    console.print(Panel.fit(
        "[bold]Fine-tune Lab Shrink Demo[/bold]\n"
        f"Messages: {len(messages)}\n"
        f"Confidence threshold: {args.confidence_threshold}\n"
        "Use this after training/deployment to verify the new fine-tuned route in Live Routing.",
        border_style="green",
    ))

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

    console.print(Panel.fit(
        "[bold green]Fine-tune lab shrink demo complete[/bold green]\n"
        "Check Live Routing for customer_policy matches and the fine-tuned model route.",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
