"""
Targeted Prompt Runner — Generate data for Replace Now + Fine-Tune + Keep-LLM
==============================================================================
Sends prompts through the AgentShrink Sarvam gateway designed to produce
all three recommendation types after analysis + evaluation:

  - REPLACE NOW:  Simple, repetitive prompts a small model can handle
  - FINE-TUNE:    Medium complexity needing domain adaptation
  - KEEP ON API:  Complex reasoning requiring full LLM capabilities

Usage:
    python test_replace_finetune_prompts.py               # 10 prompts per category per agent (60 total per agent)
    python test_replace_finetune_prompts.py --full         # all 30 per category (90 per agent)
    python test_replace_finetune_prompts.py --count 15     # 15 per category
    python test_replace_finetune_prompts.py --agents 3     # only first 3 agents
"""
import argparse
import os
import sys
import time
import pathlib

from openai import OpenAI

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")
MODEL = os.getenv("AGENTSHRINK_MODEL", "sarvam-m")
TEST_DIR = pathlib.Path(__file__).parent / "Test AI Agents"

CATEGORIES = ["starter_agents", "simple_agents", "mcp_agents", "memory_agents", "rag_apps", "advanced_agents"]

# System prompts tuned to produce clusters with different replaceability profiles
SYSTEM_PROMPTS = {
    "keep_on_slm": (
        "You are a simple assistant. Give short, factual, one-line answers. "
        "No explanations needed. Just answer the question directly."
    ),
    "need_fine_tune": (
        "You are a domain-specific assistant. Provide structured, formatted answers "
        "with the right terminology. Follow the exact output format requested."
    ),
    "keep_on_llm": (
        "You are an expert analyst. Provide deep, multi-step reasoning with "
        "nuanced analysis, trade-offs, and comprehensive explanations."
    ),
}

# Node name suffixes to create distinct clusters per recommendation type
NODE_SUFFIXES = {
    "keep_on_slm": "simple_qa",
    "need_fine_tune": "domain_tasks",
    "keep_on_llm": "complex_reasoning",
}


def parse_prompts(prompt_file: pathlib.Path) -> dict[str, list[str]]:
    """Parse a 30-30-30 prompt file into categories."""
    content = prompt_file.read_text(encoding="utf-8")
    sections = {"keep_on_llm": [], "need_fine_tune": [], "keep_on_slm": []}
    current_section = None

    for line in content.splitlines():
        line = line.strip()
        if "KEEP ON LLM" in line:
            current_section = "keep_on_llm"
        elif "NEED FINE-TUNE" in line:
            current_section = "need_fine_tune"
        elif "KEEP ON SLM" in line:
            current_section = "keep_on_slm"
        elif current_section and line and line[0].isdigit() and ". " in line:
            prompt = line.split(". ", 1)[1].strip()
            if prompt:
                sections[current_section].append(prompt)
    return sections


def discover_agents() -> list[dict]:
    """Find all agents with prompt files."""
    agents = []
    for category in CATEGORIES:
        cat_dir = TEST_DIR / category
        if not cat_dir.exists():
            continue
        for agent_dir in sorted(cat_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            prompt_file = agent_dir / "prompts_30_30_30.txt"
            if prompt_file.exists():
                agents.append({
                    "name": agent_dir.name,
                    "category": category,
                    "prompt_file": prompt_file,
                })
    return agents


def main():
    parser = argparse.ArgumentParser(description="Targeted prompt runner for Replace/Fine-tune/Keep data")
    parser.add_argument("--full", action="store_true", help="Send all 30 prompts per category (90/agent)")
    parser.add_argument("--count", type=int, default=10, help="Prompts per category per agent (default: 10)")
    parser.add_argument("--agents", type=int, default=0, help="Limit to N agents (0 = all)")
    args = parser.parse_args()

    per_category = 30 if args.full else args.count

    client = OpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)

    print("=" * 75)
    print("AgentShrink — Targeted Prompt Runner (Replace Now + Fine-Tune + Keep)")
    print(f"Gateway: {GATEWAY_URL}  |  Model: {MODEL}")
    print(f"Per category: {per_category} prompts  |  3 categories per agent")
    print("=" * 75)

    # Connectivity check
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        print(f"Gateway: OK ({r.choices[0].message.content})\n")
    except Exception as e:
        print(f"Gateway ERROR: {e}")
        print("Start: python -m agentshrink.cli gateway --upstream-provider sarvam --host 127.0.0.1 --port 8100")
        sys.exit(1)

    agents = discover_agents()
    if args.agents > 0:
        agents = agents[:args.agents]
    print(f"Using {len(agents)} agents × {per_category} prompts × 3 categories = {len(agents) * per_category * 3} total\n")

    stats = {"total": 0, "ok": 0, "err": 0}
    section_stats = {"keep_on_slm": 0, "need_fine_tune": 0, "keep_on_llm": 0}

    for agent in agents:
        prompts_by_section = parse_prompts(agent["prompt_file"])

        print(f"{'─' * 75}")
        print(f"Agent: {agent['category']}/{agent['name']}")

        for section in ["keep_on_slm", "need_fine_tune", "keep_on_llm"]:
            prompts = prompts_by_section.get(section, [])[:per_category]
            if not prompts:
                continue

            node_name = f"{agent['name']}_{NODE_SUFFIXES[section]}"
            system_msg = SYSTEM_PROMPTS[section] + f" Agent: {agent['name']}. Node: {node_name}."
            tag = section.upper().replace("_", "-")

            for i, prompt in enumerate(prompts, 1):
                try:
                    start = time.time()
                    r = client.chat.completions.create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=300,
                        temperature=0.7,
                        extra_headers={"X-Agentshrink-Node": node_name},
                    )
                    elapsed = time.time() - start
                    tokens = r.usage.total_tokens if r.usage else 0
                    print(f"  [{tag:14s}] {i:2d}/{len(prompts)} OK  {elapsed:.1f}s  {tokens:4d}tok  {prompt[:45]}...")
                    stats["ok"] += 1
                    section_stats[section] += 1
                except Exception as e:
                    print(f"  [{tag:14s}] {i:2d}/{len(prompts)} ERR  {str(e)[:50]}")
                    stats["err"] += 1

                stats["total"] += 1

    # Summary
    print(f"\n{'=' * 75}")
    print(f"DONE: {stats['total']} prompts  |  {stats['ok']} OK  |  {stats['err']} ERR")
    print(f"\nBreakdown by expected recommendation:")
    print(f"  Keep-on-SLM  (→ Replace Now):  {section_stats['keep_on_slm']} prompts sent")
    print(f"  Fine-Tune    (→ Fine-tune):    {section_stats['need_fine_tune']} prompts sent")
    print(f"  Keep-on-LLM  (→ Keep on API):  {section_stats['keep_on_llm']} prompts sent")
    print(f"\nNext steps:")
    print(f"  1. Dashboard → Overview → RUN ANALYSIS")
    print(f"  2. Wait for clustering to complete")
    print(f"  3. Cluster Map → EVALUATE ALL (runs SLM evaluation)")
    print(f"  4. Report → check Replace Now / Fine-Tune / Keep on API counts")


if __name__ == "__main__":
    main()
