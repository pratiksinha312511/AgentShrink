"""
agentshrink/centroid_index.py
==============================
PHASE 4 — Centroid Index

WHAT THIS DOES:
  At routing time, every incoming LLM call needs to be matched
  to a cluster in under 50ms. This class does that:

  1. Loads the pre-computed cluster centroids from Phase 2/3
  2. Loads the cluster → model routing config from Phase 3
  3. For any new prompt: embed it → find nearest centroid → return routing decision

  This is the "fast path" that runs for EVERY single LLM call
  after AgentShrink is set up. Speed matters here.

WHY CENTROIDS AND NOT RE-CLUSTERING:
  Re-running HDBSCAN on every call would take 10+ seconds.
  Finding the nearest centroid takes ~10ms:
    - Embed the prompt: ~8ms (sentence-transformer, CPU)
    - Dot product against N centroids: ~1ms (numpy)
  Total: ~10ms overhead per call. Invisible to users.

CONFIDENCE THRESHOLD:
  If the nearest centroid similarity is below 0.75, we don't
  recognise this prompt pattern. We return cluster_id=-1 which
  tells ShrinkLLM to fall back to GPT-4o. Safety first.
"""

import json
import logging
import pathlib
import numpy as np
import os
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _heuristic_routing_from_cluster(cluster_name: str, cluster_meta: dict) -> dict:
    local_model = os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b")
    node_dist = cluster_meta.get("node_distribution", {}) or {}
    dominant = ""
    if node_dist:
        dominant = max(node_dist.items(), key=lambda kv: kv[1])[0].lower()

    if any(key in dominant for key in ("classify", "extract", "format")):
        return {
            "model_name": local_model,
            "model_display": f"Local ({local_model})",
            "is_local": True,
            "quality_score": 0.92,
        }

    if any(key in dominant for key in ("draft_reply", "check_policy")):
        return {
            "model_name": "fallback",
            "model_display": "Fallback (kept on strong model)",
            "is_local": False,
            "quality_score": 0.58,
        }

    return {
        "model_name": local_model,
        "model_display": f"Local ({local_model}) (heuristic)",
        "is_local": True,
        "quality_score": 0.72,
        "needs_fine_tune": True,
    }


@dataclass
class RoutingDecision:
    """
    The result of a routing lookup for one incoming prompt.
    ShrinkLLM reads this to decide which model to call.
    """
    cluster_id:     int           # -1 means "unknown, use fallback"
    cluster_name:   str           # Human-readable name ("classify_complaint")
    model_name:     str           # Ollama model name ("gemma2:2b") or "fallback"
    model_display:  str           # Human-readable ("Gemma 2 2B" or "GPT-4o")
    confidence:     float         # Cosine similarity to nearest centroid (0-1)
    is_local:       bool          # True = local Ollama, False = API fallback
    reason:         str           # Why this decision was made (for trace logging)
    nearest_cluster_name: Optional[str] = None
    nearest_similarity:   float = 0.0
    threshold:            float = 0.75


class CentroidIndex:
    """
    Loads cluster centroids and routing config, provides fast
    nearest-centroid lookup for incoming prompts.

    Usage:
        index = CentroidIndex.from_output_dir(".agentshrink_output")
        decision = index.route(prompt_text)
        print(decision.model_name)   # "gemma2:2b" or "fallback"
    """

    def __init__(
        self,
        centroids:          np.ndarray,           # Shape: (n_clusters, 384)
        centroid_ids:       list[int],            # Maps row index → cluster_id
        cluster_names:      dict[int, str],       # cluster_id → name
        routing_config:     dict[int, dict],      # cluster_id → {model, display, ...}
        confidence_threshold: float = 0.75,
        fallback_model:     str = "gpt-4o-mini",
    ):
        self.centroids           = centroids
        self.centroid_ids        = centroid_ids
        self.cluster_names       = cluster_names
        self.routing_config      = routing_config
        self.confidence_threshold = confidence_threshold
        self.fallback_model      = fallback_model
        self._embedder           = None   # Lazy loaded
        self._output_dir         = pathlib.Path(".")

    @classmethod
    def from_output_dir(
        cls,
        output_dir: pathlib.Path,
        confidence_threshold: float = 0.75,
    ) -> "CentroidIndex":
        """
        Load index from the files saved by Phase 2/3 (clusterer.save_results
        + evaluator.save_report).

        Files needed:
          output_dir/centroids.npy         — numpy array of centroids
          output_dir/cluster_info.json     — cluster metadata + routing config
          output_dir/replaceability_report.json — which model per cluster
        """
        output_dir = pathlib.Path(output_dir)

        # Load centroids
        centroids_path = output_dir / "centroids.npy"
        if not centroids_path.exists():
            raise FileNotFoundError(
                f"Centroids not found at {centroids_path}\n"
                "Run: agentshrink analyse"
            )
        centroids = np.load(centroids_path)

        # Load cluster info
        cluster_info_path = output_dir / "cluster_info.json"
        with open(cluster_info_path) as f:
            cluster_info = json.load(f)

        centroid_ids  = cluster_info["centroid_ids"]
        cluster_names = {
            int(k): v
            for k, v in cluster_info["cluster_names"].items()
        }

        # Prefer an explicitly applied routing config if present.
        routing_config = {}
        routing_config_path = output_dir / "routing_config.json"
        report_path = output_dir / "replaceability_report.json"

        if routing_config_path.exists():
            with open(routing_config_path, encoding="utf-8") as f:
                saved = json.load(f)
            routing_blob = saved.get("routing", saved)
            for cid_str, cfg in routing_blob.items():
                cid = int(cid_str)
                routing_config[cid] = {
                    "model_name": cfg.get("model") or cfg.get("model_name", "fallback"),
                    "model_display": cfg.get("display") or cfg.get("model_display", cfg.get("model", "fallback")),
                    "is_local": cfg.get("local", cfg.get("is_local", False)),
                    "quality_score": cfg.get("quality_score", 0.0),
                    "needs_fine_tune": cfg.get("source") == "fine_tune_pending" or cfg.get("needs_fine_tune", False),
                }
        elif report_path.exists():
            with open(report_path) as f:
                report = json.load(f)

            for cluster_data in report["clusters"]:
                cid = cluster_data["cluster_id"]
                rec = cluster_data["recommendation"]

                if rec == "replace_now" and cluster_data.get("best_slm"):
                    routing_config[cid] = {
                        "model_name":    cluster_data["best_slm"],
                        "model_display": cluster_data.get("best_slm_display", cluster_data["best_slm"]),
                        "is_local":      True,
                        "quality_score": cluster_data.get("best_score", 0.0),
                    }
                elif rec == "fine_tune" and cluster_data.get("fine_tune_base_model"):
                    # Check if a fine-tuned adapter is registered
                    # (will be populated in Phase 6)
                    adapter_name = f"agentshrink_{cluster_data['cluster_name']}_ft"
                    routing_config[cid] = {
                        "model_name":    cluster_data.get("best_slm") or adapter_name,
                        "model_display": f"{cluster_data.get('best_slm_display', '')} (fine-tuned)",
                        "is_local":      True,
                        "quality_score": cluster_data.get("best_score", 0.0),
                        "needs_fine_tune": True,
                    }
                else:
                    # KEEP_LLM — no local routing for this cluster
                    routing_config[cid] = {
                        "model_name":    "fallback",
                        "model_display": "API (kept)",
                        "is_local":      False,
                        "quality_score": 1.0,
                    }
        else:
            logger.warning(
                "No replaceability_report.json found. "
                "Using heuristic routing config from cluster metadata."
            )
            for cid_str, meta in cluster_info.get("clusters", {}).items():
                cid = int(cid_str)
                routing_config[cid] = _heuristic_routing_from_cluster(
                    cluster_names.get(cid, f"cluster_{cid}"),
                    meta,
                )

        index = cls(
            centroids=centroids,
            centroid_ids=centroid_ids,
            cluster_names=cluster_names,
            routing_config=routing_config,
            confidence_threshold=confidence_threshold,
        )
        index._output_dir = output_dir
        return index

    def _get_embedder(self):
        """Lazy-load sentence transformer — only on first route() call."""
        if self._embedder is None:
            output_dir = pathlib.Path(".")
            vectorizer_path = output_dir / "tfidf_vectorizer.joblib"
            # Handle relative default when instantiated via from_output_dir.
            if hasattr(self, "_output_dir"):
                vectorizer_path = self._output_dir / "tfidf_vectorizer.joblib"

            if vectorizer_path.exists():
                import joblib
                vectorizer = joblib.load(vectorizer_path)

                class _TfidfRuntimeEmbedder:
                    def __init__(self, vec):
                        self.vectorizer = vec

                    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
                        from sklearn.preprocessing import normalize
                        mat = self.vectorizer.transform(texts)
                        if normalize_embeddings:
                            mat = normalize(mat)
                        return mat.astype(np.float32).toarray()

                self._embedder = _TfidfRuntimeEmbedder(vectorizer)
            else:
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(
                    "all-MiniLM-L6-v2",
                    device="cpu"
                )
        return self._embedder

    def route(self, prompt: str) -> RoutingDecision:
        """
        Core routing function — called for every incoming LLM call.

        Takes ~10ms on CPU:
          ~8ms  embedding the prompt
          ~1ms  finding nearest centroid
          ~1ms  looking up routing config

        Returns RoutingDecision with the model to use.
        """
        if not prompt or len(prompt.strip()) < 5:
            return self._fallback_decision("prompt too short")

        # Embed the prompt
        embedder = self._get_embedder()
        embedding = embedder.encode(
            [prompt],
            normalize_embeddings=True,
            show_progress_bar=False
        )[0]  # Shape: (384,)

        # Find nearest centroid — dot product (embeddings are normalized)
        similarities = np.dot(self.centroids, embedding)  # Shape: (n_clusters,)
        best_idx     = int(np.argmax(similarities))
        best_sim     = float(similarities[best_idx])
        best_cid     = self.centroid_ids[best_idx]
        nearest_cluster_name = self.cluster_names.get(best_cid, f"cluster_{best_cid}")

        # Below confidence threshold → unknown prompt → fall back to API
        if best_sim < self.confidence_threshold:
            return self._fallback_decision(
                f"low confidence ({best_sim:.2f} < {self.confidence_threshold})",
                nearest_cluster_name=nearest_cluster_name,
                nearest_similarity=best_sim,
            )

        cluster_name = nearest_cluster_name
        config       = self.routing_config.get(best_cid, {})

        # No routing config → fall back
        if not config or config.get("model_name") == "fallback":
            return RoutingDecision(
                cluster_id=best_cid,
                cluster_name=cluster_name,
                model_name=self.fallback_model,
                model_display="API (cluster kept on LLM)",
                confidence=best_sim,
                is_local=False,
                reason=f"cluster '{cluster_name}' assigned to API (quality too low for local)",
                nearest_cluster_name=cluster_name,
                nearest_similarity=best_sim,
                threshold=self.confidence_threshold,
            )

        # Check if needs fine-tuning (not yet done)
        if config.get("needs_fine_tune") and not self._is_fine_tuned_available(config["model_name"]):
            return RoutingDecision(
                cluster_id=best_cid,
                cluster_name=cluster_name,
                model_name=self.fallback_model,
                model_display="API (pending fine-tune)",
                confidence=best_sim,
                is_local=False,
                reason=f"cluster '{cluster_name}' needs fine-tuning — using API until ready",
                nearest_cluster_name=cluster_name,
                nearest_similarity=best_sim,
                threshold=self.confidence_threshold,
            )

        # Route to local SLM
        return RoutingDecision(
            cluster_id=best_cid,
            cluster_name=cluster_name,
            model_name=config["model_name"],
            model_display=config.get("model_display", config["model_name"]),
            confidence=best_sim,
            is_local=True,
            reason=f"cluster '{cluster_name}' routed to local SLM (confidence: {best_sim:.2f})",
            nearest_cluster_name=cluster_name,
            nearest_similarity=best_sim,
            threshold=self.confidence_threshold,
        )

    def _fallback_decision(
        self,
        reason: str,
        nearest_cluster_name: Optional[str] = None,
        nearest_similarity: float = 0.0,
    ) -> RoutingDecision:
        """Return a fallback-to-API decision."""
        return RoutingDecision(
            cluster_id=-1,
            cluster_name="unknown",
            model_name=self.fallback_model,
            model_display="API (fallback)",
            confidence=0.0,
            is_local=False,
            reason=reason,
            nearest_cluster_name=nearest_cluster_name,
            nearest_similarity=nearest_similarity,
            threshold=self.confidence_threshold,
        )

    def _is_fine_tuned_available(self, model_name: str) -> bool:
        """Check if a fine-tuned model is available in Ollama."""
        try:
            import ollama
            models = ollama.list()
            return any(model_name in m.model for m in models.models)
        except Exception:
            return False

    def register_fine_tuned_model(
        self,
        cluster_id: int,
        ollama_model_name: str,
        display_name: str,
        output_dir: pathlib.Path,
    ):
        """
        Register a fine-tuned model for a cluster.
        Called in Phase 6 after fine-tuning completes.
        Updates both the in-memory config and saves to disk.
        """
        if cluster_id in self.routing_config:
            self.routing_config[cluster_id]["model_name"]    = ollama_model_name
            self.routing_config[cluster_id]["model_display"] = display_name
            self.routing_config[cluster_id]["is_local"]      = True
            self.routing_config[cluster_id].pop("needs_fine_tune", None)

            # Persist the update
            config_path = pathlib.Path(output_dir) / "routing_config.json"
            with open(config_path, "w") as f:
                json.dump(self.routing_config, f, indent=2)

            logger.info(f"Fine-tuned model '{ollama_model_name}' registered for cluster {cluster_id}")

    def get_stats(self) -> dict:
        """Summary of current routing configuration."""
        local_clusters = [
            cid for cid, cfg in self.routing_config.items()
            if cfg.get("is_local") and cfg.get("model_name") != "fallback"
            and not cfg.get("needs_fine_tune")
        ]
        api_clusters = [
            cid for cid, cfg in self.routing_config.items()
            if not cfg.get("is_local") or cfg.get("model_name") == "fallback"
        ]
        pending_clusters = [
            cid for cid, cfg in self.routing_config.items()
            if cfg.get("needs_fine_tune")
        ]

        return {
            "total_clusters":   len(self.routing_config),
            "local_clusters":   len(local_clusters),
            "api_clusters":     len(api_clusters),
            "pending_finetune": len(pending_clusters),
            "confidence_threshold": self.confidence_threshold,
            "routing": {
                str(cid): {
                    "name":  self.cluster_names.get(cid, f"cluster_{cid}"),
                    "model": cfg.get("model_name", "fallback"),
                    "local": cfg.get("is_local", False),
                }
                for cid, cfg in self.routing_config.items()
            }
        }
