"""
Finance Agent — 3 Agent Nodes via AgentShrink Gateway + Sarvam AI
=================================================================
Multi-node finance pipeline:
  1. market_analyst    — Analyzes market data and trends
  2. risk_assessor     — Evaluates risk factors
  3. portfolio_advisor — Provides investment recommendations

Usage:
    python agent.py              # Run all 90 prompts
    python agent.py --count 15   # Run first 15 prompts
"""
import argparse
import os
import pathlib
import sys
import time

from openai import OpenAI

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")
MODEL = os.getenv("AGENTSHRINK_MODEL", "sarvam-m")

PROMPT_FILE = pathlib.Path(__file__).parent / "prompts_30_30_30.txt"

NODES = {
    "market_analyst": {
        "system": (
            "You are a senior market analyst. Analyze financial topics with specific "
            "data points, price targets, and market trends. Use technical analysis "
            "terminology. Always include bull and bear cases."
        ),
        "max_tokens": 350,
    },
    "risk_assessor": {
        "system": (
            "You are a risk assessment specialist. Evaluate the financial risks "
            "with a risk matrix: likelihood (low/med/high) x impact (low/med/high). "
            "List top 3 risk factors. Be quantitative."
        ),
        "max_tokens": 200,
    },
    "portfolio_advisor": {
        "system": (
            "You are a portfolio advisor. Give a clear buy/hold/sell recommendation "
            "with a one-line rationale and suggested allocation percentage. "
            "Be concise and actionable."
        ),
        "max_tokens": 80,
    },
}

CATEGORY_PIPELINES = {
    "keep_on_llm": ["market_analyst", "risk_assessor", "portfolio_advisor"],
    "need_fine_tune": ["market_analyst", "portfolio_advisor"],
    "keep_on_slm": ["portfolio_advisor"],
}


def parse_prompts() -> list[tuple[str, str]]:
    content = PROMPT_FILE.read_text(encoding="utf-8")
    results = []
    current = None
    for line in content.splitlines():
        stripped = line.strip()
        if "KEEP ON LLM" in stripped:
            current = "keep_on_llm"
        elif "NEED FINE-TUNE" in stripped:
            current = "need_fine_tune"
        elif "KEEP ON SLM" in stripped:
            current = "keep_on_slm"
        elif current and stripped and stripped[0].isdigit() and ". " in stripped:
            prompt = stripped.split(". ", 1)[1].strip()
            if prompt:
                results.append((current, prompt))
    return results


def run_pipeline(client: OpenAI, prompt: str, pipeline: list[str]) -> dict:
    context = prompt
    results = {}
    for node_name in pipeline:
        node = NODES[node_name]
        try:
            start = time.time()
            r = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": node["system"]},
                    {"role": "user", "content": context},
                ],
                max_tokens=node["max_tokens"],
                temperature=0.7,
                extra_headers={"X-Agentshrink-Node": node_name},
            )
            elapsed = time.time() - start
            content = r.choices[0].message.content or ""
            tokens = r.usage.total_tokens if r.usage else 0
            results[node_name] = {"ok": True, "content": content, "tokens": tokens, "elapsed": elapsed}
            context = f"Original question: {prompt}\n\nPrevious analysis:\n{content}"
        except Exception as e:
            results[node_name] = {"ok": False, "error": str(e)}
            break
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=None)
    args = parser.parse_args()

    client = OpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)

    try:
        r = client.chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": "ping"}], max_tokens=5,
            extra_headers={"X-Agentshrink-Node": "finance_ping"},
        )
        print(f"Gateway OK: {r.choices[0].message.content}")
    except Exception as e:
        print(f"Gateway ERROR: {e}")
        sys.exit(1)

    prompts = parse_prompts()
    if args.count:
        prompts = prompts[:args.count]

    total_calls = sum(len(CATEGORY_PIPELINES[cat]) for cat, _ in prompts)

    print(f"\n{'=' * 70}")
    print(f"Finance Agent - 3-Node Pipeline ({len(prompts)} prompts, {total_calls} LLM calls)")
    print(f"Gateway: {GATEWAY_URL}  |  Model: {MODEL}")
    print(f"Nodes: {', '.join(NODES.keys())}")
    print(f"{'=' * 70}")

    stats = {n: 0 for n in NODES}
    stats["ok"] = 0
    stats["err"] = 0

    for i, (cat, prompt) in enumerate(prompts, 1):
        pipeline = CATEGORY_PIPELINES[cat]
        tag = cat.upper().replace("_", "-")
        print(f"\n  [{i:2d}/{len(prompts)}] [{tag}] ({len(pipeline)} nodes) {prompt[:55]}...")

        results = run_pipeline(client, prompt, pipeline)
        for node_name, result in results.items():
            if result.get("ok"):
                stats[node_name] += 1
                stats["ok"] += 1
                print(f"    > {node_name:20s}  {result['elapsed']:.1f}s  {result['tokens']:4d}tok")
            else:
                stats["err"] += 1
                print(f"    x {node_name:20s}  ERR: {result.get('error', '')[:40]}")

    print(f"\n{'=' * 70}")
    print(f"DONE: {stats['ok']} OK / {stats['err']} ERR")
    for node_name in NODES:
        print(f"  {node_name:20s}: {stats[node_name]}")


if __name__ == "__main__":
    main()
