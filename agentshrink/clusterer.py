"""
agentshrink/clusterer.py
=========================
PHASE 2 — Task Clusterer (Paper Section 6, Step S3)

WHAT THIS DOES:
  Takes the clean embeddings from the curator and discovers
  natural task groups using HDBSCAN density-based clustering.

  The paper says (S3): "Employ unsupervised clustering techniques
  on collected prompts to identify recurring patterns."

  We implement exactly this — no predefined categories,
  no manual labelling. The clusters emerge from the data.

THE ALGORITHM IN PLAIN ENGLISH:
  1. Each prompt is a point in 384-dimensional space (its embedding)
  2. UMAP compresses this to 2D — nearby points stay nearby
  3. HDBSCAN finds dense regions in the 2D space
  4. Each dense region = one task type
  5. Sparse points (noise) get label -1 — excluded from analysis

WHY HDBSCAN OVER K-MEANS:
  K-Means: you must specify k (number of clusters) upfront.
    Problem: you don't know how many task types your agent has.
  HDBSCAN: discovers k automatically from data density.
    Bonus: marks uncertain points as noise (label -1) instead
    of forcing them into the wrong cluster.

WHY 2D UMAP BEFORE HDBSCAN:
  HDBSCAN on 384 dimensions is slow and suffers from the
  "curse of dimensionality" — distances become meaningless
  in high dimensions. UMAP preserves the neighbourhood
  structure while reducing to 2D where HDBSCAN works well.
  This is the standard practice in the literature.
"""

import logging
import pathlib
import numpy as np
import pandas as pd
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

@dataclass
class ClusterConfig:
    """
    HDBSCAN + UMAP parameters.

    These were validated on synthetic data (5 known clusters, 100 entries).
    They work well for small datasets (100-2000 entries) on 8GB RAM.

    If clustering finds 0 clusters or 1 giant cluster:
      → Decrease min_cluster_size (try 3 or 2)

    If clustering finds 20+ tiny clusters:
      → Increase min_cluster_size (try 10 or 15)
    """

    # HDBSCAN parameters
    # min_cluster_size: minimum points to form a cluster
    # For 100 entries (synthetic): 5 works well
    # For 500+ entries (real logs): try 10-15
    min_cluster_size: int = 5
    min_samples: int = 3       # Controls how conservative cluster boundaries are
    cluster_selection_method: str = "eom"  # "eom" = excess of mass (better for varied sizes)

    # UMAP parameters
    umap_n_components: int = 2       # 2D for visualisation
    umap_n_neighbours: int = 10      # Local neighbourhood size (lower = more local structure)
    umap_min_dist: float = 0.1       # Minimum distance between points in 2D (lower = tighter clusters)
    umap_random_state: int = 42      # For reproducibility

    # Auto-label parameters
    # How many example prompts to send to LLM for cluster labelling
    label_n_examples: int = 3
    label_max_words: int = 4         # "classify complaint type" — short and memorable


# ─────────────────────────────────────────────
# THE CLUSTERER CLASS
# ─────────────────────────────────────────────

class TaskClusterer:
    """
    Clusters LLM prompts into task groups using HDBSCAN.

    Usage:
        clusterer = TaskClusterer()
        result = clusterer.fit(df, embeddings)

        print(f"Found {result['n_clusters']} clusters")
        print(result['cluster_summary'])
    """

    def __init__(self, config: Optional[ClusterConfig] = None):
        self.config = config or ClusterConfig()
        self._umap_model = None
        self._hdbscan_model = None

    def reduce_dimensions(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Step 1: Reduce 384D embeddings to 2D using UMAP.

        WHY UMAP AND NOT PCA:
          PCA is linear — it can't capture the curved manifold structure
          of semantic embeddings. UMAP is non-linear and preserves
          local neighbourhood structure much better.

        MEMORY: embeddings array for 500 prompts = ~0.75MB. Very safe.
        TIME: ~5-15 seconds for 500 prompts on CPU. Acceptable.
        """
        import umap

        logger.info(f"Reducing {embeddings.shape[1]}D embeddings to 2D with UMAP...")

        self._umap_model = umap.UMAP(
            n_components=self.config.umap_n_components,
            n_neighbors=self.config.umap_n_neighbours,
            min_dist=self.config.umap_min_dist,
            random_state=self.config.umap_random_state,
            metric="cosine",    # Cosine distance for semantic embeddings
            verbose=False,
        )

        coords_2d = self._umap_model.fit_transform(embeddings)
        logger.info(f"UMAP complete. Output shape: {coords_2d.shape}")
        return coords_2d

    def cluster(self, coords_2d: np.ndarray) -> np.ndarray:
        """
        Step 2: Find clusters in 2D space using HDBSCAN.

        Returns cluster labels array:
        - Labels 0, 1, 2, ... = cluster membership
        - Label -1 = noise (point doesn't belong to any cluster)

        HDBSCAN works by:
        1. Computing a minimum spanning tree of the data
        2. Condensing the tree based on min_cluster_size
        3. Extracting stable clusters from the condensed tree
        """
        import hdbscan

        logger.info(f"Clustering with HDBSCAN (min_cluster_size={self.config.min_cluster_size})...")

        self._hdbscan_model = hdbscan.HDBSCAN(
            min_cluster_size=self.config.min_cluster_size,
            min_samples=self.config.min_samples,
            cluster_selection_method=self.config.cluster_selection_method,
            metric="euclidean",  # Euclidean on the 2D UMAP coordinates
            prediction_data=True,  # Needed for predicting new point clusters later
        )

        labels = self._hdbscan_model.fit_predict(coords_2d)

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise    = (labels == -1).sum()
        noise_pct  = n_noise / len(labels) * 100

        logger.info(
            f"HDBSCAN found {n_clusters} clusters. "
            f"Noise points: {n_noise} ({noise_pct:.1f}%)"
        )

        if n_clusters == 0:
            logger.warning(
                "HDBSCAN found 0 clusters! Try decreasing min_cluster_size. "
                f"Current: {self.config.min_cluster_size}"
            )
        elif n_clusters == 1:
            logger.warning(
                "HDBSCAN found only 1 cluster. Your data may not have "
                "enough diversity, or min_cluster_size is too large."
            )
        elif n_clusters > 15:
            logger.warning(
                f"HDBSCAN found {n_clusters} clusters — possibly too many. "
                f"Try increasing min_cluster_size."
            )

        return labels

    def compute_centroids(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray
    ) -> dict[int, np.ndarray]:
        """
        Step 3: Compute the centroid of each cluster.

        The centroid is the mean of all embeddings in a cluster.
        We use these centroids at routing time — when a new prompt
        comes in, we find its nearest centroid to decide which
        cluster (and therefore which SLM) it maps to.

        Centroids are in the ORIGINAL 384D space (not 2D UMAP space)
        because we embed new prompts at routing time without UMAP.
        """
        centroids = {}
        unique_labels = set(labels) - {-1}  # Exclude noise

        for label in unique_labels:
            # Get all embeddings belonging to this cluster
            mask = labels == label
            cluster_embeddings = embeddings[mask]

            # Centroid = mean of all member embeddings
            centroid = cluster_embeddings.mean(axis=0)

            # Normalize the centroid for cosine similarity later
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm

            centroids[int(label)] = centroid

        return centroids

    def auto_label_clusters(
        self,
        df: pd.DataFrame,
        labels: np.ndarray,
        use_llm: bool = True
    ) -> dict[int, str]:
        """
        Step 4: Auto-label each cluster with a short human-readable name.

        Two modes:
        1. LLM mode (use_llm=True): sends sample prompts to GPT-4o-mini
           and asks for a 3-4 word label. Costs ~$0.001 total. Best quality.

        2. Heuristic mode (use_llm=False): extracts common words from
           prompts. Free, slightly lower quality, used for testing.

        For a portfolio project, the LLM-labeled clusters make a much
        better impression in the demo — "classify_complaint" vs "cluster_0".
        """
        unique_labels = sorted(set(labels) - {-1})
        cluster_labels = {}

        if use_llm:
            cluster_labels = self._llm_label_clusters(df, labels, unique_labels)
        else:
            cluster_labels = self._heuristic_label_clusters(df, labels, unique_labels)

        return cluster_labels

    def _llm_label_clusters(
        self,
        df: pd.DataFrame,
        labels: np.ndarray,
        unique_labels: list
    ) -> dict[int, str]:
        """Use GPT-4o-mini to generate cluster labels from sample prompts."""
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        cluster_labels = {}

        for label in unique_labels:
            # Get sample prompts from this cluster
            mask = labels == label
            cluster_df = df[mask]
            samples = cluster_df["prompt"].sample(
                min(self.config.label_n_examples, len(cluster_df))
            ).tolist()

            samples_text = "\n".join([f"- {s[:100]}" for s in samples])

            messages = [
                SystemMessage(content=f"""You name AI agent task types.
Given examples of prompts sent to an LLM, give a {self.config.label_max_words}-word snake_case label.
Examples: classify_complaint, extract_order_id, format_json_output, check_refund_policy
Respond with ONLY the label. No explanation."""),
                HumanMessage(content=f"Prompts from this cluster:\n{samples_text}")
            ]

            try:
                response = llm.invoke(messages)
                label_text = response.content.strip().lower()
                # Clean up the label — only keep valid characters
                label_text = "_".join(label_text.split()[:4])
                label_text = "".join(c if c.isalnum() or c == "_" else "" for c in label_text)
                cluster_labels[label] = label_text
                logger.info(f"Cluster {label} labelled: '{label_text}'")
            except Exception as e:
                logger.warning(f"LLM labelling failed for cluster {label}: {e}")
                cluster_labels[label] = f"cluster_{label}"

        return cluster_labels

    def _heuristic_label_clusters(
        self,
        df: pd.DataFrame,
        labels: np.ndarray,
        unique_labels: list
    ) -> dict[int, str]:
        """
        Heuristic fallback for cluster labelling — no API calls needed.
        Extracts the most distinctive words from each cluster's prompts.
        Good for testing; not as clean as LLM labels for the demo.
        """
        from collections import Counter
        import re

        # Common English words to ignore
        stop_words = {
            "the", "a", "an", "this", "that", "is", "are", "was", "were",
            "from", "to", "in", "of", "for", "and", "or", "with", "as",
            "it", "its", "be", "has", "have", "do", "does", "did",
            "by", "at", "on", "into", "out", "not", "only", "more"
        }

        cluster_labels = {}
        for label in unique_labels:
            mask = labels == label
            all_prompts = " ".join(df[mask]["prompt"].tolist()).lower()

            # Extract meaningful words
            words = re.findall(r'\b[a-z]{4,}\b', all_prompts)
            filtered = [w for w in words if w not in stop_words]
            word_counts = Counter(filtered)

            # Take top 2-3 most distinctive words
            top_words = [w for w, _ in word_counts.most_common(3)]
            label_text = "_".join(top_words[:2]) if top_words else f"cluster_{label}"
            cluster_labels[label] = label_text

        return cluster_labels

    def fit(
        self,
        df: pd.DataFrame,
        embeddings: np.ndarray,
        use_llm_labels: bool = True
    ) -> dict:
        """
        Run the full clustering pipeline on clean data.

        Returns a results dict with everything needed for:
        - The dashboard visualisation (coords_2d, labels, colors)
        - The replaceability analysis (centroids, cluster_info)
        - Saving to the database (cluster assignments per row)

        Args:
            df: Clean DataFrame from curator (with 'prompt' column)
            embeddings: Corresponding embeddings array from curator
            use_llm_labels: Whether to use GPT-4o-mini for cluster naming
        """
        # Step 1: UMAP dimensionality reduction
        coords_2d = self.reduce_dimensions(embeddings)

        # Step 2: HDBSCAN clustering
        labels = self.cluster(coords_2d)

        # Step 3: Compute centroids for routing
        centroids = self.compute_centroids(embeddings, labels)

        # Step 4: Auto-label clusters
        cluster_label_names = self.auto_label_clusters(df, labels, use_llm=use_llm_labels)

        # Step 5: Build cluster summary
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = (labels == -1).sum()

        cluster_info = {}
        for label_id, label_name in cluster_label_names.items():
            mask = labels == label_id
            cluster_df = df[mask]

            cluster_info[label_id] = {
                "id":           label_id,
                "name":         label_name,
                "size":         int(mask.sum()),
                "centroid":     centroids[label_id],
                "sample_prompts": cluster_df["prompt"].head(3).tolist(),
                "avg_latency_ms": float(cluster_df["latency_ms"].mean()) if "latency_ms" in cluster_df else 0,
                "avg_tokens":   float((cluster_df["tokens_in"] + cluster_df["tokens_out"]).mean()) if "tokens_in" in cluster_df else 0,
                "avg_cost_usd": float(cluster_df["cost_usd"].mean()) if "cost_usd" in cluster_df else 0,
                "node_distribution": cluster_df["node_name"].value_counts().to_dict() if "node_name" in cluster_df else {},
            }

        # Attach cluster assignments to the DataFrame
        df = df.copy()
        df["cluster_id"]   = labels
        df["cluster_name"] = [cluster_label_names.get(l, "noise") if l != -1 else "noise" for l in labels]
        df["umap_x"]       = coords_2d[:, 0]
        df["umap_y"]       = coords_2d[:, 1]

        # Assign colors for visualisation
        palette = [
            "#1D9E75", "#7F77DD", "#EF9F27",
            "#D85A30", "#185FA5", "#9F3F7A",
            "#5D8A1A", "#C44B4B", "#2B8B8B"
        ]
        color_map = {
            label_id: palette[i % len(palette)]
            for i, label_id in enumerate(sorted(cluster_label_names.keys()))
        }
        df["cluster_color"] = [
            color_map.get(l, "#888780") for l in labels
        ]

        result = {
            "df":              df,             # DataFrame with cluster columns added
            "embeddings":      embeddings,     # Original 384D embeddings
            "coords_2d":       coords_2d,      # UMAP 2D coords for visualisation
            "labels":          labels,         # HDBSCAN labels per row
            "n_clusters":      n_clusters,
            "n_noise":         n_noise,
            "noise_pct":       round(n_noise / len(labels) * 100, 1),
            "centroids":       centroids,      # For routing (384D)
            "cluster_info":    cluster_info,   # Rich metadata per cluster
            "cluster_names":   cluster_label_names,  # id → name mapping
            "color_map":       color_map,
        }

        self._log_summary(result)
        return result

    def _log_summary(self, result: dict):
        logger.info(f"Clustering complete:")
        logger.info(f"  Clusters found: {result['n_clusters']}")
        logger.info(f"  Noise points: {result['n_noise']} ({result['noise_pct']}%)")
        for cid, info in result["cluster_info"].items():
            logger.info(f"  Cluster {cid} '{info['name']}': {info['size']} points")

    def predict_cluster(
        self,
        prompt: str,
        centroids: dict[int, np.ndarray],
        embedder,
        confidence_threshold: float = 0.75
    ) -> tuple[int, float]:
        """
        Predict which cluster a new prompt belongs to.

        Used by ShrinkLLM at routing time — this is the fast path
        that runs for EVERY incoming LLM call after setup.

        Returns: (cluster_id, confidence_score)
        If confidence < threshold → returns (-1, confidence)
        meaning "unknown, fall back to GPT-4o"

        Speed: ~10ms on CPU (just one embedding + dot products)
        """
        # Embed the prompt
        embedding = embedder.encode(
            [prompt],
            normalize_embeddings=True,
            show_progress_bar=False
        )[0]

        if not centroids:
            return -1, 0.0

        # Find nearest centroid using cosine similarity (dot product on normalized vectors)
        best_cluster = -1
        best_sim = -1.0

        for cluster_id, centroid in centroids.items():
            sim = float(np.dot(embedding, centroid))
            if sim > best_sim:
                best_sim = sim
                best_cluster = cluster_id

        # If below confidence threshold, return "unknown"
        if best_sim < confidence_threshold:
            return -1, best_sim

        return best_cluster, best_sim

    def save_results(self, result: dict, output_dir: pathlib.Path):
        """
        Save clustering results to disk for use by the router and dashboard.

        Saves:
        - centroids.npy — numpy array of centroids (for fast routing)
        - cluster_info.json — metadata about each cluster
        - clustered_df.parquet — DataFrame with cluster assignments
        """
        import json

        output_dir = pathlib.Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save centroids as numpy (fast loading for routing)
        centroids_array = np.array([
            result["centroids"][i]
            for i in sorted(result["centroids"].keys())
        ])
        np.save(output_dir / "centroids.npy", centroids_array)

        # Save centroid ID mapping
        centroid_ids = [int(cid) for cid in sorted(result["centroids"].keys())]

        # Save cluster info as JSON (convert numpy types for JSON serialization)
        def _json_safe(value):
            if isinstance(value, np.generic):
                return value.item()
            if isinstance(value, dict):
                return {str(k): _json_safe(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_json_safe(v) for v in value]
            return value

        cluster_info_serializable = {}
        for cid, info in result["cluster_info"].items():
            cluster_info_serializable[str(cid)] = {
                k: _json_safe(v) for k, v in info.items()
                if k != "centroid"  # numpy array — saved separately
            }

        with open(output_dir / "cluster_info.json", "w") as f:
            json.dump({
                "n_clusters": int(result["n_clusters"]),
                "n_noise":    int(result["n_noise"]),
                "centroid_ids": centroid_ids,
                "clusters":   cluster_info_serializable,
                "cluster_names": {str(int(k)): _json_safe(v) for k, v in result["cluster_names"].items()},
            }, f, indent=2)

        # Save the full dataframe with cluster assignments
        result["df"].drop(
            columns=["_embedding_idx"], errors="ignore"
        ).to_parquet(output_dir / "clustered_df.parquet", index=False)

        logger.info(f"Clustering results saved to {output_dir}")
