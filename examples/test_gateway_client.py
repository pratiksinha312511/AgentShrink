"""Simple OpenAI-compatible client for local AgentShrink gateway testing."""

from __future__ import annotations

import argparse
from openai import OpenAI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8100/v1")
    parser.add_argument("--model", default="mock-model")
    parser.add_argument("--message", default="Classify this customer message into a short label.")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--node", default="gateway_demo_node")
    parser.add_argument("--run-id", default="gateway-demo-run")
    args = parser.parse_args()

    client = OpenAI(base_url=args.base_url, api_key="agentshrink-local")

    if args.stream:
        stream = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": args.message},
            ],
            stream=True,
            extra_headers={
                "x-agentshrink-node": args.node,
                "x-agentshrink-run-id": args.run_id,
            },
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print()
        return

    response = client.chat.completions.create(
        model=args.model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": args.message},
        ],
        extra_headers={
            "x-agentshrink-node": args.node,
            "x-agentshrink-run-id": args.run_id,
        },
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
