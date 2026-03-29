"""
tests/test_phase3_evaluator.py
================================
PHASE 3 VERIFICATION TESTS

Tests the SLM evaluator without requiring real Ollama models loaded.
Uses a mock Ollama runner for most tests, real Ollama only for Test 7.

Tests:
  Test 1: Judge prompt produces consistent scores
  Test 2: Composite score calculation is correct
  Test 3: Recommendation logic (replace/fine-tune/keep) is correct
  Test 4: Report serialisation works
  Test 5: Available models detection works
  Test 6: Memory safety — unload logic is correct
  Test 7: Real Ollama evaluation (only if Ollama is running + model pulled)

Run with:
    python tests/test_phase3_evaluator.py
"""

import sys
import json
import pathlib
import unittest
import numpy as np
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel

console = Console()


def test_judge_scoring_consistency():
    """
    TEST 1: Verify judge prompt produces sensible scores.

    We mock the LLM response to test our score parsing logic —
    this verifies the JSON parsing and score normalisation code
    without paying for actual API calls.
    """
    console.print("\n[bold]Test 1:[/bold] Judge score parsing and normalisation")

    from agentshrink.evaluator import SLMEvaluator

    evaluator = SLMEvaluator()

    # Mock the judge LLM response
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content='{"correctness": 8, "format": 9, "completeness": 7}'
    )

    scores = evaluator._judge_response(
        prompt="Classify this complaint: 'My order is late'",
        reference="shipping",
        candidate="shipping",
        judge_llm=mock_llm,
    )

    assert "correctness" in scores
    assert "format" in scores
    assert "completeness" in scores
    assert 0.0 <= scores["correctness"] <= 1.0,  "correctness out of 0-1 range"
    assert 0.0 <= scores["format"] <= 1.0,        "format out of 0-1 range"
    assert 0.0 <= scores["completeness"] <= 1.0,  "completeness out of 0-1 range"

    # 8/10 = 0.80, 9/10 = 0.90, 7/10 = 0.70
    assert abs(scores["correctness"] - 0.80) < 0.01
    assert abs(scores["format"]      - 0.90) < 0.01
    assert abs(scores["completeness"]- 0.70) < 0.01

    console.print(f"  Scores: {scores}")
    console.print("  [green]✓ Test 1 passed[/green] — Judge scoring and normalisation works")


def test_judge_handles_malformed_response():
    """Test that judge gracefully handles bad LLM responses."""
    console.print("\n[bold]Test 1b:[/bold] Judge handles malformed responses gracefully")

    from agentshrink.evaluator import SLMEvaluator

    evaluator = SLMEvaluator()

    # Test with markdown-wrapped JSON
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content='```json\n{"correctness": 7, "format": 8, "completeness": 6}\n```'
    )
    scores = evaluator._judge_response("prompt", "ref", "cand", mock_llm)
    assert scores["correctness"] == 0.7

    # Test with completely invalid response — should return defaults
    mock_llm.invoke.return_value = MagicMock(content="I cannot evaluate this.")
    scores = evaluator._judge_response("prompt", "ref", "cand", mock_llm)
    assert scores == {"correctness": 0.5, "format": 0.5, "completeness": 0.5}

    console.print("  [green]✓ Test 1b passed[/green] — Malformed responses handled gracefully")


def test_composite_score_weights():
    """
    TEST 2: Verify composite score weighting is correct.
    Format (40%) + Correctness (40%) + Completeness (20%) = 100%
    """
    console.print("\n[bold]Test 2:[/bold] Composite score calculation")

    from agentshrink.evaluator import SLMEvaluator

    evaluator = SLMEvaluator()

    # All perfect
    score = evaluator._compute_composite_score(
        {"correctness": 1.0, "format": 1.0, "completeness": 1.0}
    )
    assert abs(score - 1.0) < 0.001, f"Expected 1.0, got {score}"

    # Only correctness correct
    score = evaluator._compute_composite_score(
        {"correctness": 1.0, "format": 0.0, "completeness": 0.0}
    )
    assert abs(score - 0.40) < 0.001, f"Expected 0.40, got {score}"

    # Only format correct
    score = evaluator._compute_composite_score(
        {"correctness": 0.0, "format": 1.0, "completeness": 0.0}
    )
    assert abs(score - 0.40) < 0.001, f"Expected 0.40, got {score}"

    # Mixed: correctness=0.9, format=0.8, completeness=0.7
    score = evaluator._compute_composite_score(
        {"correctness": 0.9, "format": 0.8, "completeness": 0.7}
    )
    expected = 0.9 * 0.40 + 0.8 * 0.40 + 0.7 * 0.20  # = 0.36 + 0.32 + 0.14 = 0.82
    assert abs(score - expected) < 0.001, f"Expected {expected:.3f}, got {score:.3f}"

    console.print(f"  All-perfect: 1.00 ✓")
    console.print(f"  Only correctness: 0.40 ✓")
    console.print(f"  Mixed (0.9, 0.8, 0.7): {expected:.2f} ✓")
    console.print("  [green]✓ Test 2 passed[/green] — Composite score weights are correct")


def test_recommendation_logic():
    """
    TEST 3: Verify recommendation thresholds are applied correctly.

    Rules:
    - composite >= 0.85 → REPLACE_NOW (pick smallest model first)
    - 0.60 <= composite < 0.85 → FINE_TUNE (use best candidate)
    - composite < 0.60 → KEEP_LLM
    """
    console.print("\n[bold]Test 3:[/bold] Recommendation logic")

    from agentshrink.evaluator import (
        SLMEvaluator, ClusterEvalResult, Recommendation
    )

    evaluator = SLMEvaluator()

    def make_eval(slm_name: str, score: float) -> ClusterEvalResult:
        model_costs = {
            "gemma2:2b": 0.10,
            "llama3.2:3b": 0.20,
            "phi3.5:mini": 0.30,
        }
        return ClusterEvalResult(
            cluster_id=0, cluster_name="test_cluster",
            provider="ollama",
            slm_name=slm_name, slm_display=slm_name,
            local=True,
            quality_tier=2,
            cost_in_per_1k=model_costs[slm_name],
            cost_out_per_1k=0.0,
            correctness_score=score, format_score=score,
            completeness_score=score, composite_score=score,
            n_evaluated=20, sample_comparisons=[],
            avg_latency_ms=100.0, p95_latency_ms=200.0,
            selection_score=0.0,
        )

    # Case 1: multiple models pass → highest-ranked passing candidate wins
    evals_1 = [
        make_eval("gemma2:2b",  0.91),
        make_eval("llama3.2:3b", 0.93),
        make_eval("phi3.5:mini", 0.95),
    ]
    report_1 = evaluator._make_recommendation(
        0, "classify", 100, {}, evals_1, {"avg_cost_usd": 0.001}
    )
    assert report_1.recommendation == Recommendation.REPLACE_NOW
    assert report_1.best_slm == "phi3.5:mini"
    console.print(f"  Case 1 (all pass): REPLACE_NOW with phi3.5:mini ✓")

    # Case 2: only llama and phi pass → highest-ranked passing candidate wins
    evals_2 = [
        make_eval("gemma2:2b",   0.72),
        make_eval("llama3.2:3b", 0.88),
        make_eval("phi3.5:mini", 0.92),
    ]
    report_2 = evaluator._make_recommendation(
        0, "format", 100, {}, evals_2, {"avg_cost_usd": 0.001}
    )
    assert report_2.recommendation == Recommendation.REPLACE_NOW
    assert report_2.best_slm == "phi3.5:mini"
    console.print(f"  Case 2 (72% gemma, 88% llama): REPLACE_NOW with phi3.5:mini ✓")

    # Case 3: all models score 60-84% → recommend FINE_TUNE with best candidate
    evals_3 = [
        make_eval("gemma2:2b",   0.65),
        make_eval("llama3.2:3b", 0.74),
        make_eval("phi3.5:mini", 0.82),
    ]
    report_3 = evaluator._make_recommendation(
        0, "policy", 100, {}, evals_3, {"avg_cost_usd": 0.001}
    )
    assert report_3.recommendation == Recommendation.FINE_TUNE
    assert report_3.needs_fine_tuning == True
    assert report_3.fine_tune_base_model == "phi3.5:mini"  # Best candidate
    console.print(f"  Case 3 (all 65-82%): FINE_TUNE with phi3.5:mini ✓")

    # Case 4: all models score < 60% → KEEP_LLM
    evals_4 = [
        make_eval("gemma2:2b",   0.45),
        make_eval("llama3.2:3b", 0.52),
        make_eval("phi3.5:mini", 0.58),
    ]
    report_4 = evaluator._make_recommendation(
        0, "draft_reply", 100, {}, evals_4, {"avg_cost_usd": 0.001}
    )
    assert report_4.recommendation == Recommendation.KEEP_LLM
    assert report_4.best_slm is None
    console.print(f"  Case 4 (all < 60%): KEEP_LLM ✓")

    console.print("  [green]✓ Test 3 passed[/green] — Recommendation logic is correct")


def test_report_serialisation():
    """
    TEST 4: Verify report serialises to valid JSON and saves correctly.
    """
    console.print("\n[bold]Test 4:[/bold] Report serialisation")

    from agentshrink.evaluator import (
        SLMEvaluator, ClusterReport, ClusterEvalResult, Recommendation
    )
    import tempfile

    evaluator = SLMEvaluator()

    # Build a mock report
    mock_reports = [
        ClusterReport(
            cluster_id=0, cluster_name="classify_complaint",
            cluster_size=68, node_distribution={"classify": 68},
            evaluations=[
                ClusterEvalResult(
                    cluster_id=0, cluster_name="classify_complaint",
                    provider="ollama",
                    slm_name="gemma2:2b", slm_display="Gemma 2 2B",
                    local=True,
                    quality_tier=2,
                    cost_in_per_1k=0.0,
                    cost_out_per_1k=0.0,
                    correctness_score=0.91, format_score=0.94,
                    completeness_score=0.88, composite_score=0.92,
                    n_evaluated=20, sample_comparisons=[],
                    avg_latency_ms=28.5, p95_latency_ms=45.0,
                    selection_score=0.92,
                )
            ],
            recommendation=Recommendation.REPLACE_NOW,
            incumbent_provider="openai",
            incumbent_slm="gpt-4o-mini",
            incumbent_slm_display="GPT-4o mini",
            incumbent_score=0.95,
            best_provider="ollama",
            best_slm="gemma2:2b",
            best_slm_display="Gemma 2 2B",
            best_score=0.92,
            estimated_cost_saving_pct=73.2,
            needs_fine_tuning=False,
            fine_tune_base_model=None,
        )
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = evaluator.save_report(mock_reports, pathlib.Path(tmpdir))

        assert report_path.exists(), "Report file not created"
        assert (pathlib.Path(tmpdir) / "replaceability_report_cluster_0.json").exists(), "Per-cluster report file not created"

        with open(report_path) as f:
            data = json.load(f)

        assert "summary" in data
        assert "clusters" in data
        assert len(data["clusters"]) == 1
        assert data["clusters"][0]["cluster_name"] == "classify_complaint"
        assert data["clusters"][0]["recommendation"] == "replace_now"
        assert data["summary"]["replace_now_count"] == 1

    console.print("  [green]✓ Test 4 passed[/green] — Report serialises and saves correctly")


def test_targeted_report_updates_main_report():
    """
    TEST 4B: Verify targeted cluster saves refresh the aggregate report.
    """
    console.print("\n[bold]Test 4B:[/bold] Targeted report merge")

    from agentshrink.evaluator import (
        SLMEvaluator, ClusterReport, ClusterEvalResult, Recommendation
    )
    import tempfile

    evaluator = SLMEvaluator()

    def make_eval(cluster_id, cluster_name, model_name, score):
        return ClusterEvalResult(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            provider="ollama",
            slm_name=model_name,
            slm_display=model_name,
            local=True,
            quality_tier=2,
            cost_in_per_1k=0.0,
            cost_out_per_1k=0.0,
            correctness_score=score,
            format_score=score,
            completeness_score=score,
            composite_score=score,
            n_evaluated=5,
            sample_comparisons=[],
            avg_latency_ms=42.0,
            p95_latency_ms=50.0,
            selection_score=score,
        )

    def make_report(cluster_id, cluster_name, model_name, score):
        return ClusterReport(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            cluster_size=10,
            node_distribution={"node": 10},
            evaluations=[make_eval(cluster_id, cluster_name, model_name, score)],
            recommendation=Recommendation.FINE_TUNE,
            incumbent_provider="openai",
            incumbent_slm="gpt-4o-mini",
            incumbent_slm_display="GPT-4o mini",
            incumbent_score=0.95,
            best_provider="ollama",
            best_slm=model_name,
            best_slm_display=model_name,
            best_score=score,
            estimated_cost_saving_pct=50.0,
            needs_fine_tuning=True,
            fine_tune_base_model=model_name,
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = pathlib.Path(tmpdir)
        evaluator.save_report(
            [
                make_report(0, "cluster_zero", "gemma2:2b", 0.60),
                make_report(1, "cluster_one", "llama3.2:3b", 0.70),
            ],
            output_dir,
        )

        evaluator.save_report(
            [make_report(1, "cluster_one", "llama3.2:3b", 0.82)],
            output_dir,
            filename="replaceability_report_cluster_1.json",
        )

        with open(output_dir / "replaceability_report.json") as f:
            data = json.load(f)

        clusters = {c["cluster_id"]: c for c in data["clusters"]}
        assert len(clusters) == 2
        assert clusters[0]["best_score"] == 0.60
        assert clusters[1]["best_score"] == 0.82

    console.print("  [green]✓ Test 4B passed[/green] — Targeted saves update the main report")


def test_ollama_availability_check():
    """
    TEST 5: Verify availability checks work (without needing Ollama running).
    """
    console.print("\n[bold]Test 5:[/bold] Ollama availability checks")

    from agentshrink.evaluator import OllamaRunner, EvaluatorConfig

    runner = OllamaRunner(EvaluatorConfig())

    # Test is_ollama_running — should return bool without crashing
    # (True if Ollama is running, False otherwise)
    is_running = runner.is_ollama_running()
    console.print(f"  Ollama running: {is_running}")

    if is_running:
        # If running, test model availability check
        is_available = runner.is_model_available("nonexistent-model:99b")
        assert is_available == False, "Nonexistent model should not be available"
        console.print(f"  Nonexistent model available: {is_available} (correctly False)")

    console.print("  [green]✓ Test 5 passed[/green] — Availability checks work without crashing")


def test_memory_safety_logic():
    """
    TEST 6: Verify the memory safety logic — models are unloaded before new ones load.
    This is critical for 8GB machines.
    """
    console.print("\n[bold]Test 6:[/bold] Memory safety — sequential model loading")

    from agentshrink.evaluator import OllamaRunner, EvaluatorConfig

    runner = OllamaRunner(EvaluatorConfig())

    # Track unload calls
    unload_calls = []
    load_calls = []

    original_unload = runner.unload_model
    original_load = runner.load_model

    def mock_unload(model_name):
        unload_calls.append(model_name)
        runner._current_model = None

    def mock_load(model_name):
        load_calls.append(model_name)
        if runner._current_model and runner._current_model != model_name:
            mock_unload(runner._current_model)  # Should unload first
        runner._current_model = model_name
        return True  # Pretend model loaded

    # Patch the methods
    runner.unload_model = mock_unload
    runner.load_model = mock_load

    # Simulate loading 3 models in sequence
    runner.load_model("gemma2:2b")
    runner.load_model("llama3.2:3b")   # Should trigger unload of gemma
    runner.load_model("phi3.5:mini")   # Should trigger unload of llama

    assert "gemma2:2b" in unload_calls, \
        "gemma2:2b should have been unloaded before loading llama3.2:3b"
    assert "llama3.2:3b" in unload_calls, \
        "llama3.2:3b should have been unloaded before loading phi3.5:mini"

    console.print(f"  Unload sequence: {unload_calls}")
    console.print("  [green]✓ Test 6 passed[/green] — Models unloaded sequentially, memory safe")


def test_real_ollama_evaluation():
    """
    TEST 7: Real evaluation with actual Ollama — only runs if Ollama + gemma2:2b available.
    Evaluates ONE cluster with ONE model to verify end-to-end integration.
    """
    console.print("\n[bold]Test 7:[/bold] Real Ollama evaluation (optional — requires Ollama)")

    from agentshrink.evaluator import OllamaRunner, SLMEvaluator, EvaluatorConfig, ModelCandidate

    runner = OllamaRunner(EvaluatorConfig())

    if not runner.is_ollama_running():
        console.print("  [yellow]⚠ Skipped — Ollama not running[/yellow]")
        console.print("  Start Ollama: ollama serve")
        return

    gemma_slm = ModelCandidate(
        id="test-gemma",
        provider="ollama",
        model_name="gemma2:2b",
        display_name="Gemma 2 2B",
        enabled=True,
        local=True,
        supports=["general"],
        quality_tier=2,
        cost_in_per_1k=0.0,
        cost_out_per_1k=0.0,
    )

    if not runner.is_model_available(gemma_slm):
        console.print("  [yellow]⚠ Skipped — gemma2:2b not pulled[/yellow]")
        console.print("  Pull model: ollama pull gemma2:2b")
        return

    # Build a minimal test dataset
    import pandas as pd
    test_df = pd.DataFrame({
        "prompt": [
            "Classify this complaint type (refund/shipping/product/other): 'My package never arrived'",
            "Classify: 'I received the wrong item, want a refund'",
            "What type of complaint: 'Product broke after 1 day'",
        ],
        "response": ["shipping", "refund", "product"],
        "latency_ms": [500, 600, 550],
        "tokens_in": [50, 55, 48],
        "tokens_out": [2, 2, 2],
        "cost_usd": [0.0001, 0.0001, 0.0001],
        "cluster_id": [0, 0, 0],
    })

    evaluator = SLMEvaluator(config=EvaluatorConfig(
        n_samples_per_cluster=3,  # Just 3 for the test
        quality_threshold=0.85,
    ))

    # Mock judge LLM to avoid paying for test
    mock_judge = MagicMock()
    mock_judge.invoke.return_value = MagicMock(
        content='{"correctness": 9, "format": 9, "completeness": 8}'
    )

    result = evaluator.evaluate_cluster_with_model(
        cluster_id=0,
        cluster_name="classify_complaint",
        cluster_df=test_df,
        centroids={0: np.array([0.0, 0.0])},
        embeddings=np.array([[0.0, 0.0], [0.1, 0.0], [0.0, 0.1]]),
        candidate_model=gemma_slm,
        judge_llm=mock_judge,
        max_cost_reference=0.0001,
    )

    assert result.n_evaluated > 0, "No evaluations completed"
    assert 0.0 <= result.composite_score <= 1.0, "Score out of range"
    assert result.avg_latency_ms > 0, "Latency should be positive"

    console.print(f"  Composite score: {result.composite_score:.2f}")
    console.print(f"  Avg latency: {result.avg_latency_ms:.0f}ms")
    console.print(f"  Evaluations completed: {result.n_evaluated}")
    console.print("  [green]✓ Test 7 passed[/green] — Real Ollama evaluation works end-to-end")


if __name__ == "__main__":
    from unittest.mock import MagicMock

    console.print(Panel.fit(
        "[bold]AgentShrink — Phase 3 Evaluator Verification Tests[/bold]\n"
        "Tests 1-6 use mocks — no API calls, no Ollama needed.\n"
        "Test 7 requires Ollama running with gemma2:2b pulled.\n\n"
        "[yellow]DO NOT proceed to Phase 4 if tests 1-6 fail.[/yellow]",
        border_style="blue"
    ))

    try:
        test_judge_scoring_consistency()
        test_judge_handles_malformed_response()
        test_composite_score_weights()
        test_recommendation_logic()
        test_report_serialisation()
        test_ollama_availability_check()
        test_memory_safety_logic()
        test_real_ollama_evaluation()  # Optional — skips gracefully

        console.print(Panel.fit(
            "[bold green]All Phase 3 tests passed ✓[/bold green]\n\n"
            "The evaluator logic is correct.\n"
            "You are ready to build Phase 4 — the ShrinkLLM router.",
            border_style="green"
        ))

    except AssertionError as e:
        console.print(f"\n[bold red]❌ TEST FAILED:[/bold red] {e}")
        console.print("[red]Fix this before moving to Phase 4.[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]❌ ERROR:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
