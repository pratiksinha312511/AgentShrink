from __future__ import annotations

import argparse

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from target_agent.nebius_raw_gateway_chat import GatewayStudioChat

console = Console()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--message",
        default="Suggest a healthy one-day meal plan for a college student with moderate activity.",
    )
    parser.add_argument("--node-name", default="nebius_raw_gateway_demo")
    args = parser.parse_args()

    console.print(
        Panel.fit(
            "[bold]Raw API Gateway Demo[/bold]\n"
            "Source: simple_ai_agents/nebius_chat/app.py\n"
            "Path: requests.post -> AgentShrink Gateway -> provider/local route",
            border_style="blue",
        )
    )

    client = GatewayStudioChat()
    response, error, usage = client.send_message(args.message, node_name=args.node_name)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)

    table = Table(box=None, show_header=False)
    table.add_row("Message", args.message)
    table.add_row("Response", response or "")
    table.add_row("Prompt tokens", str(usage.get("prompt_tokens", 0)))
    table.add_row("Completion tokens", str(usage.get("completion_tokens", 0)))
    console.print(table)


if __name__ == "__main__":
    main()
