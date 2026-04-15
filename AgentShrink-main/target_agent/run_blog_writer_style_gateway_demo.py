from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from target_agent.blog_writer_gateway_agent import analyze_writing_style_via_gateway


console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the blog writer style-analysis step through the AgentShrink gateway.")
    parser.add_argument(
        "--text-file",
        required=True,
        help="Path to a TXT file whose writing style should be analyzed",
    )
    args = parser.parse_args()

    text_path = Path(args.text_file)
    if not text_path.exists():
        console.print(f"[red]Text file not found:[/red] {text_path}")
        return 1

    text = text_path.read_text(encoding="utf-8")
    if not text.strip():
        console.print("[red]Text file is empty.[/red]")
        return 1

    console.print(
        Panel.fit(
            "[bold]Blog Writer Style Analysis Gateway Demo[/bold]\n"
            "Path: writing-style analysis -> AgentShrink Gateway -> configured provider",
            border_style="blue",
        )
    )

    analysis, run_id = analyze_writing_style_via_gateway(text)
    console.print(f"[bold]Run ID:[/bold] {run_id}")
    console.print_json(json.dumps(analysis, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
