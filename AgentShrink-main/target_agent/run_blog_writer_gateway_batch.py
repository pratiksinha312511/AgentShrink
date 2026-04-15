from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from target_agent.blog_writer_gateway_agent import (
    create_blog_writer_gateway_client,
    generate_blog_post_with_client,
    load_blog_topics,
)


console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Send many blog-writing prompts through AgentShrink.")
    parser.add_argument(
        "--prompts-file",
        default="target_agent/blog_writer_test_prompts_100.txt",
        help="Path to the blog topic list",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of prompts to send",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=100,
        help="How many response characters to preview per call",
    )
    args = parser.parse_args()

    topics = load_blog_topics(args.prompts_file)
    if not topics:
        console.print("[red]No topics found in the prompts file.[/red]")
        return 1

    selected_topics = topics[: max(1, args.limit)]
    batch_id = f"blog-batch-{uuid.uuid4().hex[:8]}"

    console.print(
        Panel.fit(
            "[bold]Blog Writing Agent Batch Runner[/bold]\n"
            "Source: memory_agents/blog_writing_agent/agents.py\n"
            f"Prompts file: {Path(args.prompts_file)}\n"
            f"Calls planned: {len(selected_topics)}",
            border_style="green",
        )
    )

    table = Table(title="Batch Progress")
    table.add_column("#", justify="right")
    table.add_column("Topic")
    table.add_column("Run ID")
    table.add_column("Preview")

    client, model, run_id = create_blog_writer_gateway_client(run_id=batch_id)

    for index, topic in enumerate(selected_topics, start=1):
        response = generate_blog_post_with_client(
            client,
            model,
            topic,
        )
        preview = response[: args.preview_chars].replace("\n", " ")
        table.add_row(str(index), topic, run_id, preview)
        console.print(f"[green]{index:03d}[/green] {topic}")

    console.print(table)
    console.print(f"[green]Sent {len(selected_topics)} blog prompts through AgentShrink.[/green]")
    console.print(f"[bold]Batch ID:[/bold] {batch_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)
