from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel

from target_agent.blog_writer_gateway_agent import generate_blog_post_via_gateway


console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the blog writing agent through the AgentShrink gateway.")
    parser.add_argument(
        "--topic",
        default="How small AI teams can use local model routing to cut inference costs",
        help="Blog topic to send through the gateway",
    )
    args = parser.parse_args()

    console.print(
        Panel.fit(
            "[bold]Blog Writing Agent Gateway Demo[/bold]\n"
            "Source: memory_agents/blog_writing_agent/agents.py\n"
            "Path: OpenAI client -> AgentShrink Gateway -> provider/local route",
            border_style="blue",
        )
    )

    content, run_id = generate_blog_post_via_gateway(args.topic)
    console.print(f"[bold]Topic:[/bold] {args.topic}\n")
    console.print(f"[bold]Run ID:[/bold] {run_id}")
    console.print(f"[bold]Response:[/bold] {content}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)
