"""
Universal Gateway Test — Tests AgentShrink Gateway + Sarvam AI
================================================================
Uses only the openai SDK (already installed). No extra frameworks needed.
Tests all 3 prompt categories: Keep-LLM, Fine-tune, Keep-SLM.

Usage:
    python "Test AI Agents/test_gateway_sarvam.py"
    python "Test AI Agents/test_gateway_sarvam.py" --all       # run all 9 prompts
    python "Test AI Agents/test_gateway_sarvam.py" --category llm  # only LLM prompts
"""
import argparse
import os
import sys
import time
from openai import OpenAI

GATEWAY_URL = os.getenv("AGENTSHRINK_GATEWAY_URL", "http://127.0.0.1:8100/v1")
GATEWAY_KEY = os.getenv("AGENTSHRINK_GATEWAY_KEY", "as_live_33lTz9tmAWqyscwkWSOwi3TK")
MODEL = os.getenv("AGENTSHRINK_SARVAM_MODEL", "sarvam-m")

# ── Sample prompts from each category ──────────────────────────────

KEEP_ON_LLM = [
    "Analyze the top 5 HackerNews stories from today. Identify emerging technology themes connecting them and explain the investment implications in detail.",
    "Write a comprehensive comparison of NVIDIA, AMD, and Intel's AI chip strategies. Include architecture differences, performance benchmarks, and market positioning.",
    "Design a database schema for a multi-tenant SaaS application with role-based access control, audit logging, and soft deletes. Generate the complete DDL.",
]

NEED_FINE_TUNE = [
    "Summarize the top 3 AI trends from this week in 2-3 sentences each.",
    "What is the current stock price and P/E ratio of Apple (AAPL)?",
    "Write a SQL query to find the top 10 customers by total order amount.",
]

KEEP_ON_SLM = [
    "What is artificial intelligence?",
    "What does API stand for?",
    "What is a database?",
]


def test_prompt(client: OpenAI, prompt: str, category: str, index: int) -> dict:
    """Send a single prompt through the gateway and measure response."""
    print(f"\n{'─' * 60}")
    print(f"[{category}] Prompt {index}: {prompt[:80]}...")
    start = time.time()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.7,
        )
        elapsed = time.time() - start
        content = response.choices[0].message.content or ""
        tokens_used = response.usage.total_tokens if response.usage else 0
        print(f"  ✅ {elapsed:.2f}s | {tokens_used} tokens | model={response.model}")
        print(f"  Response: {content[:200]}...")
        return {"status": "ok", "time": elapsed, "tokens": tokens_used, "category": category}
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ {elapsed:.2f}s | ERROR: {e}")
        return {"status": "error", "time": elapsed, "error": str(e), "category": category}


def main():
    parser = argparse.ArgumentParser(description="Test AgentShrink Gateway + Sarvam AI")
    parser.add_argument("--all", action="store_true", help="Run all 9 sample prompts")
    parser.add_argument("--category", choices=["llm", "finetune", "slm"], help="Run only one category")
    args = parser.parse_args()

    print("=" * 60)
    print("AgentShrink Gateway + Sarvam AI — Universal Test")
    print(f"Gateway: {GATEWAY_URL}")
    print(f"Model:   {MODEL}")
    print("=" * 60)

    client = OpenAI(base_url=GATEWAY_URL, api_key=GATEWAY_KEY)

    # Quick connectivity check
    print("\n🔌 Testing gateway connectivity...")
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_tokens=10,
        )
        print(f"  ✅ Gateway is up! Response: {r.choices[0].message.content}")
    except Exception as e:
        print(f"  ❌ Gateway NOT reachable: {e}")
        print("\n💡 Start the gateway first:")
        print("   python -m agentshrink.cli gateway --upstream-provider sarvam --host 127.0.0.1 --port 8100")
        sys.exit(1)

    # Select prompts
    prompts_to_run = []
    if args.category == "llm" or args.all or not args.category:
        for i, p in enumerate(KEEP_ON_LLM[:1] if not args.all else KEEP_ON_LLM, 1):
            prompts_to_run.append(("KEEP-ON-LLM", i, p))
    if args.category == "finetune" or args.all:
        for i, p in enumerate(NEED_FINE_TUNE[:1] if not args.all else NEED_FINE_TUNE, 1):
            prompts_to_run.append(("NEED-FINE-TUNE", i, p))
    if args.category == "slm" or args.all:
        for i, p in enumerate(KEEP_ON_SLM[:1] if not args.all else KEEP_ON_SLM, 1):
            prompts_to_run.append(("KEEP-ON-SLM", i, p))
    if not args.all and not args.category:
        # Default: 1 prompt from each category
        prompts_to_run = [
            ("KEEP-ON-LLM", 1, KEEP_ON_LLM[0]),
            ("NEED-FINE-TUNE", 1, NEED_FINE_TUNE[0]),
            ("KEEP-ON-SLM", 1, KEEP_ON_SLM[0]),
        ]

    results = []
    for category, idx, prompt in prompts_to_run:
        result = test_prompt(client, prompt, category, idx)
        results.append(result)

    # Summary
    ok = [r for r in results if r["status"] == "ok"]
    fail = [r for r in results if r["status"] == "error"]
    print(f"\n{'=' * 60}")
    print(f"RESULTS: {len(ok)} passed, {len(fail)} failed out of {len(results)}")
    if ok:
        avg_time = sum(r["time"] for r in ok) / len(ok)
        total_tokens = sum(r["tokens"] for r in ok)
        print(f"Avg response time: {avg_time:.2f}s | Total tokens: {total_tokens}")
        for cat in ["KEEP-ON-LLM", "NEED-FINE-TUNE", "KEEP-ON-SLM"]:
            cat_results = [r for r in ok if r["category"] == cat]
            if cat_results:
                cat_avg = sum(r["time"] for r in cat_results) / len(cat_results)
                print(f"  {cat}: {len(cat_results)} ok, avg {cat_avg:.2f}s")
    if fail:
        print(f"\nFailed prompts:")
        for r in fail:
            print(f"  ❌ [{r['category']}] {r['error']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
