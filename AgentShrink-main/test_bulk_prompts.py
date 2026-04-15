"""
Bulk Prompt Runner — Sends prompts from all Test AI Agent categories
through the AgentShrink gateway to populate dashboard data for
clustering, evaluation, and fine-tune candidate generation.

Usage:
    python test_bulk_prompts.py              # 5 prompts per agent (quick)
    python test_bulk_prompts.py --full       # all 90 prompts per agent
    python test_bulk_prompts.py --count 10   # 10 per agent
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


def parse_prompts(prompt_file: pathlib.Path) -> list[tuple[str, str]]:
    """Parse a 30-30-30 prompt file, returning (category, prompt) tuples."""
    content = prompt_file.read_text(encoding="utf-8")
    results = []
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
                results.append((current_section, prompt))
    return results


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
    parser = argparse.ArgumentParser(description="Bulk prompt runner for AgentShrink data generation")
    parser.add_argument("--full", action="store_true", help="Send all prompts (90 per agent)")
    parser.add_argument("--count", type=int, default=5, help="Prompts per agent (default: 5)")
    args = parser.parse_args()

    per_agent = 90 if args.full else args.count

    client = OpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)

    # Connectivity check
    print("=" * 70)
    print("AgentShrink — Bulk Prompt Runner")
    print(f"Gateway: {GATEWAY_URL}  |  Model: {MODEL}")
    print("=" * 70)

    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        print(f"Gateway: OK ({r.choices[0].message.content})")
    except Exception as e:
        print(f"Gateway ERROR: {e}")
        print("Start gateway first: python -m agentshrink.cli gateway --upstream-provider mock")
        sys.exit(1)

    agents = discover_agents()
    print(f"\nFound {len(agents)} agents with prompt files")

    total_sent = 0
    total_ok = 0
    total_err = 0
    all_results = []

    for agent in agents:
        prompts = parse_prompts(agent["prompt_file"])
        selected = prompts[:per_agent]

        print(f"\n{'─' * 70}")
        print(f"Agent: {agent['category']}/{agent['name']} ({len(selected)}/{len(prompts)} prompts)")

        agent_ok = 0
        agent_err = 0

        for i, (section, prompt) in enumerate(selected, 1):
            # Use different node names based on prompt category to create
            # distinct clusters that produce fine-tune candidates
            node_name = f"{agent['name']}_{section}"
            system_msg = (
                f"You are the {agent['name']} agent. "
                f"Node: {node_name}. Respond helpfully and concisely."
            )

            try:
                start = time.time()
                r = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=256,
                    temperature=0.7,
                    extra_headers={"X-Agentshrink-Node": node_name},
                )
                elapsed = time.time() - start
                content = r.choices[0].message.content or ""
                tokens = r.usage.total_tokens if r.usage else 0
                tag = section.upper().replace("_", "-")
                print(f"  [{i:2d}] OK  {elapsed:.1f}s  {tokens:4d}tok  [{tag:14s}]  {prompt[:50]}...")
                agent_ok += 1
                all_results.append({"agent": agent["name"], "section": section, "ok": True})
            except Exception as e:
                print(f"  [{i:2d}] ERR  {str(e)[:60]}")
                agent_err += 1
                all_results.append({"agent": agent["name"], "section": section, "ok": False})

            total_sent += 1

        total_ok += agent_ok
        total_err += agent_err
        print(f"  Result: {agent_ok} OK / {agent_err} ERR")

    # Summary
    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total_sent} prompts sent  |  {total_ok} OK  |  {total_err} ERR")
    print(f"\nNext steps:")
    print(f"  1. Open dashboard → Overview → click 'RUN ANALYSIS'")
    print(f"  2. Check Cluster Map for prompt groupings")
    print(f"  3. Check Fine-Tune for candidates marked 'FINE-TUNE'")
    print(f"  4. Check Report for replaceability scores")


if __name__ == "__main__":
    main()
