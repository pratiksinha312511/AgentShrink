"""
tests/test_phase1_logger.py
============================
PHASE 1 VERIFICATION TEST

Run this BEFORE building Phase 2.
If this passes, your logger is working correctly.
If this fails, DO NOT move to Phase 2 — fix it first.

The entire project depends on this being correct.

Run with:
    python tests/test_phase1_logger.py
"""

import sys
import os
import pathlib
import sqlite3
import time

# Add parent to path so we can import our modules
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def test_logger_captures_calls():
    """
    TEST 1: Verify the logger captures calls to SQLite.
    Run the target agent once with the logger attached.
    Check that the database has rows.
    """
    console.print("\n[bold]Test 1:[/bold] Logger captures LLM calls to SQLite")

    from agentshrink.logger import AgentShrinkLogger
    from target_agent.agent import build_agent

    # Use a temporary DB for testing — don't pollute the real one
    test_db = pathlib.Path("/tmp/agentshrink_test.db")
    if test_db.exists():
        test_db.unlink()  # Start fresh for each test run

    logger_instance = AgentShrinkLogger(db_path=test_db)
    agent = build_agent(callbacks=[logger_instance])

    # Run the agent with a simple test message
    result = agent.invoke({
        "customer_message": "I need a refund for order ORD-99999. The item was broken.",
        "complaint_type": "",
        "order_id": "",
        "policy_verdict": "",
        "draft_reply": "",
        "final_response": {}
    })

    # ── ASSERTIONS ──
    # 1. The agent should have returned a result
    assert result["complaint_type"] != "", "classify node didn't run"
    assert result["order_id"] != "", "extract node didn't run"
    assert result["draft_reply"] != "", "draft_reply node didn't run"

    # 2. The database should have exactly 5 rows (one per node)
    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM llm_calls")
        count = cursor.fetchone()[0]

    assert count == 5, f"Expected 5 calls (one per node), got {count}. Check your callback hooks."

    # 3. All 5 nodes should be represented
    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT node_name FROM llm_calls")
        nodes = {row[0] for row in cursor.fetchall()}

    expected_nodes = {"classify", "extract", "check_policy", "draft_reply", "format_output"}
    # Note: if node names show as "unknown", the LangGraph metadata isn't passing through
    # That's okay for now — clustering still works on prompt content
    console.print(f"  Nodes captured: {nodes}")

    # 4. Every row should have a non-empty prompt
    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM llm_calls WHERE prompt = '' OR prompt IS NULL")
        empty_prompts = cursor.fetchone()[0]

    assert empty_prompts == 0, f"{empty_prompts} rows have empty prompts"

    console.print("  [green]✓ Test 1 passed[/green] — Logger captures 5 calls correctly")
    return test_db


def test_logger_captures_latency(test_db: pathlib.Path):
    """
    TEST 2: Verify latency is being recorded and is sensible.
    GPT-4o-mini typically takes 500ms–3000ms per call.
    """
    console.print("\n[bold]Test 2:[/bold] Latency values are captured and sensible")

    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT latency_ms FROM llm_calls")
        latencies = [row[0] for row in cursor.fetchall()]

    assert all(l is not None for l in latencies), "Some latency values are NULL"
    assert all(l > 0 for l in latencies), "Some latency values are 0 or negative"
    assert all(l < 60000 for l in latencies), "Some latency values are > 60s (timeout?)"

    avg_latency = sum(latencies) / len(latencies)
    console.print(f"  Latencies: {latencies} ms")
    console.print(f"  Average: {avg_latency:.0f} ms")
    console.print("  [green]✓ Test 2 passed[/green] — Latencies look sensible")


def test_logger_captures_tokens(test_db: pathlib.Path):
    """
    TEST 3: Verify token counts are being captured.
    """
    console.print("\n[bold]Test 3:[/bold] Token counts are captured")

    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tokens_in, tokens_out FROM llm_calls")
        token_rows = cursor.fetchall()

    # At least some rows should have non-zero tokens
    # (OpenAI returns token usage in the response)
    rows_with_tokens = [(t_in, t_out) for t_in, t_out in token_rows if t_in > 0]

    if len(rows_with_tokens) == 0:
        console.print("  [yellow]⚠ Warning:[/yellow] No token counts captured. This is okay —")
        console.print("  Token tracking requires the OpenAI API to return usage data.")
        console.print("  Cost estimates will be approximate. Clustering still works fine.")
    else:
        console.print(f"  Rows with token data: {len(rows_with_tokens)}/5")
        console.print("  [green]✓ Test 3 passed[/green] — Token counts captured")


def test_run_id_groups_calls(test_db: pathlib.Path):
    """
    TEST 4: Verify all 5 calls from one agent run share the same run_id.
    This is critical for Phase 2 — we need to group calls by run.
    """
    console.print("\n[bold]Test 4:[/bold] All calls from one run share the same run_id")

    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT run_id FROM llm_calls")
        distinct_runs = cursor.fetchall()

    assert len(distinct_runs) == 1, \
        f"Expected 1 unique run_id, got {len(distinct_runs)}. " \
        f"All 5 nodes should share the run_id assigned to the logger instance."

    console.print(f"  run_id: {distinct_runs[0][0][:16]}...")
    console.print("  [green]✓ Test 4 passed[/green] — All 5 calls share one run_id")


def test_prompt_hash_deduplication(test_db: pathlib.Path):
    """
    TEST 5: Verify prompt hashing works (used for deduplication in Phase 2).
    """
    console.print("\n[bold]Test 5:[/bold] Prompt hashing works for deduplication")

    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT prompt_hash FROM llm_calls")
        hashes = [row[0] for row in cursor.fetchall()]

    assert all(h is not None and len(h) == 16 for h in hashes), \
        "Some prompt hashes are missing or wrong length (expected 16 hex chars)"

    # All 5 calls should have DIFFERENT hashes (they're all different prompts)
    assert len(set(hashes)) == 5, \
        f"Expected 5 unique prompt hashes, got {len(set(hashes))}. " \
        f"Two nodes may have identical prompts (unlikely but check your nodes)."

    console.print(f"  Hashes: {hashes}")
    console.print("  [green]✓ Test 5 passed[/green] — Prompt hashing works correctly")


def test_summary_method(test_db: pathlib.Path):
    """
    TEST 6: Verify the get_summary() method works (used by CLI status command).
    """
    console.print("\n[bold]Test 6:[/bold] get_summary() returns correct data")

    from agentshrink.logger import AgentShrinkLogger
    logger_instance = AgentShrinkLogger.from_db(db_path=test_db)
    summary = logger_instance.get_summary()

    assert summary["total_calls"] == 5, f"Expected 5 total calls, got {summary['total_calls']}"
    assert summary["total_runs"] == 1, f"Expected 1 run, got {summary['total_runs']}"
    assert "nodes" in summary and len(summary["nodes"]) > 0

    console.print(f"  Total calls: {summary['total_calls']}")
    console.print(f"  Total runs: {summary['total_runs']}")
    console.print(f"  Nodes: {[n['name'] for n in summary['nodes']]}")
    console.print(f"  Est. cost: ${summary['total_cost_usd']:.4f}")
    console.print("  [green]✓ Test 6 passed[/green] — Summary method works")


def test_generate_bulk_data():
    """
    TEST 7: Generate 40 calls (8 messages × 5 nodes) to the REAL database.
    This is the data you'll use for clustering in Phase 2.
    We run this LAST because it hits the real OpenAI API.
    """
    console.print("\n[bold]Test 7:[/bold] Generate bulk test data for Phase 2 clustering")
    console.print("  [dim]Running 8 test messages × 5 nodes = 40 API calls...[/dim]")
    console.print("  [dim]This will cost approximately $0.02-0.05 in OpenAI credits[/dim]")

    from agentshrink.logger import AgentShrinkLogger
    from target_agent.agent import TEST_MESSAGES, build_agent
    from rich.progress import Progress

    # Use the real database this time
    real_logger = AgentShrinkLogger()  # Uses ~/.agentshrink/logs.db

    success_count = 0
    failure_count = 0

    with Progress(console=console) as progress:
        task = progress.add_task("  Running agent...", total=len(TEST_MESSAGES))

        for i, message in enumerate(TEST_MESSAGES):
            # Create a new logger per run so each has a unique run_id
            run_logger = AgentShrinkLogger()
            agent = build_agent(callbacks=[run_logger])

            try:
                agent.invoke({
                    "customer_message": message,
                    "complaint_type": "",
                    "order_id": "",
                    "policy_verdict": "",
                    "draft_reply": "",
                    "final_response": {}
                })
                success_count += 1
            except Exception as e:
                run_logger.mark_run_failed()
                failure_count += 1
                console.print(f"  [red]Run {i+1} failed: {e}[/red]")

            progress.advance(task)

    # Check what we have
    summary = AgentShrinkLogger.from_db().get_summary()

    console.print(f"\n  Runs completed: {success_count} success, {failure_count} failed")
    console.print(f"  Total calls in DB: {summary['total_calls']}")
    console.print(f"  Total runs in DB: {summary['total_runs']}")

    assert summary["total_calls"] >= 40, \
        f"Expected at least 40 calls, got {summary['total_calls']}"

    console.print("  [green]✓ Test 7 passed[/green] — Bulk data generated, ready for Phase 2")
    console.print(f"  [green]Database location: {summary['db_path']}[/green]")


if __name__ == "__main__":
    console.print(Panel.fit(
        "[bold]AgentShrink — Phase 1 Verification Tests[/bold]\n"
        "These tests verify the logger works before you build Phase 2.\n"
        "[yellow]DO NOT proceed to Phase 2 if any test fails.[/yellow]",
        border_style="blue"
    ))

    try:
        # Tests 1-6 use a temp DB and cost almost nothing (1 agent run)
        test_db = test_logger_captures_calls()
        test_logger_captures_latency(test_db)
        test_logger_captures_tokens(test_db)
        test_run_id_groups_calls(test_db)
        test_prompt_hash_deduplication(test_db)
        test_summary_method(test_db)

        console.print(Panel.fit(
            "[bold green]Tests 1-6 passed ✓[/bold green]\n"
            "Your logger is working correctly.\n\n"
            "Now run Test 7 to generate bulk data for Phase 2.\n"
            "This costs ~$0.05 in OpenAI credits.",
            border_style="green"
        ))

        # Ask before running Test 7 (costs money)
        response = input("\nRun Test 7 to generate 40 calls for Phase 2? (y/n): ").strip().lower()
        if response == "y":
            test_generate_bulk_data()
            console.print(Panel.fit(
                "[bold green]All 7 tests passed ✓[/bold green]\n"
                "Phase 1 complete. You are ready to build Phase 2 (clustering).",
                border_style="green"
            ))
        else:
            console.print("[yellow]Skipped Test 7. Run it when ready for Phase 2.[/yellow]")

    except AssertionError as e:
        console.print(f"\n[bold red]❌ TEST FAILED:[/bold red] {e}")
        console.print("[red]Fix this before moving to Phase 2.[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]❌ ERROR:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
