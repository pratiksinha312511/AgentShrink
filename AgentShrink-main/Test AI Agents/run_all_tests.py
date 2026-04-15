"""
Master Test Runner — Run all adapted agents through AgentShrink + Sarvam AI
============================================================================
Usage:
    python run_all_tests.py                  # Run all agents
    python run_all_tests.py --category starter   # Run only starter agents
    python run_all_tests.py --agent agno_hackernews  # Run specific agent
    python run_all_tests.py --prompts-only       # Just validate prompt files
"""
import argparse
import json
import os
import sys
import pathlib
from datetime import datetime

TEST_DIR = pathlib.Path(__file__).parent
GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")

AGENT_REGISTRY = {
    "starter_agents": {
        "agno_hackernews": {"framework": "Agno", "method": "Gateway"},
        "openai_sdk_email": {"framework": "OpenAI Agents SDK", "method": "Gateway + wrap"},
        "crewai_research": {"framework": "CrewAI", "method": "Gateway"},
        "pydantic_weather": {"framework": "PydanticAI", "method": "Gateway"},
        "dspy_starter": {"framework": "DSPy", "method": "Gateway"},
        "llamaindex_tasks": {"framework": "LlamaIndex", "method": "Gateway"},
    },
    "simple_agents": {
        "finance_agent": {"framework": "Agno + YFinance", "method": "Gateway"},
        "browser_agent": {"framework": "browser-use + ChatOpenAI", "method": "Gateway / ShrinkLLM"},
        "talk_to_db": {"framework": "LangChain + GibsonAI", "method": "ShrinkLLM / Gateway"},
    },
    "mcp_agents": {
        "langgraph_mcp": {"framework": "LangChain ReAct + MCP", "method": "ShrinkLLM / Gateway"},
    },
    "memory_agents": {
        "agno_memory": {"framework": "Agno + Memory", "method": "Gateway"},
    },
    "rag_apps": {
        "agentic_rag": {"framework": "Agno + RAG", "method": "Gateway"},
    },
    "advanced_agents": {
        "deep_researcher": {"framework": "Agno + ScrapeGraph", "method": "Gateway"},
    },
}


def parse_prompts(prompt_file: pathlib.Path) -> dict:
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


def validate_prompt_files():
    """Validate all prompt files have 30-30-30 structure."""
    results = []
    for category, agents in AGENT_REGISTRY.items():
        for agent_name, info in agents.items():
            prompt_file = TEST_DIR / category / agent_name / "prompts_30_30_30.txt"
            if not prompt_file.exists():
                results.append({"agent": agent_name, "status": "MISSING", "counts": {}})
                continue
            prompts = parse_prompts(prompt_file)
            counts = {k: len(v) for k, v in prompts.items()}
            status = "OK" if all(c == 30 for c in counts.values()) else "INCOMPLETE"
            results.append({"agent": agent_name, "status": status, "counts": counts})
    return results


def print_summary():
    """Print a summary of all test agents and their prompt counts."""
    print("=" * 80)
    print("AgentShrink + Sarvam AI — Test Agent Summary")
    print(f"Gateway: {GATEWAY_URL}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    total_agents = 0
    total_prompts = 0

    for category, agents in AGENT_REGISTRY.items():
        print(f"\n📁 {category}/")
        for agent_name, info in agents.items():
            prompt_file = TEST_DIR / category / agent_name / "prompts_30_30_30.txt"
            if prompt_file.exists():
                prompts = parse_prompts(prompt_file)
                count = sum(len(v) for v in prompts.values())
                total_prompts += count
                print(f"  ✅ {agent_name:25s} | {info['framework']:25s} | {count} prompts")
            else:
                print(f"  ❌ {agent_name:25s} | {info['framework']:25s} | NO PROMPTS")
            total_agents += 1

    print(f"\n{'=' * 80}")
    print(f"Total: {total_agents} test agents, {total_prompts} prompts")
    print(f"Prompt split: ~{total_prompts // 3} Keep-LLM + ~{total_prompts // 3} Fine-tune + ~{total_prompts // 3} Keep-SLM")

    print(f"\n📊 Prompt Validation:")
    for result in validate_prompt_files():
        icon = "✅" if result["status"] == "OK" else "⚠️" if result["status"] == "INCOMPLETE" else "❌"
        counts_str = ", ".join(f"{k}={v}" for k, v in result["counts"].items()) if result["counts"] else "—"
        print(f"  {icon} {result['agent']:25s} [{result['status']}] {counts_str}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentShrink Test Runner")
    parser.add_argument("--category", help="Run only this category")
    parser.add_argument("--agent", help="Run only this agent")
    parser.add_argument("--prompts-only", action="store_true", help="Only validate prompt files")
    args = parser.parse_args()

    if args.prompts_only:
        print_summary()
    else:
        print_summary()
        print("\n⚡ To run an agent test:")
        print("  1. Start gateway:  python -m agentshrink.cli gateway --upstream-provider sarvam")
        print("  2. Run agent:      python Test\\ AI\\ Agents/starter_agents/agno_hackernews/agent.py")
