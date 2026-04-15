import argparse
import itertools
import os
import sys

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()


PROMPTS = [
    (
        "classify_customer_message",
        "Classify this customer message as billing, shipping, refund, or general inquiry: My order arrived late and I want a refund.",
    ),
    (
        "extract_order_id",
        "Extract the order ID from this support ticket: Hello team, my order ORD-10452 has not arrived yet.",
    ),
    (
        "format_json_output",
        "Convert this support response into compact JSON with keys status, priority, and reply: status resolved, priority low, reply Your replacement has shipped.",
    ),
    (
        "draft_support_reply",
        "Write a short friendly support reply for a customer asking where their package is.",
    ),
    (
        "check_support_policy",
        "Check whether this request follows refund policy: Customer asks for refund after 45 days without defect.",
    ),
]


def main():
    parser = argparse.ArgumentParser(description="Send free mock traffic through the AgentShrink gateway.")
    parser.add_argument("--count", type=int, default=30, help="Number of mock calls to send")
    parser.add_argument("--base-url", default=os.getenv("AGENTSHRINK_GATEWAY_BASE_URL", "http://127.0.0.1:8152/v1"))
    parser.add_argument("--model", default=os.getenv("AGENTSHRINK_GATEWAY_MODEL", "mock-model"))
    parser.add_argument("--api-key", default=os.getenv("AGENTSHRINK_GATEWAY_API_KEY", "agentshrink-local"))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    chat_url = args.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
    }

    console.print(
        Panel.fit(
            "[bold]AgentShrink Mock Traffic Generator[/bold]\n"
            f"Gateway: {chat_url}\n"
            f"Model: {args.model}\n"
            f"Calls: {args.count}",
            border_style="blue",
        )
    )

    sent = 0
    by_node: dict[str, int] = {}

    for idx, (node, prompt) in enumerate(itertools.islice(itertools.cycle(PROMPTS), args.count), start=1):
        payload = {
            "model": args.model,
            "messages": [
                {"role": "system", "content": "You are a helpful customer support assistant."},
                {"role": "user", "content": prompt},
            ],
            "metadata": {"agentshrink_node": node},
        }
        response = requests.post(chat_url, headers=headers, json=payload, timeout=args.timeout)
        response.raise_for_status()
        sent += 1
        by_node[node] = by_node.get(node, 0) + 1
        console.print(f"[green]{idx:02d}[/green] {node} -> {response.status_code}")

    table = Table(title="Mock Traffic Summary")
    table.add_column("Node")
    table.add_column("Calls", justify="right")
    for node, count in sorted(by_node.items()):
        table.add_row(node, str(count))
    console.print(table)
    console.print(f"[green]Sent {sent} mock calls through AgentShrink.[/green]")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
