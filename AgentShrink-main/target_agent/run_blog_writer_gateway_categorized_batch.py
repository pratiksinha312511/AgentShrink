from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from target_agent.blog_writer_gateway_agent import (
    create_blog_writer_gateway_client,
    generate_blog_post_with_client,
    load_categorized_prompts,
)


console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run categorized blog-writer prompts through AgentShrink.")
    parser.add_argument(
        "--prompts-file",
        default=r"c:\Users\DELL\Desktop\90 prompts.txt",
        help="Path to the categorized prompt file",
    )
    parser.add_argument(
        "--category",
        required=True,
        help="Category key to run, for example category_1___llm_required",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max prompts from that category to send",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=120,
        help="How many response characters to preview",
    )
    args = parser.parse_args()

    categorized = load_categorized_prompts(args.prompts_file)
    if args.category not in categorized:
        console.print("[red]Unknown category.[/red]")
        console.print("Available categories:")
        for key in categorized:
            console.print(f"  - {key}")
        return 1

    prompts = categorized[args.category][: max(1, args.limit)]
    batch_id = f"{args.category}-{uuid.uuid4().hex[:8]}"
    client, model, run_id = create_blog_writer_gateway_client(run_id=batch_id)

    console.print(
        Panel.fit(
            "[bold]Blog Writer Categorized Batch Runner[/bold]\n"
            f"Category: {args.category}\n"
            f"Prompts file: {Path(args.prompts_file)}\n"
            f"Calls planned: {len(prompts)}",
            border_style="green",
        )
    )

    table = Table(title="Prompt Progress")
    table.add_column("#", justify="right")
    table.add_column("Prompt")
    table.add_column("Preview")

    for index, prompt in enumerate(prompts, start=1):
        response = generate_blog_post_with_client(client, model, prompt)
        preview = response[: args.preview_chars].replace("\n", " ")
        table.add_row(str(index), prompt, preview)
        console.print(f"[green]{index:03d}[/green] {prompt}")

    console.print(table)
    console.print(f"[bold]Batch ID:[/bold] {batch_id}")
    console.print(f"[bold]Run ID header:[/bold] {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
