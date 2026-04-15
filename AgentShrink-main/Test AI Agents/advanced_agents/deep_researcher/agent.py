"""
Deep Researcher Multi-Node Agent — 5 Agent Nodes via AgentShrink Gateway + Sarvam AI
=====================================================================================
Demonstrates a multi-stage research pipeline with 5 distinct agent nodes:
  1. research_planner     — Plans research strategy and subtasks
  2. web_researcher       — Gathers raw information
  3. fact_checker          — Validates claims and cross-references
  4. report_synthesizer   — Compiles findings into structured report
  5. executive_summarizer — Creates concise executive summary

Usage:
    python agent.py              # Run all 90 prompts through 5 nodes
    python agent.py --count 15   # Run first 15 prompts
    python agent.py --interactive  # Interactive mode
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

# ── 5 Agent Nodes with distinct personas ──

NODES = {
    "research_planner": {
        "system": (
            "You are a research planning specialist. Given a research topic, "
            "break it down into 3-5 focused sub-questions that need investigation. "
            "Output a numbered list of research sub-tasks. Be strategic and thorough."
        ),
        "max_tokens": 200,
    },
    "web_researcher": {
        "system": (
            "You are a web research analyst. Given a research question, provide "
            "detailed findings with specific facts, statistics, and examples. "
            "Cite your reasoning. Focus on accuracy and depth."
        ),
        "max_tokens": 400,
    },
    "fact_checker": {
        "system": (
            "You are a fact-checking specialist. Review the research findings and "
            "assess their accuracy. Flag any claims that seem dubious. Rate overall "
            "reliability on a scale of 1-5. Be skeptical but fair."
        ),
        "max_tokens": 150,
    },
    "report_synthesizer": {
        "system": (
            "You are a report writer. Synthesize research findings into a clear, "
            "well-structured report with sections: Overview, Key Findings, Analysis, "
            "and Implications. Use professional tone."
        ),
        "max_tokens": 400,
    },
    "executive_summarizer": {
        "system": (
            "You are an executive summary writer. Condense the research into a "
            "3-sentence executive summary. Be concise, highlight the single most "
            "important takeaway. Maximum 50 words."
        ),
        "max_tokens": 80,
    },
}

# Map prompt categories to different pipeline depths
CATEGORY_PIPELINES = {
    "keep_on_llm": ["research_planner", "web_researcher", "fact_checker", "report_synthesizer", "executive_summarizer"],
    "need_fine_tune": ["web_researcher", "report_synthesizer", "executive_summarizer"],
    "keep_on_slm": ["executive_summarizer"],
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
    """Run a prompt through a sequence of agent nodes."""
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


def run_batch(count: int | None = None):
    client = OpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)

    try:
        r = client.chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": "ping"}], max_tokens=5,
            extra_headers={"X-Agentshrink-Node": "deep_researcher_ping"},
        )
        print(f"Gateway OK: {r.choices[0].message.content}")
    except Exception as e:
        print(f"Gateway ERROR: {e}")
        sys.exit(1)

    prompts = parse_prompts()
    if count:
        prompts = prompts[:count]

    total_calls = sum(len(CATEGORY_PIPELINES[cat]) for cat, _ in prompts)

    print(f"\n{'=' * 70}")
    print(f"Deep Researcher - 5-Node Pipeline ({len(prompts)} prompts, {total_calls} LLM calls)")
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
                print(f"    > {node_name:25s}  {result['elapsed']:.1f}s  {result['tokens']:4d}tok")
            else:
                stats["err"] += 1
                print(f"    x {node_name:25s}  ERR: {result.get('error', '')[:40]}")

    print(f"\n{'=' * 70}")
    print(f"DONE: {stats['ok']} OK / {stats['err']} ERR")
    print(f"\nCalls per node:")
    for node_name in NODES:
        print(f"  {node_name:25s}: {stats[node_name]}")


def run_interactive():
    client = OpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)
    print("Deep Researcher (5-node pipeline). Type 'quit' to exit.")
    while True:
        prompt = input("\nResearch topic> ").strip()
        if prompt.lower() in ("quit", "exit", "q"):
            break
        results = run_pipeline(client, prompt, list(NODES.keys()))
        for node_name, result in results.items():
            if result.get("ok"):
                print(f"\n--- {node_name} ---\n{result['content']}")
            else:
                print(f"\n--- {node_name} --- ERROR: {result.get('error')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--count", type=int, default=None)
    args = parser.parse_args()

    if args.interactive:
        run_interactive()
    else:
        run_batch(args.count)
