"""
agentshrink/evaluator.py
=========================
PHASE 3 — SLM Evaluator (Paper Section 6, Step S4)

WHAT THIS DOES:
  For each cluster found in Phase 2, this module:
  1. Samples 20 representative prompts from the cluster
  2. Runs each prompt through 3 local Ollama SLMs
  3. Scores each SLM response against the original GPT-4o response
     using LLM-as-judge (3 dimensions: correctness, format, completeness)
  4. Recommends the smallest model that achieves >= 85% quality
  5. Produces a Replaceability Report — the core output of AgentShrink

THE LLM-AS-JUDGE APPROACH:
  We can't use exact-match scoring because LLM outputs are open-ended.
  Instead, we ask GPT-4o-mini to compare the original response vs the
  SLM response on 3 dimensions and score each 1-10. This is called
  "LLM-as-judge" and is the standard technique for evaluating
  open-ended generation tasks.

  Cost: ~$0.002 per evaluation × 20 samples × 3 models × 5 clusters
        = ~$0.60 total for the full report. Very affordable.

8GB RAM STRATEGY:
  Never load two Ollama models simultaneously.
  Pipeline: load Gemma → evaluate all clusters → unload →
            load Llama → evaluate all clusters → unload →
            load Phi → evaluate all clusters → unload.
  This keeps peak memory at: OS(2GB) + Python(0.8GB) + one model(~2GB) = ~4.8GB. Safe.
"""

import time
import json
import logging
import pathlib
import numpy as np
import pandas as pd
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# MODELS TO EVALUATE
# Ordered from smallest to largest.
# We try smallest first — if it passes, we stop.
# This ensures we always recommend the most economical option.
# ─────────────────────────────────────────────

@dataclass
class SLMCandidate:
    """A local SLM candidate for evaluation."""
    ollama_name: str        # Name as used in Ollama (e.g., "gemma2:2b")
    display_name: str       # Human-readable name for the report
    ram_gb: float           # Approximate RAM usage — for 8GB safety checks
    tier: str               # "fast", "mid", or "deep"
    strengths: list[str]    # What this model is good at


# Models ordered from smallest to largest RAM usage
# For 8GB machines, we cap at phi3.5:mini (2.2GB)
SLM_CANDIDATES = [
    SLMCandidate(
        ollama_name="gemma2:2b",
        display_name="Gemma 2 2B",
        ram_gb=1.6,
        tier="fast",
        strengths=["classification", "extraction", "formatting", "simple Q&A"]
    ),
    SLMCandidate(
        ollama_name="llama3.2:3b",
        display_name="Llama 3.2 3B",
        ram_gb=2.0,
        tier="mid",
        strengths=["structured output", "routing", "medium complexity tasks"]
    ),
    SLMCandidate(
        ollama_name="phi3.5:mini",
        display_name="Phi-3.5 Mini 3.8B",
        ram_gb=2.2,
        tier="deep",
        strengths=["reasoning", "coding", "complex analysis", "longer context"]
    ),
]


# ─────────────────────────────────────────────
# RECOMMENDATION TYPES
# ─────────────────────────────────────────────

class Recommendation(Enum):
    REPLACE_NOW   = "replace_now"    # SLM quality >= threshold, swap immediately
    FINE_TUNE     = "fine_tune"      # Quality 60-85%, fine-tuning will get it there
    KEEP_LLM      = "keep_llm"       # Quality < 60%, this task needs the big model


@dataclass
class ClusterEvalResult:
    """Evaluation result for a single cluster against a single SLM."""
    cluster_id:         int
    cluster_name:       str
    slm_name:           str
    slm_display:        str

    # Quality scores (0.0 to 1.0)
    correctness_score:  float     # Is the answer factually/semantically correct?
    format_score:       float     # Does it match the expected output format?
    completeness_score: float     # Is anything important missing?
    composite_score:    float     # Weighted average of the three

    # Sample results for the report
    n_evaluated:        int       # How many prompts were evaluated
    sample_comparisons: list[dict]  # A few side-by-side examples

    # Performance
    avg_latency_ms:     float
    p95_latency_ms:     float     # 95th percentile — shows worst-case performance


@dataclass
class ClusterReport:
    """Full report for one cluster — best SLM recommendation + all scores."""
    cluster_id:         int
    cluster_name:       str
    cluster_size:       int
    node_distribution:  dict      # Which agent nodes populate this cluster

    # All evaluations for this cluster
    evaluations:        list[ClusterEvalResult]

    # Final recommendation
    recommendation:     Recommendation
    best_slm:           Optional[str]    # Ollama name of recommended model (None if keep LLM)
    best_slm_display:   Optional[str]    # Human-readable name
    best_score:         float
    estimated_cost_saving_pct: float     # % cost reduction if this cluster is replaced

    # Fine-tuning needed?
    needs_fine_tuning:  bool
    fine_tune_base_model: Optional[str]  # Which model to fine-tune if needed


@dataclass
class EvaluatorConfig:
    """Controls evaluation behaviour."""
    n_samples_per_cluster:  int   = 20    # Prompts to evaluate per cluster
    quality_threshold:      float = 0.85  # >= this → replace now
    fine_tune_threshold:    float = 0.60  # >= this → fine-tune recommended, < this → keep LLM
    judge_model:            str   = "gpt-4o-mini"  # Cheapest capable judge
    max_ram_gb:             float = 6.0   # Max RAM for models (leave 2GB for OS+Python)
    ollama_timeout_s:       int   = 60    # Timeout per model call
    verbose:                bool  = True


# ─────────────────────────────────────────────
# THE LLM-AS-JUDGE PROMPT
# This is the most important prompt in Phase 3.
# It must be precise and consistent to produce reliable scores.
# ─────────────────────────────────────────────

JUDGE_SYSTEM_PROMPT = """You are an AI quality evaluator. Compare two responses to the same prompt and score the CANDIDATE response relative to the REFERENCE response.

Score on three dimensions from 1-10:
- correctness: Does the candidate convey the same factual/semantic content as the reference?
- format: Does the candidate match the structural format of the reference (JSON, single word, paragraph, etc.)?
- completeness: Does the candidate include all important information from the reference?

IMPORTANT RULES:
- Score 10 = candidate is identical or better than reference
- Score 7-9 = candidate is slightly different but functionally equivalent
- Score 4-6 = candidate is partially correct but missing something important
- Score 1-3 = candidate is significantly wrong or in wrong format
- If the task is classification or extraction, format compliance is critical (score 1 if wrong format)
- Ignore minor stylistic differences — focus on functional equivalence

Respond with ONLY a JSON object, no explanation:
{"correctness": <1-10>, "format": <1-10>, "completeness": <1-10>}"""


# ─────────────────────────────────────────────
# OLLAMA CLIENT WRAPPER
# Handles model loading, inference, and safe unloading
# With explicit memory management for 8GB machines
# ─────────────────────────────────────────────

class OllamaRunner:
    """
    Wrapper around the Ollama Python client with memory safety for 8GB RAM.

    Key feature: load_model() and unload_model() explicitly manage
    which model is in memory. Never loads two models simultaneously.
    """

    def __init__(self, config: EvaluatorConfig):
        self.config = config
        self._current_model: Optional[str] = None

    def is_ollama_running(self) -> bool:
        """Check if Ollama server is running before attempting any calls."""
        try:
            import ollama
            ollama.list()
            return True
        except Exception:
            return False

    def is_model_available(self, model_name: str) -> bool:
        """Check if a model has been pulled and is available locally."""
        try:
            import ollama
            models = ollama.list()
            available = [m.model for m in models.models]
            # Check for exact match or prefix match (e.g., "gemma2:2b" in "gemma2:2b-instruct")
            return any(model_name in m or m in model_name for m in available)
        except Exception:
            return False

    def load_model(self, model_name: str) -> bool:
        """
        Pre-load a model into memory.

        For 8GB RAM: this is critical. We explicitly unload the previous
        model before loading the next one.

        Returns True if successful, False if model not available.
        """
        if not self.is_model_available(model_name):
            logger.warning(
                f"Model '{model_name}' not found. "
                f"Run: ollama pull {model_name}"
            )
            return False

        # Unload previous model first (8GB safety)
        if self._current_model and self._current_model != model_name:
            self.unload_model(self._current_model)

        # Warm up the model with a tiny test call
        # This loads it into RAM before the actual evaluation
        try:
            import ollama
            ollama.generate(model=model_name, prompt="hi", options={"num_predict": 1})
            self._current_model = model_name
            logger.info(f"Model '{model_name}' loaded and ready")
            return True
        except Exception as e:
            logger.error(f"Failed to load model '{model_name}': {e}")
            return False

    def unload_model(self, model_name: str):
        """
        Explicitly unload a model from RAM.

        Ollama keeps models warm by default. We force unload by setting
        keep_alive=0 on a dummy call. Critical for 8GB machines.
        """
        try:
            import ollama
            # keep_alive=0 tells Ollama to immediately unload after this call
            ollama.generate(
                model=model_name,
                prompt="",
                keep_alive=0,
                options={"num_predict": 0}
            )
            self._current_model = None
            logger.info(f"Model '{model_name}' unloaded from RAM")
            time.sleep(2)  # Give OS time to reclaim memory
        except Exception as e:
            logger.debug(f"Unload attempt for '{model_name}': {e}")

    def generate(self, model_name: str, prompt: str) -> tuple[str, float]:
        """
        Run a single inference. Returns (response_text, latency_ms).

        Uses options to keep responses focused:
        - num_predict: max tokens to generate
        - temperature: 0 for deterministic (consistent evaluation)
        """
        import ollama

        start = time.perf_counter()
        try:
            response = ollama.generate(
                model=model_name,
                prompt=prompt,
                options={
                    "temperature": 0,
                    "num_predict": 256,    # Enough for most agentic task outputs
                    "top_p": 0.9,
                },
                keep_alive="5m",           # Keep warm between evaluations
            )
            latency_ms = (time.perf_counter() - start) * 1000
            return response.response.strip(), latency_ms

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error(f"Ollama generation failed for {model_name}: {e}")
            return "", latency_ms


# ─────────────────────────────────────────────
# THE EVALUATOR CLASS
# ─────────────────────────────────────────────

class SLMEvaluator:
    """
    Evaluates each cluster against candidate SLMs and produces
    the Replaceability Report — the core output of AgentShrink.

    Usage:
        evaluator = SLMEvaluator()
        report = evaluator.evaluate_all_clusters(cluster_result)
        evaluator.save_report(report, output_dir)
    """

    def __init__(self, config: Optional[EvaluatorConfig] = None):
        self.config = config or EvaluatorConfig()
        self.runner = OllamaRunner(self.config)

    def _get_judge_llm(self):
        """Get the judge LLM (GPT-4o-mini)."""
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.config.judge_model,
            temperature=0,
        )

    def _judge_response(
        self,
        prompt:    str,
        reference: str,
        candidate: str,
        judge_llm
    ) -> dict[str, float]:
        """
        Use LLM-as-judge to score the candidate response against the reference.

        Returns dict with correctness, format, completeness scores (0.0 to 1.0).
        Falls back to {"correctness": 0.5, "format": 0.5, "completeness": 0.5}
        if the judge call fails.
        """
        from langchain_core.messages import SystemMessage, HumanMessage

        judge_prompt = f"""PROMPT given to both models:
{prompt[:500]}

REFERENCE response (from GPT-4o):
{reference[:300]}

CANDIDATE response (from local SLM):
{candidate[:300]}

Score the CANDIDATE against the REFERENCE."""

        try:
            messages = [
                SystemMessage(content=JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=judge_prompt)
            ]
            response = judge_llm.invoke(messages)
            raw = response.content.strip()

            # Parse JSON response
            # Handle case where model wraps in markdown code blocks
            if "```" in raw:
                raw = raw.split("```")[1].replace("json", "").strip()

            scores_raw = json.loads(raw)
            return {
                "correctness":  min(max(float(scores_raw.get("correctness",  5)) / 10, 0.0), 1.0),
                "format":       min(max(float(scores_raw.get("format",       5)) / 10, 0.0), 1.0),
                "completeness": min(max(float(scores_raw.get("completeness", 5)) / 10, 0.0), 1.0),
            }

        except Exception as e:
            logger.warning(f"Judge scoring failed: {e}. Using default 0.5 scores.")
            return {"correctness": 0.5, "format": 0.5, "completeness": 0.5}

    def _compute_composite_score(self, scores: dict[str, float]) -> float:
        """
        Compute a single composite quality score from the 3 dimensions.

        Weights:
        - format (40%): Most important for agentic tasks. If the SLM outputs
          "approved" when GPT-4o outputs "approved", that's fine. If it outputs
          "Yes, I think this should be approved because..." that breaks the agent.
        - correctness (40%): The semantic content must be right.
        - completeness (20%): Less critical — partial answers often still work.
        """
        return (
            scores["correctness"]  * 0.40 +
            scores["format"]       * 0.40 +
            scores["completeness"] * 0.20
        )

    def evaluate_cluster_with_model(
        self,
        cluster_id:   int,
        cluster_name: str,
        cluster_df:   pd.DataFrame,
        slm:          SLMCandidate,
        judge_llm,
    ) -> ClusterEvalResult:
        """
        Evaluate one cluster against one SLM.

        Samples up to n_samples_per_cluster prompts,
        runs each through the SLM, judges each response,
        and returns aggregated scores.
        """
        # Sample prompts from this cluster
        n_samples = min(self.config.n_samples_per_cluster, len(cluster_df))
        sample_df = cluster_df.sample(n=n_samples, random_state=42)

        all_correctness  = []
        all_format       = []
        all_completeness = []
        all_latencies    = []
        sample_comparisons = []

        for i, (_, row) in enumerate(sample_df.iterrows()):
            prompt   = row["prompt"]
            reference = row.get("response", "")

            if not prompt or not reference:
                continue

            # Run SLM inference
            candidate, latency_ms = self.runner.generate(slm.ollama_name, prompt)

            if not candidate:
                # Model failed — treat as worst score
                all_correctness.append(0.1)
                all_format.append(0.1)
                all_completeness.append(0.1)
                all_latencies.append(latency_ms)
                continue

            # Judge the response
            scores = self._judge_response(prompt, reference, candidate, judge_llm)

            all_correctness.append(scores["correctness"])
            all_format.append(scores["format"])
            all_completeness.append(scores["completeness"])
            all_latencies.append(latency_ms)

            # Store first 3 comparisons as examples for the report
            if len(sample_comparisons) < 3:
                sample_comparisons.append({
                    "prompt":     prompt[:150],
                    "reference":  reference[:200],
                    "candidate":  candidate[:200],
                    "scores":     scores,
                    "composite":  self._compute_composite_score(scores),
                })

            if self.config.verbose and i % 5 == 0:
                composite = self._compute_composite_score(scores)
                logger.info(
                    f"  {slm.display_name} on '{cluster_name}' "
                    f"sample {i+1}/{n_samples}: "
                    f"composite={composite:.2f}, latency={latency_ms:.0f}ms"
                )

        if not all_correctness:
            # No valid evaluations — return worst scores
            return ClusterEvalResult(
                cluster_id=cluster_id, cluster_name=cluster_name,
                slm_name=slm.ollama_name, slm_display=slm.display_name,
                correctness_score=0.0, format_score=0.0,
                completeness_score=0.0, composite_score=0.0,
                n_evaluated=0, sample_comparisons=[],
                avg_latency_ms=0.0, p95_latency_ms=0.0,
            )

        avg_correctness  = sum(all_correctness)  / len(all_correctness)
        avg_format       = sum(all_format)        / len(all_format)
        avg_completeness = sum(all_completeness)  / len(all_completeness)
        composite        = self._compute_composite_score({
            "correctness":  avg_correctness,
            "format":       avg_format,
            "completeness": avg_completeness,
        })

        latencies_sorted = sorted(all_latencies)
        p95_idx = int(len(latencies_sorted) * 0.95)
        p95_latency = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)]

        return ClusterEvalResult(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            slm_name=slm.ollama_name,
            slm_display=slm.display_name,
            correctness_score=round(avg_correctness, 3),
            format_score=round(avg_format, 3),
            completeness_score=round(avg_completeness, 3),
            composite_score=round(composite, 3),
            n_evaluated=len(all_correctness),
            sample_comparisons=sample_comparisons,
            avg_latency_ms=round(sum(all_latencies) / len(all_latencies), 1),
            p95_latency_ms=round(p95_latency, 1),
        )

    def _make_recommendation(
        self,
        cluster_id:        int,
        cluster_name:      str,
        cluster_size:      int,
        node_distribution: dict,
        evaluations:       list[ClusterEvalResult],
        cluster_cost_info: dict,
    ) -> ClusterReport:
        """
        Given all SLM evaluations for a cluster, make the final recommendation.

        Logic:
        1. Find the smallest SLM that achieves >= quality_threshold (85%)
           → Recommend REPLACE_NOW
        2. If no SLM passes, check if any reached >= fine_tune_threshold (60%)
           → Recommend FINE_TUNE (the best candidate)
        3. If nothing is promising
           → Recommend KEEP_LLM
        """
        # Sort evaluations from smallest model to largest (we prefer smallest)
        tier_order = {"fast": 0, "mid": 1, "deep": 2}
        slm_by_tier = {c.ollama_name: tier_order.get(c.tier, 99) for c in SLM_CANDIDATES}
        sorted_evals = sorted(
            evaluations,
            key=lambda e: slm_by_tier.get(e.slm_name, 99)
        )

        # Calculate estimated cost saving (assuming local SLMs are free)
        # avg_cost_usd per call × cluster_size gives total cost
        avg_cost_per_call = cluster_cost_info.get("avg_cost_usd", 0.001)
        total_cluster_cost = avg_cost_per_call * cluster_size

        best_eval = None
        recommendation = Recommendation.KEEP_LLM

        for eval_result in sorted_evals:
            if eval_result.composite_score >= self.config.quality_threshold:
                # This SLM passes the bar — recommend it
                best_eval = eval_result
                recommendation = Recommendation.REPLACE_NOW
                break

        if recommendation == Recommendation.KEEP_LLM:
            # No model passed — check if fine-tuning is worth it
            # Pick the best-scoring model as the fine-tune candidate
            best_candidate = max(sorted_evals, key=lambda e: e.composite_score)
            if best_candidate.composite_score >= self.config.fine_tune_threshold:
                best_eval = best_candidate
                recommendation = Recommendation.FINE_TUNE

        # Determine fine-tune base model
        fine_tune_base = None
        needs_fine_tuning = recommendation == Recommendation.FINE_TUNE
        if needs_fine_tuning and best_eval:
            # Fine-tune the model that came closest to the threshold
            fine_tune_base = best_eval.slm_name

        return ClusterReport(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            cluster_size=cluster_size,
            node_distribution=node_distribution,
            evaluations=evaluations,
            recommendation=recommendation,
            best_slm=best_eval.slm_name if best_eval else None,
            best_slm_display=best_eval.slm_display if best_eval else None,
            best_score=round(best_eval.composite_score, 3) if best_eval else 0.0,
            estimated_cost_saving_pct=round(
                (total_cluster_cost / (total_cluster_cost + 0.0001)) * 100, 1
            ) if recommendation != Recommendation.KEEP_LLM else 0.0,
            needs_fine_tuning=needs_fine_tuning,
            fine_tune_base_model=fine_tune_base,
        )

    def evaluate_all_clusters(
        self,
        cluster_result: dict,
        skip_unavailable_models: bool = True,
    ) -> list[ClusterReport]:
        """
        Main method: evaluate ALL clusters against ALL SLMs.

        Memory strategy for 8GB:
        - Outer loop: iterate over SLMs (load once per model)
        - Inner loop: evaluate all clusters with that model
        - Unload model before loading next
        This means each model is loaded ONCE, not once-per-cluster.

        Returns a list of ClusterReport objects (one per cluster).
        """
        if not self.runner.is_ollama_running():
            raise RuntimeError(
                "Ollama is not running! Start it with: ollama serve\n"
                "Then pull models: ollama pull gemma2:2b"
            )

        cluster_info  = cluster_result["cluster_info"]
        clustered_df  = cluster_result["df"]
        judge_llm     = self._get_judge_llm()

        # Determine which SLMs to evaluate based on RAM constraints
        available_slms = []
        for slm in SLM_CANDIDATES:
            if slm.ram_gb <= self.config.max_ram_gb:
                if self.runner.is_model_available(slm.ollama_name):
                    available_slms.append(slm)
                elif not skip_unavailable_models:
                    logger.warning(
                        f"Model '{slm.ollama_name}' not pulled. "
                        f"Skipping. Run: ollama pull {slm.ollama_name}"
                    )
            else:
                logger.info(
                    f"Skipping '{slm.display_name}' — "
                    f"too large for {self.config.max_ram_gb}GB RAM limit"
                )

        if not available_slms:
            raise RuntimeError(
                "No SLM candidates available. Pull at least one model:\n"
                "  ollama pull gemma2:2b\n"
                "  ollama pull llama3.2:3b\n"
                "  ollama pull phi3.5:mini"
            )

        logger.info(
            f"Evaluating {len(cluster_info)} clusters "
            f"against {len(available_slms)} SLMs..."
        )

        # Collect all evaluations per cluster
        # Structure: {cluster_id: [ClusterEvalResult, ...]}
        all_cluster_evals: dict[int, list[ClusterEvalResult]] = {
            cid: [] for cid in cluster_info.keys()
        }

        # ── OUTER LOOP: one model at a time (memory safety) ──
        for slm in available_slms:
            logger.info(f"\n{'='*50}")
            logger.info(f"Evaluating with: {slm.display_name} ({slm.ollama_name})")
            logger.info(f"RAM estimate: {slm.ram_gb}GB")
            logger.info(f"{'='*50}")

            # Load this model
            if not self.runner.load_model(slm.ollama_name):
                logger.warning(f"Failed to load {slm.ollama_name} — skipping")
                continue

            # ── INNER LOOP: all clusters with this model ──
            for cluster_id, info in cluster_info.items():
                cluster_name = info["name"]
                cluster_size = info["size"]

                logger.info(
                    f"  Cluster '{cluster_name}' "
                    f"({cluster_size} entries)..."
                )

                # Get rows belonging to this cluster
                cluster_mask = clustered_df["cluster_id"] == cluster_id
                cluster_df   = clustered_df[cluster_mask]

                if len(cluster_df) == 0:
                    logger.warning(f"  Cluster {cluster_id} is empty — skipping")
                    continue

                eval_result = self.evaluate_cluster_with_model(
                    cluster_id=cluster_id,
                    cluster_name=cluster_name,
                    cluster_df=cluster_df,
                    slm=slm,
                    judge_llm=judge_llm,
                )
                all_cluster_evals[cluster_id].append(eval_result)

                logger.info(
                    f"  → {slm.display_name}: "
                    f"composite={eval_result.composite_score:.2f}, "
                    f"avg_latency={eval_result.avg_latency_ms:.0f}ms"
                )

            # Unload model before loading next — 8GB safety
            logger.info(f"Unloading {slm.display_name}...")
            self.runner.unload_model(slm.ollama_name)

        # Build final recommendations for each cluster
        cluster_reports = []
        for cluster_id, info in cluster_info.items():
            evals = all_cluster_evals.get(cluster_id, [])

            if not evals:
                logger.warning(f"No evaluations for cluster {cluster_id} — skipping")
                continue

            report = self._make_recommendation(
                cluster_id=cluster_id,
                cluster_name=info["name"],
                cluster_size=info["size"],
                node_distribution=info.get("node_distribution", {}),
                evaluations=evals,
                cluster_cost_info={"avg_cost_usd": info.get("avg_cost_usd", 0.001)},
            )
            cluster_reports.append(report)

        # Sort: REPLACE_NOW first, then FINE_TUNE, then KEEP_LLM
        priority = {
            Recommendation.REPLACE_NOW: 0,
            Recommendation.FINE_TUNE:   1,
            Recommendation.KEEP_LLM:    2,
        }
        cluster_reports.sort(key=lambda r: priority[r.recommendation])

        return cluster_reports

    def save_report(
        self,
        reports: list[ClusterReport],
        output_dir: pathlib.Path
    ):
        """Save the Replaceability Report to JSON and print summary."""
        output_dir = pathlib.Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build serialisable report
        report_data = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": self._compute_summary(reports),
            "clusters": []
        }

        for r in reports:
            cluster_data = {
                "cluster_id":       r.cluster_id,
                "cluster_name":     r.cluster_name,
                "cluster_size":     r.cluster_size,
                "recommendation":   r.recommendation.value,
                "best_slm":         r.best_slm,
                "best_slm_display": r.best_slm_display,
                "best_score":       r.best_score,
                "needs_fine_tuning": r.needs_fine_tuning,
                "fine_tune_base_model": r.fine_tune_base_model,
                "estimated_cost_saving_pct": r.estimated_cost_saving_pct,
                "node_distribution": r.node_distribution,
                "evaluations": [
                    {
                        "slm_name":          e.slm_name,
                        "slm_display":       e.slm_display,
                        "correctness_score": e.correctness_score,
                        "format_score":      e.format_score,
                        "completeness_score": e.completeness_score,
                        "composite_score":   e.composite_score,
                        "avg_latency_ms":    e.avg_latency_ms,
                        "p95_latency_ms":    e.p95_latency_ms,
                        "n_evaluated":       e.n_evaluated,
                        "sample_comparisons": e.sample_comparisons[:2],  # Keep 2 examples
                    }
                    for e in r.evaluations
                ]
            }
            report_data["clusters"].append(cluster_data)

        report_path = output_dir / "replaceability_report.json"
        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2)

        logger.info(f"Report saved to {report_path}")
        return report_path

    def _compute_summary(self, reports: list[ClusterReport]) -> dict:
        """Compute summary statistics for the full report."""
        replace_now   = [r for r in reports if r.recommendation == Recommendation.REPLACE_NOW]
        fine_tune     = [r for r in reports if r.recommendation == Recommendation.FINE_TUNE]
        keep_llm      = [r for r in reports if r.recommendation == Recommendation.KEEP_LLM]

        total_clusters  = len(reports)
        total_size      = sum(r.cluster_size for r in reports)
        replaceable_size = sum(r.cluster_size for r in replace_now)
        finetune_size    = sum(r.cluster_size for r in fine_tune)

        pct_replaceable_now = round(replaceable_size / total_size * 100, 1) if total_size > 0 else 0
        pct_with_finetune   = round((replaceable_size + finetune_size) / total_size * 100, 1) if total_size > 0 else 0

        return {
            "total_clusters":            total_clusters,
            "replace_now_count":         len(replace_now),
            "fine_tune_count":           len(fine_tune),
            "keep_llm_count":            len(keep_llm),
            "pct_calls_replaceable_now": pct_replaceable_now,
            "pct_calls_replaceable_with_finetune": pct_with_finetune,
            "models_evaluated":          list({e.slm_name for r in reports for e in r.evaluations}),
        }

    def print_report(self, reports: list[ClusterReport]):
        """Print a rich formatted report to the terminal."""
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich import box

        console = Console()
        summary = self._compute_summary(reports)

        console.print(Panel.fit(
            f"[bold]AgentShrink — Replaceability Report[/bold]\n\n"
            f"  Replace now:   [green]{summary['replace_now_count']} clusters[/green] "
            f"({summary['pct_calls_replaceable_now']}% of calls)\n"
            f"  Fine-tune:     [yellow]{summary['fine_tune_count']} clusters[/yellow]\n"
            f"  Keep on LLM:   [red]{summary['keep_llm_count']} clusters[/red]\n\n"
            f"  Total replaceable (with fine-tune): "
            f"[bold cyan]{summary['pct_calls_replaceable_with_finetune']}%[/bold cyan] of calls",
            border_style="green"
        ))

        table = Table(
            title="Cluster Replaceability Report",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold dim"
        )
        table.add_column("Cluster",     style="white",  min_width=22)
        table.add_column("Best SLM",    style="cyan",   min_width=18)
        table.add_column("Quality",     justify="right")
        table.add_column("Latency",     justify="right")
        table.add_column("Action",      min_width=14)

        action_styles = {
            Recommendation.REPLACE_NOW: ("[green]Replace now ✓[/green]", "green"),
            Recommendation.FINE_TUNE:   ("[yellow]Fine-tune[/yellow]",   "yellow"),
            Recommendation.KEEP_LLM:    ("[red]Keep on LLM[/red]",       "red"),
        }

        for r in reports:
            action_text, _ = action_styles[r.recommendation]
            best_eval = next(
                (e for e in r.evaluations if e.slm_name == r.best_slm), None
            )
            latency_str = f"{best_eval.avg_latency_ms:.0f}ms" if best_eval else "—"

            table.add_row(
                r.cluster_name,
                r.best_slm_display or "—",
                f"{r.best_score:.0%}" if r.best_score > 0 else "—",
                latency_str,
                action_text,
            )

        console.print(table)
