"""
Run the target agent with ShrinkLLM enabled so the Live Routing dashboard updates.

This demo now supports a policy-focused mode so we can verify whether the
customer_policy cluster is being routed to a fine-tuned model.
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
os.environ["TARGET_AGENT_PROVIDER"] = "shrink"
os.environ.setdefault("SHRINKLLM_FALLBACK_PROVIDER", "ollama")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from target_agent.agent import TEST_MESSAGES, build_agent


CUSTOMER_POLICY_MESSAGES = [
    "Carrier confirmed order ORD-31006 was lost in transit. What does policy say about refund or reship?",
    "My order ORD-31001 arrived damaged and the item inside is broken. Do I qualify for a refund?",
    "I received the wrong item for order ORD-31002. Please confirm if this is approved for refund.",
    "I changed my mind about order ORD-31003 after 10 days. Am I still eligible for a refund?",
    "I bought a digital product on order ORD-31004 and did not like it. Can I get my money back?",
    "Order ORD-31005 has been delayed for 18 days and still has not arrived. Should this be approved?",  
]


def _parse_args():
    parser = argparse.ArgumentParser(description="Run target agent with ShrinkLLM routing enabled.")
    parser.add_argument(
        "--mode",
        choices=["mixed", "customer_policy"],
        default="customer_policy",
        help="Choose which demo message set to run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=6,
        help="How many messages to run from the selected set.",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.55,
        help="Routing threshold for this demo. Lower helps debug borderline matches.",
    )
    parser.add_argument(
        "--prompt-file",
        help="Optional text file containing one customer prompt per line.",
    )
    return parser.parse_args()


def _load_messages_from_file(prompt_file: str | None):
    if not prompt_file:
        return None
    path = Path(prompt_file).expanduser()
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    messages = [line for line in lines if line]
    if not messages:
        raise ValueError(f"No prompts found in {path}")
    return messages


def _messages_for_mode(mode: str):
    if mode == "customer_policy":
        return CUSTOMER_POLICY_MESSAGES
    return TEST_MESSAGES


def main():
    args = _parse_args()
    console = Console()
    os.environ["AGENTSHRINK_CONFIDENCE_THRESHOLD"] = str(args.confidence_threshold)
    agent = build_agent()
    messages = (_load_messages_from_file(args.prompt_file) or _messages_for_mode(args.mode))[: args.limit]

    console.print(Panel.fit(
        "[bold]Target Agent Shrink Demo[/bold]\n"
        "Provider: shrink\n"
        f"Mode: {'prompt-file' if args.prompt_file else args.mode}\n"
        f"Messages: {len(messages)}\n"
        f"Confidence threshold: {args.confidence_threshold}\n"
        "This run should emit routing events to the dashboard live feed.",
        border_style="green",
    ))

    if args.prompt_file:
        console.print("[dim]Using prompts loaded from file for a larger routing test.[/dim]")
    elif args.mode == "customer_policy":
        console.print(
            "[dim]Using policy-heavy prompts so the customer_policy cluster has a better chance of matching.[/dim]"
        )

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

    console.print(Panel.fit(
        "[bold green]Demo complete[/bold green]\n"
        "Check the Live Routing page for customer_policy events and the routed model name.",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
