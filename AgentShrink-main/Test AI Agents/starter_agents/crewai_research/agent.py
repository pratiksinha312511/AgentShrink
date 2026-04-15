"""
CrewAI Research Agent — 4 Agent Nodes via AgentShrink Gateway + Sarvam AI
=========================================================================
Multi-node research pipeline with 4 distinct agent personas:
  1. research_analyst    — Deep research and data gathering
  2. content_writer      — Writes structured content from research
  3. quality_reviewer    — Reviews and rates quality
  4. trend_classifier    — Classifies topics into categories

Usage:
    python agent.py              # Run all 90 prompts through 4 nodes
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

# ── 4 Agent Nodes ──

NODES = {
    "research_analyst": {
        "system": (
            "You are a senior research analyst. Investigate the topic deeply, "
            "provide specific data points, statistics, and expert opinions. "
            "Be thorough and cite specific examples."
        ),
        "max_tokens": 350,
    },
    "content_writer": {
        "system": (
            "You are a professional content writer. Take research findings and "
            "craft them into a well-structured 3-paragraph article. Use clear "
            "headers, smooth transitions, and engaging language."
        ),
        "max_tokens": 300,
    },
    "quality_reviewer": {
        "system": (
            "You are a quality reviewer. Evaluate the content for accuracy, "
            "clarity, and completeness. Give a score out of 10 and list 2-3 "
            "specific improvements needed. Be constructive."
        ),
        "max_tokens": 150,
    },
    "trend_classifier": {
        "system": (
            "You are a trend classifier. Classify the topic into one of: "
            "[Technology, Business, Science, Health, Society, Environment]. "
            "Output: Category, Confidence (high/medium/low), one-line reasoning."
        ),
        "max_tokens": 60,
    },
}

# keep_on_llm: full 4-node pipeline
# need_fine_tune: 2-node (research + writer)
# keep_on_slm: 1-node (classifier only)
CATEGORY_PIPELINES = {
    "keep_on_llm": ["research_analyst", "content_writer", "quality_reviewer", "trend_classifier"],
    "need_fine_tune": ["research_analyst", "content_writer"],
    "keep_on_slm": ["trend_classifier"],
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
            context = f"Original topic: {prompt}\n\nPrevious output:\n{content}"
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
            extra_headers={"X-Agentshrink-Node": "crewai_ping"},
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
    print(f"CrewAI Research - 4-Node Pipeline ({len(prompts)} prompts, {total_calls} LLM calls)")
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
    print(f"\nCalls per node:")
    for node_name in NODES:
        print(f"  {node_name:20s}: {stats[node_name]}")


if __name__ == "__main__":
    main()
