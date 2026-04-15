from __future__ import annotations

import argparse

from rich.console import Console
from rich.panel import Panel

from target_agent.openai_sdk_gateway_basic_agent import run_gateway_demo

console = Console()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompt",
        default="Give me a balanced diet plan for an 18 year old student who wants steady energy and healthy protein intake.",
    )
    parser.add_argument("--node-name", default="openai_sdk_gateway_demo")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    console.print(
        Panel.fit(
            "[bold]OpenAI Agents SDK Gateway Demo[/bold]\n"
            "Source: starter_ai_agents/openai_agents_sdk/simple-example/basic-agent.py\n"
            "Path: Agent -> AgentShrink Gateway -> provider/local route",
            border_style="blue",
        )
    )
    console.print(f"Prompt: {args.prompt}\n")

    result, run_id = run_gateway_demo(args.prompt, node_name=args.node_name, run_id=args.run_id)
    final_output = getattr(result, "final_output", None) or str(result)

    console.print(f"[bold]Run ID:[/bold] {run_id}")
    console.print(f"[bold]Response:[/bold] {final_output}")


if __name__ == "__main__":
    main()
