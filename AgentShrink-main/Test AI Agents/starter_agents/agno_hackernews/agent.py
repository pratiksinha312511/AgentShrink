"""
Agno HackerNews Agent — Adapted for AgentShrink Gateway + Sarvam AI
Original: awesome-ai-apps/starter_ai_agents/agno_starter/main.py

Modes:
  python agent.py              # Batch-run all 90 prompts (populates dashboard)
  python agent.py --interactive  # Interactive chat mode
  python agent.py --count 10    # Run first N prompts only
"""
import argparse
import os
import pathlib
import sys
import time
from datetime import datetime

from openai import OpenAI

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")
MODEL = os.getenv("AGENTSHRINK_MODEL", "sarvam-m")

PROMPT_FILE = pathlib.Path(__file__).parent / "prompts_30_30_30.txt"

# ── System prompts per category (distinct node names for clustering) ──

SYSTEM_PROMPTS = {
    "keep_on_llm": (
        "You are a senior HackerNews analyst performing deep multi-step analysis. "
        "Node: hackernews_deep_analysis. Provide thorough, well-reasoned responses."
    ),
    "need_fine_tune": (
        "You are a HackerNews summarizer that extracts and organizes information. "
        "Node: hackernews_summarizer. Provide concise, structured summaries."
    ),
    "keep_on_slm": (
        "You are a simple HackerNews FAQ bot. "
        "Node: hackernews_faq. Answer briefly in 1-2 sentences."
    ),
}


def parse_prompts() -> list[tuple[str, str]]:
    """Parse prompts file into (category, prompt) tuples."""
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


def run_batch(count: int | None = None):
    """Send prompts through the gateway in batch mode."""
    client = OpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)

    # Connectivity check
    try:
        r = client.chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": "ping"}], max_tokens=5,
        )
        print(f"Gateway OK: {r.choices[0].message.content}")
    except Exception as e:
        print(f"Gateway ERROR: {e}")
        print("Start gateway: python -m agentshrink.cli stack up")
        sys.exit(1)

    prompts = parse_prompts()
    if count:
        prompts = prompts[:count]

    print(f"\n{'=' * 65}")
    print(f"Agno HackerNews Agent — Batch Run ({len(prompts)} prompts)")
    print(f"Gateway: {GATEWAY_URL}  |  Model: {MODEL}")
    print(f"{'=' * 65}")

    stats = {"keep_on_llm": 0, "need_fine_tune": 0, "keep_on_slm": 0, "ok": 0, "err": 0}

    for i, (cat, prompt) in enumerate(prompts, 1):
        sys_msg = SYSTEM_PROMPTS[cat]
        tag = cat.upper().replace("_", "-")
        try:
            start = time.time()
            # Extract node name from system prompt
            hn_node = "hackernews_deep_analysis" if cat == "keep_on_llm" else "hackernews_summarizer" if cat == "need_fine_tune" else "hackernews_faq"
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0.7,
                extra_headers={"X-Agentshrink-Node": hn_node},
            )
            elapsed = time.time() - start
            tokens = resp.usage.total_tokens if resp.usage else 0
            print(f"  [{i:2d}/{len(prompts)}] OK  {elapsed:.1f}s  {tokens:4d}tok  [{tag:14s}]  {prompt[:55]}...")
            stats[cat] += 1
            stats["ok"] += 1
        except Exception as e:
            print(f"  [{i:2d}/{len(prompts)}] ERR [{tag:14s}]  {str(e)[:50]}")
            stats["err"] += 1

    print(f"\n{'=' * 65}")
    print(f"DONE: {stats['ok']} OK / {stats['err']} ERR")
    print(f"  LLM:       {stats['keep_on_llm']}")
    print(f"  Fine-tune: {stats['need_fine_tune']}")
    print(f"  SLM:       {stats['keep_on_slm']}")
    print(f"\nNow go to http://localhost:3000 -> Overview -> RUN ANALYSIS")
    print(f"Then check Fine-Tune page for candidates.")


def run_interactive():
    """Interactive chat mode (requires agno package)."""
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.tools.hackernews import HackerNewsTools

    agent = Agent(
        name="Tech News Analyst",
        instructions=[
            "You are an intelligent HackerNews analyst and tech news curator. "
            "Analyze content, provide summaries, and make connections between stories."
        ],
        tools=[HackerNewsTools()],
        show_tool_calls=True,
        model=OpenAIChat(id=MODEL, base_url=GATEWAY_URL, api_key=GATEWAY_KEY),
        markdown=True,
    )
    print("Tech News Analyst (AgentShrink Gateway) — type 'exit' to quit")
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() == "exit":
            break
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}]")
        agent.print_response(user_input)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agno HackerNews Agent")
    parser.add_argument("--interactive", action="store_true", help="Interactive chat mode (needs agno)")
    parser.add_argument("--count", type=int, help="Number of prompts to run (default: all 90)")
    args = parser.parse_args()

    if args.interactive:
        run_interactive()
    else:
        run_batch(args.count)
