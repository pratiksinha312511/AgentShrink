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

import hashlib
import time
import json
import logging
import pathlib
import os
import numpy as np
import pandas as pd
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

from agentshrink.model_catalog import load_model_catalog, selection_score, active_gateway_defaults
from agentshrink.provider_clients import analysis_model, analysis_provider, get_chat_model
from agentshrink.project_config import get_judge_model_id

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
@dataclass
class ModelCandidate:
    """A routing candidate from the configurable model catalog."""
    id: str
    provider: str
    model_name: str
    display_name: str
    enabled: bool
    local: bool
    supports: list[str]
    quality_tier: int
    cost_in_per_1k: float
    cost_out_per_1k: float
    candidate_enabled: bool = True
    judge_eligible: bool = True
    source: str = "user"


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
    provider:           str
    slm_name:           str
    slm_display:        str
    local:              bool
    quality_tier:       int
    cost_in_per_1k:     float
    cost_out_per_1k:    float

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
    selection_score:    float = 0.0


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
    incumbent_provider: Optional[str]
    incumbent_slm:      Optional[str]
    incumbent_slm_display: Optional[str]
    incumbent_score:    float
    best_provider:      Optional[str]
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
    central_sample_ratio:   float = 0.6   # % of samples nearest to centroid
    quality_threshold:      float = 0.85  # >= this → replace now
    fine_tune_threshold:    float = 0.60  # >= this → fine-tune recommended, < this → keep LLM
    judge_model:            str   = "gpt-4o-mini"  # Cheapest capable judge
    max_ram_gb:             float = 6.0   # Max RAM for models (leave 2GB for OS+Python)
    ollama_timeout_s:       int   = 60    # Timeout per model call
    remote_min_interval_s:  float = 0.75  # Minimum spacing between remote candidate calls
    judge_min_interval_s:   float = 1.0   # Minimum spacing between remote judge calls
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


BATCH_JUDGE_SYSTEM_PROMPT = """You are an AI quality evaluator. You will receive multiple prompt/response comparisons.

For each item, compare the CANDIDATE response relative to the REFERENCE response.

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

Respond with ONLY a JSON array, one object per item, in the same order:
[{"correctness": <1-10>, "format": <1-10>, "completeness": <1-10>}]"""


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
            if isinstance(models, dict):
                items = models.get("models", [])
                available = [
                    m.get("name") or m.get("model")
                    for m in items
                    if (m.get("name") or m.get("model"))
                ]
            else:
                items = getattr(models, "models", [])
                available = []
                for m in items:
                    name = getattr(m, "model", None) or getattr(m, "name", None)
                    if name:
                        available.append(name)
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
            if isinstance(response, dict):
                text = response.get("response", "") or ""
            else:
                text = getattr(response, "response", "") or ""
            return text.strip(), latency_ms

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error(f"Ollama generation failed for {model_name}: {e}")
            return "", latency_ms


class ProviderRunner:
    """Unified runtime wrapper for evaluating configured local and remote models."""

    def __init__(self, config: EvaluatorConfig):
        self.config = config
        self.ollama = OllamaRunner(config)
        self._clients: dict[tuple[str, str], object] = {}
        self._last_remote_call_at: dict[tuple[str, str], float] = {}

    def is_ollama_running(self) -> bool:
        return self.ollama.is_ollama_running()

    def is_model_available(self, candidate: ModelCandidate) -> bool:
        if candidate.provider == "ollama":
            return self.ollama.is_model_available(candidate.model_name)
        return True

    def load_model(self, candidate: ModelCandidate) -> bool:
        if candidate.provider == "ollama":
            return self.ollama.load_model(candidate.model_name)
        return True

    def unload_model(self, candidate: ModelCandidate):
        if candidate.provider == "ollama":
            self.ollama.unload_model(candidate.model_name)

    def generate(self, candidate: ModelCandidate, prompt: str) -> tuple[str, float]:
        if candidate.provider == "ollama":
            return self.ollama.generate(candidate.model_name, prompt)

        self._respect_remote_rate_limit(candidate)
        start = time.perf_counter()
        client = self._get_client(candidate)
        if client is None:
            return "", (time.perf_counter() - start) * 1000
        try:
            response = client.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            latency_ms = (time.perf_counter() - start) * 1000
            return (content or "").strip(), latency_ms
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error(f"{candidate.provider} generation failed for {candidate.model_name}: {e}")
            return "", latency_ms

    def _get_client(self, candidate: ModelCandidate):
        cache_key = (candidate.provider, candidate.model_name)
        if cache_key in self._clients:
            return self._clients[cache_key]

        client = None
        try:
            client = get_chat_model(
                provider=candidate.provider,
                model=candidate.model_name,
                temperature=0,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize {candidate.provider}:{candidate.model_name} for evaluation: {e}")
            client = None

        self._clients[cache_key] = client
        return client

    def _respect_remote_rate_limit(self, candidate: ModelCandidate):
        """Apply simple pacing to remote provider calls to reduce 429s."""
        if candidate.provider == "ollama":
            return
        min_interval = max(0.0, float(self.config.remote_min_interval_s))
        if min_interval <= 0:
            return
        key = (candidate.provider, candidate.model_name)
        now = time.perf_counter()
        last_called = self._last_remote_call_at.get(key)
        if last_called is not None:
            remaining = min_interval - (now - last_called)
            if remaining > 0:
                logger.info(
                    f"Rate limiting {candidate.provider}:{candidate.model_name} "
                    f"for {remaining:.2f}s before next candidate call"
                )
                time.sleep(remaining)
        self._last_remote_call_at[key] = time.perf_counter()


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
        self.runner = ProviderRunner(self.config)
        self._last_judge_call_at: Optional[float] = None

    def _get_judge_llm(self):
        """Get the configured judge LLM for analysis."""
        provider = analysis_provider()
        model = self.config.judge_model
        catalog = load_model_catalog(pathlib.Path(os.getenv("AGENTSHRINK_OUTPUT_DIR", ".agentshrink_output")))
        judge_model_id = get_judge_model_id()
        if judge_model_id:
            selected = next(
                (entry for entry in catalog.get("models", []) if entry.get("id") == judge_model_id),
                None,
            )
            if selected:
                provider = selected.get("provider", provider)
                model = selected.get("model_name", model)
        else:
            judge_candidates = [
                entry for entry in catalog.get("models", [])
                if entry.get("enabled") and entry.get("judge_eligible", True)
            ]
            selected = sorted(
                judge_candidates,
                key=lambda entry: (
                    bool(entry.get("local")),
                    -int(entry.get("quality_tier", 0) or 0),
                    entry.get("display_name", ""),
                ),
            )[0] if judge_candidates else None
            if selected:
                provider = selected.get("provider", provider)
                model = selected.get("model_name", model)
        if model == self.config.judge_model:
            model = analysis_model(provider)
        logger.info(f"Using judge model {provider}:{model}")
        return get_chat_model(
            provider=provider,
            model=model,
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

    def _judge_responses_batch(
        self,
        items: list[dict[str, str]],
        judge_llm,
    ) -> list[dict[str, float]]:
        """
        Batch-score multiple prompt/reference/candidate comparisons in one judge call.

        Returns scores in the same order as `items`.
        Falls back to neutral 0.5 scores for all items if the judge call fails.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        if not items:
            return []

        fallback = [{"correctness": 0.5, "format": 0.5, "completeness": 0.5} for _ in items]
        payload_items = []
        for idx, item in enumerate(items, start=1):
            payload_items.append({
                "index": idx,
                "prompt": (item.get("prompt", "") or "")[:500],
                "reference": (item.get("reference", "") or "")[:300],
                "candidate": (item.get("candidate", "") or "")[:300],
            })

        try:
            self._respect_judge_rate_limit()
            logger.info(f"    Judge batch scoring start: {len(items)} items")
            messages = [
                SystemMessage(content=BATCH_JUDGE_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        "Score each item and return a JSON array in the same order.\n\n"
                        f"{json.dumps(payload_items, ensure_ascii=True)}"
                    )
                ),
            ]
            response = judge_llm.invoke(messages)
            raw = response.content.strip()

            if "```" in raw:
                parts = raw.split("```")
                if len(parts) > 1:
                    raw = parts[1].replace("json", "").strip()

            parsed = json.loads(raw)
            if not isinstance(parsed, list) or len(parsed) != len(items):
                raise ValueError(
                    f"Expected JSON list of length {len(items)}, got {type(parsed).__name__} "
                    f"with length {len(parsed) if isinstance(parsed, list) else 'n/a'}"
                )

            normalized = []
            for score_obj in parsed:
                normalized.append({
                    "correctness": min(max(float(score_obj.get("correctness", 5)) / 10, 0.0), 1.0),
                    "format": min(max(float(score_obj.get("format", 5)) / 10, 0.0), 1.0),
                    "completeness": min(max(float(score_obj.get("completeness", 5)) / 10, 0.0), 1.0),
                })
            logger.info(f"    Judge batch scoring complete: {len(items)} items")
            return normalized
        except Exception as e:
            logger.warning(
                f"Batch judge scoring failed for {len(items)} items: {e}. "
                "Using default 0.5 scores."
            )
            return fallback

    def _respect_judge_rate_limit(self):
        """Apply simple pacing to the judge model to avoid bursty remote scoring calls."""
        min_interval = max(0.0, float(self.config.judge_min_interval_s))
        if min_interval <= 0:
            return
        now = time.perf_counter()
        if self._last_judge_call_at is not None:
            remaining = min_interval - (now - self._last_judge_call_at)
            if remaining > 0:
                logger.info(f"    Rate limiting judge for {remaining:.2f}s before next batch")
                time.sleep(remaining)
        self._last_judge_call_at = time.perf_counter()

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

    def _incumbent_identity(self, cluster_reference: Optional[dict] = None) -> tuple[str, str]:
        reference = cluster_reference or {}
        provider = (reference.get("provider") or "").strip().lower()
        model = (reference.get("model") or "").strip()
        if provider and model:
            return provider, model
        # Use active gateway defaults (reflects current provider config)
        try:
            gw = active_gateway_defaults()
            if gw.get("provider_id") and gw.get("gateway_model"):
                return gw["provider_id"], gw["gateway_model"]
        except Exception:
            pass
        provider = analysis_provider()
        model = analysis_model(provider)
        return provider, model

    def _to_json_safe(self, value):
        """Recursively convert numpy/pandas scalar types into plain Python JSON-safe values."""
        if isinstance(value, dict):
            return {str(k): self._to_json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._to_json_safe(v) for v in value]
        if isinstance(value, tuple):
            return [self._to_json_safe(v) for v in value]
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.bool_):
            return bool(value)
        return value

    # ── Evaluation cache ─────────────────────────────────────────────

    def _eval_cache_dir(self) -> pathlib.Path:
        output_dir = pathlib.Path(os.getenv("AGENTSHRINK_OUTPUT_DIR", ".agentshrink_output"))
        return output_dir / "evaluation_cache"

    def _eval_cache_key(self, cluster_id: int, candidate_model, sample_df: pd.DataFrame) -> str:
        prompt_blob = "|".join(sorted(sample_df["prompt"].astype(str).values))
        prompt_hash = hashlib.sha256(prompt_blob.encode()).hexdigest()[:8]
        model_name = candidate_model.model_name.replace("/", "_").replace(":", "_")
        provider = candidate_model.provider
        return f"{cluster_id}_{model_name}_{provider}_{prompt_hash}"

    def _read_eval_cache(self, cache_key: str) -> Optional[ClusterEvalResult]:
        cache_file = self._eval_cache_dir() / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
            return ClusterEvalResult(**data)
        except Exception as exc:
            logger.debug(f"Eval cache miss (corrupt): {cache_key}: {exc}")
            return None

    def _write_eval_cache(self, cache_key: str, result: ClusterEvalResult) -> None:
        try:
            cache_dir = self._eval_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            data = self._to_json_safe(asdict(result))
            with open(cache_dir / f"{cache_key}.json", "w") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            logger.debug(f"Eval cache write failed for {cache_key}: {exc}")

    def evaluate_cluster_with_model(
        self,
        cluster_id:   int,
        cluster_name: str,
        cluster_df:   pd.DataFrame,
        centroids:    dict[int, np.ndarray],
        embeddings:   np.ndarray,
        candidate_model: ModelCandidate,
        judge_llm,
        max_cost_reference: float,
    ) -> ClusterEvalResult:
        """
        Evaluate one cluster against one SLM.

        Samples up to n_samples_per_cluster prompts,
        runs each through the SLM, judges each response,
        and returns aggregated scores.
        """
        sample_df = self._select_representative_samples(
            cluster_id=cluster_id,
            cluster_df=cluster_df,
            centroids=centroids,
            embeddings=embeddings,
        )

        # Check evaluation cache
        cache_key = self._eval_cache_key(cluster_id, candidate_model, sample_df)
        cached = self._read_eval_cache(cache_key)
        if cached is not None:
            logger.info(f"    Cache hit for cluster {cluster_id} × {candidate_model.model_name}")
            return cached

        n_samples = len(sample_df)
        logger.info(
            f"    Representative sample set for '{cluster_name}': "
            f"{n_samples} prompts ({round(self.config.central_sample_ratio * 100)}% centroid-near, "
            f"{round((1 - self.config.central_sample_ratio) * 100)}% edge cases)"
        )

        all_correctness  = []
        all_format       = []
        all_completeness = []
        all_latencies    = []
        sample_comparisons = []
        judge_items: list[dict[str, str]] = []
        pending_results: list[dict[str, object]] = []

        for i, (_, row) in enumerate(sample_df.iterrows()):
            prompt   = row["prompt"]
            reference = row.get("response", "")

            if not prompt or not reference:
                continue

            # Run SLM inference
            candidate, latency_ms = self.runner.generate(candidate_model, prompt)

            if not candidate:
                # Model failed — treat as worst score
                all_correctness.append(0.1)
                all_format.append(0.1)
                all_completeness.append(0.1)
                all_latencies.append(latency_ms)
                continue

            all_latencies.append(latency_ms)
            judge_items.append({
                "prompt": prompt,
                "reference": reference,
                "candidate": candidate,
            })
            pending_results.append({
                "prompt": prompt,
                "reference": reference,
                "candidate": candidate,
                "latency_ms": latency_ms,
                "sample_idx": i + 1,
            })

        batch_scores = self._judge_responses_batch(judge_items, judge_llm)
        for result, scores in zip(pending_results, batch_scores):
            all_correctness.append(scores["correctness"])
            all_format.append(scores["format"])
            all_completeness.append(scores["completeness"])

            if len(sample_comparisons) < 3:
                sample_comparisons.append({
                    "prompt": result["prompt"][:150],
                    "reference": result["reference"][:200],
                    "candidate": result["candidate"][:200],
                    "scores": scores,
                    "composite": self._compute_composite_score(scores),
                })

            if self.config.verbose and (int(result["sample_idx"]) - 1) % 5 == 0:
                composite = self._compute_composite_score(scores)
                logger.info(
                    f"  {candidate_model.display_name} on '{cluster_name}' "
                    f"sample {result['sample_idx']}/{n_samples}: "
                    f"composite={composite:.2f}, latency={float(result['latency_ms']):.0f}ms"
                )

        if not all_correctness:
            # No valid evaluations — return worst scores
            return ClusterEvalResult(
                cluster_id=cluster_id, cluster_name=cluster_name,
                provider=candidate_model.provider,
                slm_name=candidate_model.model_name, slm_display=candidate_model.display_name,
                local=candidate_model.local,
                quality_tier=candidate_model.quality_tier,
                cost_in_per_1k=candidate_model.cost_in_per_1k,
                cost_out_per_1k=candidate_model.cost_out_per_1k,
                correctness_score=0.0, format_score=0.0,
                completeness_score=0.0, composite_score=0.0,
                n_evaluated=0, sample_comparisons=[],
                avg_latency_ms=0.0, p95_latency_ms=0.0,
                selection_score=0.0,
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

        result = ClusterEvalResult(
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            provider=candidate_model.provider,
            slm_name=candidate_model.model_name,
            slm_display=candidate_model.display_name,
            local=candidate_model.local,
            quality_tier=candidate_model.quality_tier,
            cost_in_per_1k=candidate_model.cost_in_per_1k,
            cost_out_per_1k=candidate_model.cost_out_per_1k,
            correctness_score=round(avg_correctness, 3),
            format_score=round(avg_format, 3),
            completeness_score=round(avg_completeness, 3),
            composite_score=round(composite, 3),
            n_evaluated=len(all_correctness),
            sample_comparisons=sample_comparisons,
            avg_latency_ms=round(sum(all_latencies) / len(all_latencies), 1),
            p95_latency_ms=round(p95_latency, 1),
            selection_score=selection_score(
                composite,
                candidate_model.quality_tier,
                candidate_model.cost_in_per_1k,
                candidate_model.cost_out_per_1k,
                max_cost_reference,
            ),
        )

        # Write to evaluation cache
        self._write_eval_cache(cache_key, result)

        return result

    def _select_representative_samples(
        self,
        cluster_id: int,
        cluster_df: pd.DataFrame,
        centroids: dict[int, np.ndarray],
        embeddings: np.ndarray,
    ) -> pd.DataFrame:
        """
        Pick a compact representative set for evaluation:
        - some prompts closest to the centroid (canonical cases)
        - some prompts farthest from the centroid (edge cases)
        Falls back to random sampling if embedding indices are unavailable.
        """
        target_n = min(self.config.n_samples_per_cluster, len(cluster_df))
        if target_n <= 0:
            return cluster_df.head(0)
        if len(cluster_df) <= target_n:
            return cluster_df.copy()
        if "_embedding_idx" not in cluster_df.columns or cluster_id not in centroids:
            return cluster_df.sample(n=target_n, random_state=42)

        centroid = centroids[cluster_id]
        working = cluster_df.copy()
        embedding_indices = working["_embedding_idx"].astype(int).tolist()
        working["_sim_to_centroid"] = [
            float(np.dot(embeddings[idx], centroid))
            for idx in embedding_indices
        ]

        central_count = max(1, round(target_n * self.config.central_sample_ratio))
        edge_count = max(0, target_n - central_count)

        selected_indices: list[int] = []

        central = working.sort_values("_sim_to_centroid", ascending=False).head(central_count)
        selected_indices.extend(central.index.tolist())

        if edge_count > 0:
            edge_candidates = working.loc[~working.index.isin(selected_indices)]
            edge = edge_candidates.sort_values("_sim_to_centroid", ascending=True).head(edge_count)
            selected_indices.extend(edge.index.tolist())

        if len(selected_indices) < target_n:
            remaining = working.loc[~working.index.isin(selected_indices)]
            filler = remaining.sample(n=min(target_n - len(selected_indices), len(remaining)), random_state=42)
            selected_indices.extend(filler.index.tolist())

        sample_df = working.loc[selected_indices].drop(columns=["_sim_to_centroid"], errors="ignore")
        return sample_df

    def _make_recommendation(
        self,
        cluster_id:        int,
        cluster_name:      str,
        cluster_size:      int,
        node_distribution: dict,
        evaluations:       list[ClusterEvalResult],
        cluster_cost_info: dict,
        cluster_reference: Optional[dict] = None,
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
        sorted_evals = sorted(
            evaluations,
            key=lambda e: (-e.selection_score, -e.composite_score, e.cost_in_per_1k + e.cost_out_per_1k)
        )
        incumbent_provider, incumbent_model = self._incumbent_identity(cluster_reference)
        incumbent_eval = next(
            (
                e for e in evaluations
                if e.provider == incumbent_provider and e.slm_name == incumbent_model
            ),
            None,
        )
        alternative_evals = [
            e for e in sorted_evals
            if not (e.provider == incumbent_provider and e.slm_name == incumbent_model)
        ]

        # Calculate estimated cost saving (assuming local SLMs are free)
        # avg_cost_usd per call × cluster_size gives total cost
        avg_cost_per_call = cluster_cost_info.get("avg_cost_usd", 0.001)
        total_cluster_cost = avg_cost_per_call * cluster_size

        best_eval = None
        recommendation = Recommendation.KEEP_LLM

        for eval_result in alternative_evals:
            if eval_result.composite_score >= self.config.quality_threshold:
                best_eval = eval_result
                recommendation = Recommendation.REPLACE_NOW
                break

        if recommendation == Recommendation.KEEP_LLM and alternative_evals:
            # No model passed — check if fine-tuning is worth it
            # Pick the best-scoring model as the fine-tune candidate
            best_candidate = max(alternative_evals, key=lambda e: e.composite_score)
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
            evaluations=sorted_evals,
            recommendation=recommendation,
            incumbent_provider=incumbent_eval.provider if incumbent_eval else incumbent_provider,
            incumbent_slm=incumbent_eval.slm_name if incumbent_eval else incumbent_model,
            incumbent_slm_display=incumbent_eval.slm_display if incumbent_eval else incumbent_model,
            incumbent_score=round(incumbent_eval.composite_score, 3) if incumbent_eval else 0.0,
            best_provider=best_eval.provider if best_eval else None,
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
        cluster_ids: Optional[list[int]] = None,
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
        cluster_info  = cluster_result["cluster_info"]
        clustered_df  = cluster_result["df"]
        centroids     = cluster_result["centroids"]
        embeddings    = cluster_result["embeddings"]
        judge_llm     = self._get_judge_llm()
        requested_cluster_ids = {int(cid) for cid in (cluster_ids or [])}
        if requested_cluster_ids:
            missing = requested_cluster_ids.difference({int(cid) for cid in cluster_info.keys()})
            if missing:
                raise RuntimeError(
                    f"Requested cluster_id(s) not found: {sorted(missing)}"
                )
            cluster_info = {
                cid: info for cid, info in cluster_info.items()
                if int(cid) in requested_cluster_ids
            }
        catalog = load_model_catalog(pathlib.Path(os.getenv("AGENTSHRINK_OUTPUT_DIR", ".agentshrink_output")))
        configured_models = [
            ModelCandidate(**model)
            for model in catalog.get("models", [])
            if model.get("enabled") and model.get("candidate_enabled", True)
        ]
        available_slms: list[ModelCandidate] = []
        eligibility_log: list[str] = []
        for candidate in configured_models:
            if candidate.provider == "ollama":
                if not self.runner.is_ollama_running():
                    if not skip_unavailable_models:
                        raise RuntimeError("Ollama is not running! Start it with: ollama serve")
                    eligibility_log.append(
                        f"- EXCLUDED {candidate.provider}:{candidate.model_name} -> Ollama not running"
                    )
                    continue
                if not self.runner.is_model_available(candidate):
                    eligibility_log.append(
                        f"- EXCLUDED {candidate.provider}:{candidate.model_name} -> model not found in ollama list"
                    )
                    continue
            eligibility_log.append(
                f"- INCLUDED {candidate.provider}:{candidate.model_name} -> enabled and available"
            )
            available_slms.append(candidate)

        if not available_slms:
            raise RuntimeError(
                "No enabled model candidates available for evaluation. "
                "Check your model catalog and local Ollama pulls."
            )

        logger.info("Model eligibility summary:")
        if configured_models:
            for line in eligibility_log:
                logger.info(line)
        else:
            logger.info("- No enabled models found in model catalog")

        scope_label = (
            f"clusters {sorted(requested_cluster_ids)}"
            if requested_cluster_ids else
            f"{len(cluster_info)} clusters"
        )
        logger.info(
            f"Evaluating {scope_label} "
            f"against {len(available_slms)} enabled models..."
        )
        max_cost_reference = max(
            (candidate.cost_in_per_1k + candidate.cost_out_per_1k for candidate in available_slms),
            default=0.001,
        )

        # Collect all evaluations per cluster
        # Structure: {cluster_id: [ClusterEvalResult, ...]}
        all_cluster_evals: dict[int, list[ClusterEvalResult]] = {
            cid: [] for cid in cluster_info.keys()
        }

        for slm in available_slms:
            logger.info(f"\n{'='*50}")
            logger.info(f"Evaluating with: {slm.display_name} ({slm.provider}:{slm.model_name})")
            logger.info(f"{'='*50}")

            if not self.runner.load_model(slm):
                logger.warning(f"Failed to prepare {slm.provider}:{slm.model_name} — skipping")
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
                    centroids=centroids,
                    embeddings=embeddings,
                    candidate_model=slm,
                    judge_llm=judge_llm,
                    max_cost_reference=max_cost_reference,
                )
                all_cluster_evals[cluster_id].append(eval_result)

                logger.info(
                    f"  → {slm.display_name}: "
                    f"composite={eval_result.composite_score:.2f}, "
                    f"avg_latency={eval_result.avg_latency_ms:.0f}ms"
                )

            logger.info(f"Unloading {slm.display_name}...")
            self.runner.unload_model(slm)

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
                cluster_reference={
                    "provider": info.get("reference_provider"),
                    "model": info.get("reference_model"),
                },
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
        output_dir: pathlib.Path,
        filename: str = "replaceability_report.json",
    ):
        """Save report artifacts and keep the aggregate report in sync."""
        output_dir = pathlib.Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / filename
        report_data = self._make_report_payload(reports)
        self._write_report_payload(report_path, report_data)

        for report in reports:
            cluster_report_path = output_dir / f"replaceability_report_cluster_{report.cluster_id}.json"
            self._write_report_payload(cluster_report_path, self._make_report_payload([report]))

        aggregate_payload = self._build_aggregate_report_payload(
            output_dir=output_dir,
            current_reports=reports,
        )
        self._write_report_payload(output_dir / "replaceability_report.json", aggregate_payload)

        logger.info(f"Report saved to {report_path}")
        return report_path

    def _make_report_payload(self, reports: list[ClusterReport]) -> dict:
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": self._compute_summary(reports),
            "clusters": [self._serialise_cluster_report(r) for r in reports],
        }

    def _serialise_cluster_report(self, report: ClusterReport) -> dict:
        return {
            "cluster_id": report.cluster_id,
            "cluster_name": report.cluster_name,
            "cluster_size": report.cluster_size,
            "recommendation": report.recommendation.value,
            "incumbent_provider": report.incumbent_provider,
            "incumbent_slm": report.incumbent_slm,
            "incumbent_slm_display": report.incumbent_slm_display,
            "incumbent_score": report.incumbent_score,
            "best_provider": report.best_provider,
            "best_slm": report.best_slm,
            "best_slm_display": report.best_slm_display,
            "best_score": report.best_score,
            "needs_fine_tuning": report.needs_fine_tuning,
            "fine_tune_base_model": report.fine_tune_base_model,
            "estimated_cost_saving_pct": report.estimated_cost_saving_pct,
            "node_distribution": report.node_distribution,
            "evaluations": [
                {
                    "slm_name": e.slm_name,
                    "provider": e.provider,
                    "slm_display": e.slm_display,
                    "local": e.local,
                    "quality_tier": e.quality_tier,
                    "cost_in_per_1k": e.cost_in_per_1k,
                    "cost_out_per_1k": e.cost_out_per_1k,
                    "correctness_score": e.correctness_score,
                    "format_score": e.format_score,
                    "completeness_score": e.completeness_score,
                    "composite_score": e.composite_score,
                    "avg_latency_ms": e.avg_latency_ms,
                    "p95_latency_ms": e.p95_latency_ms,
                    "selection_score": e.selection_score,
                    "n_evaluated": e.n_evaluated,
                    "sample_comparisons": e.sample_comparisons[:2],
                }
                for e in report.evaluations
            ],
        }

    def _write_report_payload(self, path: pathlib.Path, payload: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._to_json_safe(payload), f, indent=2)

    def _build_aggregate_report_payload(
        self,
        output_dir: pathlib.Path,
        current_reports: list[ClusterReport],
    ) -> dict:
        clusters_by_id = {}

        aggregate_path = output_dir / "replaceability_report.json"
        if aggregate_path.exists():
            try:
                with open(aggregate_path, encoding="utf-8") as f:
                    aggregate_report = json.load(f)
                for cluster in aggregate_report.get("clusters", []):
                    if "cluster_id" in cluster:
                        clusters_by_id[int(cluster["cluster_id"])] = cluster
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                logger.warning("Ignoring unreadable aggregate report at %s", aggregate_path)

        for cluster_path in output_dir.glob("replaceability_report_cluster_*.json"):
            try:
                with open(cluster_path, encoding="utf-8") as f:
                    cluster_report = json.load(f)
                for cluster in cluster_report.get("clusters", []):
                    if "cluster_id" in cluster:
                        clusters_by_id[int(cluster["cluster_id"])] = cluster
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                logger.warning("Ignoring unreadable cluster report at %s", cluster_path)

        for report in current_reports:
            clusters_by_id[int(report.cluster_id)] = self._serialise_cluster_report(report)

        clusters = [clusters_by_id[cid] for cid in sorted(clusters_by_id)]
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "summary": self._compute_serialized_summary(clusters),
            "clusters": clusters,
        }

    def _compute_serialized_summary(self, clusters: list[dict]) -> dict:
        replace_now = [c for c in clusters if c.get("recommendation") == Recommendation.REPLACE_NOW.value]
        fine_tune = [c for c in clusters if c.get("recommendation") == Recommendation.FINE_TUNE.value]
        keep_llm = [c for c in clusters if c.get("recommendation") == Recommendation.KEEP_LLM.value]

        total_clusters = len(clusters)
        total_size = sum(int(c.get("cluster_size", 0) or 0) for c in clusters)
        replaceable_size = sum(int(c.get("cluster_size", 0) or 0) for c in replace_now)
        finetune_size = sum(int(c.get("cluster_size", 0) or 0) for c in fine_tune)
        models_evaluated = sorted({
            ev.get("slm_name")
            for cluster in clusters
            for ev in (cluster.get("evaluations", []) or [])
            if ev.get("slm_name")
        })

        pct_replaceable_now = round(replaceable_size / total_size * 100, 1) if total_size > 0 else 0
        pct_with_finetune = round((replaceable_size + finetune_size) / total_size * 100, 1) if total_size > 0 else 0

        return {
            "total_clusters": total_clusters,
            "replace_now_count": len(replace_now),
            "fine_tune_count": len(fine_tune),
            "keep_llm_count": len(keep_llm),
            "pct_calls_replaceable_now": pct_replaceable_now,
            "pct_calls_replaceable_with_finetune": pct_with_finetune,
            "models_evaluated": models_evaluated,
        }

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
        table.add_column("Recommendation", style="cyan",   min_width=18)
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
            recommendation_label = r.best_slm_display or f"Keep {r.incumbent_slm_display or 'incumbent'}"

            table.add_row(
                r.cluster_name,
                recommendation_label,
                f"{r.best_score:.0%}" if r.best_score > 0 else "—",
                latency_str,
                action_text,
            )

        console.print(table)
