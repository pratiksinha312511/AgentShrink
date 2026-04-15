from __future__ import annotations

import argparse

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from target_agent.youtube_trend_gateway_agent import run_youtube_trend_gateway_demo


def main():
    parser = argparse.ArgumentParser(description="Run the YouTube trend gateway demo through AgentShrink.")
    parser.add_argument(
        "--prompt",
        default="Suggest 3 YouTube video ideas for a programming channel covering AI agents and automation.",
        help="Prompt to send through the AgentShrink gateway.",
    )
    args = parser.parse_args()

    console = Console()
    console.print(
        Panel.fit(
            "\n".join(
                [
                    "YouTube Trend Gateway Demo",
                    "Source: memory_agents/youtube_trend_agent/app.py",
                    "Path: OpenAI client -> AgentShrink Gateway -> provider/local route",
                ]
            )
        )
    )

    result, run_id = run_youtube_trend_gateway_demo(args.prompt)

    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_row("Prompt", args.prompt)
    table.add_row("Run ID", run_id)
    table.add_row("Response", result)
    console.print(table)


if __name__ == "__main__":
    main()
