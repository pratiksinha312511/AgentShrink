"""
agentshrink/curator.py
=======================
PHASE 2 — Data Curator (Paper Section 6, Step S2)

WHAT THIS DOES:
  Takes raw captured logs from SQLite and cleans them:
  1. Filters out failed workflow runs (unreliable training data)
  2. Removes PII — names, emails, phone numbers, order IDs get masked
  3. Deduplicates near-identical prompts using cosine similarity
  4. Validates minimum data quality (non-empty, minimum length)
  5. Returns a clean pandas DataFrame ready for clustering

WHY EACH STEP MATTERS:
  Failed runs → if the agent crashed mid-run, those prompts/responses
    may be incomplete or malformed. They'd corrupt our training data.

  PII removal → if we later fine-tune on this data, we don't want
    real customer names or order IDs baked into model weights.
    The paper explicitly requires this in S2.

  Deduplication → if "classify refund complaint" appears 200 times
    with identical text, clustering will create one massive cluster
    that drowns out the others. We keep one representative example.

  Minimum length → prompts shorter than 20 chars are usually noise
    (test calls, health checks) not real agent calls.
"""

import re
import sqlite3
import pathlib
import logging
import numpy as np
import pandas as pd
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

@dataclass
class CuratorConfig:
    """Controls how aggressively we clean the data."""

    # Deduplication: two prompts with cosine similarity > this
    # threshold are considered duplicates — we keep only one.
    # 0.95 = very strict (only near-identical removed)
    # 0.85 = moderate (semantically similar removed)
    # Lower = more aggressive deduplication
    dedup_threshold: float = 0.92

    # Minimum prompt length in characters
    # Prompts shorter than this are almost certainly noise
    min_prompt_length: int = 20

    # Maximum prompt length to embed (longer prompts get truncated)
    # sentence-transformers has a 256 token limit anyway
    max_prompt_length: int = 2000

    # Whether to mask PII in prompts before clustering
    # Set False only for testing/debugging
    mask_pii: bool = True

    # Only keep calls from runs where workflow_success = 1
    # Set False to include all calls (useful for debugging)
    successful_runs_only: bool = True


# ─────────────────────────────────────────────
# PII MASKING PATTERNS
# These patterns catch the most common PII types
# in customer support conversations.
# ─────────────────────────────────────────────

PII_PATTERNS = [
    # Email addresses → [EMAIL]
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),

    # Phone numbers (Indian and international) → [PHONE]
    (r'\b(?:\+91|0)?[6-9]\d{9}\b', '[PHONE]'),
    (r'\b\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]'),

    # Order IDs → [ORDER_ID]
    # Keep the structure but mask the specific number
    # We want "ORD-XXXXX" not "ORD-12345" in training data
    (r'\b(?:ORD|ORDER|REF|BK|INV|CS|SO|RCT|P)-?\d{4,}\b', '[ORDER_ID]'),
    (r'\b(?:order|invoice|reference|booking)\s*(?:number|#|id)?\s*:?\s*#?\d{4,}\b',
     'order [ORDER_ID]', re.IGNORECASE),

    # Credit card numbers → [CARD]
    (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', '[CARD]'),

    # Aadhaar numbers (12 digits) → [ID_NUMBER]
    (r'\b\d{4}\s?\d{4}\s?\d{4}\b', '[ID_NUMBER]'),
]


def mask_pii(text: str) -> str:
    """
    Replace PII patterns in text with placeholder tokens.

    This is NOT perfect — sophisticated NLP-based PII detection
    (like spaCy NER) is better for production. But for a portfolio
    project, regex patterns cover 95% of cases and add zero latency.

    For Phase 6 (fine-tuning), we'll add spaCy NER on top of this.
    """
    for pattern_args in PII_PATTERNS:
        if len(pattern_args) == 3:
            pattern, replacement, flags = pattern_args
            text = re.sub(pattern, replacement, text, flags=flags)
        else:
            pattern, replacement = pattern_args
            text = re.sub(pattern, replacement, text)
    return text


# ─────────────────────────────────────────────
# THE CURATOR CLASS
# ─────────────────────────────────────────────

class DataCurator:
    """
    Cleans raw LLM call logs into a DataFrame ready for clustering.

    Usage:
        curator = DataCurator(db_path="~/.agentshrink/logs.db")
        df = curator.curate()
        print(f"Clean rows: {len(df)}")
    """

    def __init__(
        self,
        db_path: Optional[pathlib.Path] = None,
        config: Optional[CuratorConfig] = None
    ):
        self.db_path = pathlib.Path(
            db_path or pathlib.Path("~/.agentshrink/logs.db")
        ).expanduser()
        self.config = config or CuratorConfig()
        self._embedder = None   # Lazy load — expensive import

    def _get_embedder(self):
        """
        Lazy-load the sentence transformer.
        We only import it when actually needed (deduplication step).
        This keeps the import fast when curator is just loaded.

        On 8GB RAM: this model uses ~400MB. Load it, use it,
        then the garbage collector can free it before Ollama loads.
        """
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            # all-MiniLM-L6-v2: 90MB, fast, good quality for clustering
            # Perfect balance for 8GB RAM constraint
            logger.info("Loading sentence transformer (first time only)...")
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        return self._embedder

    def load_from_db(self) -> pd.DataFrame:
        """
        Load raw logs from SQLite into a DataFrame.
        """
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Database not found: {self.db_path}\n"
                f"Have you run the logger yet? Try: python target_agent/agent.py"
            )

        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT * FROM llm_calls"
            if self.config.successful_runs_only:
                query += " WHERE workflow_success = 1"
            df = pd.read_sql_query(query, conn)

        logger.info(f"Loaded {len(df)} raw log entries from {self.db_path}")
        return df

    def load_from_json(self, json_path: pathlib.Path) -> pd.DataFrame:
        """
        Load logs from a JSON file (used for synthetic data testing).
        """
        import json
        with open(json_path) as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        logger.info(f"Loaded {len(df)} entries from {json_path}")
        return df

    def filter_quality(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Step 1: Remove low-quality entries.

        Removes:
        - Rows where prompt is empty or null
        - Rows where prompt is too short (likely noise/test calls)
        - Rows where prompt is too long (embedding quality degrades)
        """
        before = len(df)

        # Remove null/empty prompts
        df = df[df["prompt"].notna() & (df["prompt"].str.strip() != "")]

        # Remove prompts that are too short
        df = df[df["prompt"].str.len() >= self.config.min_prompt_length]

        # Truncate very long prompts (affects embedding quality)
        df["prompt"] = df["prompt"].str[:self.config.max_prompt_length]

        after = len(df)
        if before - after > 0:
            logger.info(f"Quality filter: removed {before - after} low-quality entries")

        return df.reset_index(drop=True)

    def apply_pii_masking(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Step 2: Mask PII in prompts.

        This is applied to prompts BEFORE clustering and before
        any fine-tuning dataset export. The responses are also
        masked because they may contain PII echoed from the prompt.
        """
        if not self.config.mask_pii:
            return df

        before_sample = df["prompt"].iloc[0] if len(df) > 0 else ""
        df["prompt"]   = df["prompt"].apply(mask_pii)
        df["response"] = df["response"].apply(
            lambda x: mask_pii(str(x)) if pd.notna(x) else x
        )

        # Recompute prompt hash after masking (hash changed)
        import hashlib
        df["prompt_hash"] = df["prompt"].apply(
            lambda p: hashlib.sha256(p.encode()).hexdigest()[:16]
        )

        after_sample = df["prompt"].iloc[0] if len(df) > 0 else ""
        if before_sample != after_sample:
            logger.debug("PII masking changed at least one prompt")

        return df

    def deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Step 3: Remove near-duplicate prompts using cosine similarity.

        WHY THIS IS IMPORTANT:
          If your agent runs 1000 customer queries and 600 of them
          trigger the same "classify complaint" node with nearly
          identical prompts, your cluster will be dominated by one
          task type. Deduplication ensures each unique prompt pattern
          appears only once — giving balanced clusters.

        HOW IT WORKS:
          1. Embed all prompts into 384-dimensional vectors
          2. Compute cosine similarity between all pairs
          3. For any pair with similarity > threshold, keep one, remove the other
          4. This is called "greedy deduplication" — fast but not optimal

        TIME COMPLEXITY: O(n²) — fine for n < 5000 on 8GB RAM.
          For larger datasets, use approximate nearest neighbours (FAISS).

        MEMORY NOTE FOR 8GB RAM:
          n=1000 prompts × 384 dimensions × 4 bytes = 1.5MB for embeddings
          Similarity matrix: n² × 4 bytes = 4MB for n=1000. Very safe.
        """
        if len(df) < 2:
            return df

        embedder = self._get_embedder()

        logger.info(f"Computing embeddings for {len(df)} prompts (for deduplication)...")

        # Batch embedding — chunk of 32 to avoid memory spikes on 8GB RAM
        # sentence-transformers handles batching internally but we control it
        batch_size = 32
        all_embeddings = []

        prompts = df["prompt"].tolist()
        for i in range(0, len(prompts), batch_size):
            batch = prompts[i:i + batch_size]
            batch_embeddings = embedder.encode(
                batch,
                show_progress_bar=False,
                normalize_embeddings=True  # Normalize → cosine sim = dot product
            )
            all_embeddings.append(batch_embeddings)

        embeddings = np.vstack(all_embeddings)  # Shape: (n_prompts, 384)

        # Greedy deduplication
        # Keep track of which indices to KEEP
        keep_indices = []
        removed_count = 0

        for i in range(len(embeddings)):
            is_duplicate = False
            for kept_idx in keep_indices:
                # Cosine similarity (embeddings are normalized, so this is dot product)
                sim = float(np.dot(embeddings[i], embeddings[kept_idx]))
                if sim > self.config.dedup_threshold:
                    is_duplicate = True
                    removed_count += 1
                    break
            if not is_duplicate:
                keep_indices.append(i)

        if removed_count > 0:
            logger.info(
                f"Deduplication: removed {removed_count} near-duplicate prompts "
                f"(threshold: {self.config.dedup_threshold})"
            )

        df_deduped = df.iloc[keep_indices].reset_index(drop=True)

        # Store embeddings on the dataframe — we'll reuse them for clustering
        # No need to recompute! This saves time and memory.
        kept_embeddings = embeddings[keep_indices]
        df_deduped["_embedding_idx"] = range(len(df_deduped))

        # Save embeddings separately (can't store numpy arrays in DataFrame columns easily)
        self._cached_embeddings = kept_embeddings

        return df_deduped

    def curate(
        self,
        source: str = "db",
        json_path: Optional[pathlib.Path] = None
    ) -> tuple[pd.DataFrame, np.ndarray]:
        """
        Main method: runs the full curation pipeline.

        Args:
            source: "db" to load from SQLite, "json" to load from file
            json_path: required if source="json"

        Returns:
            (clean_df, embeddings) — DataFrame and corresponding embeddings array
            The embeddings are already computed during deduplication, so
            the clusterer can use them directly without recomputing.
        """
        # Load data
        if source == "json" and json_path:
            df = self.load_from_json(json_path)
        else:
            df = self.load_from_db()

        original_count = len(df)
        logger.info(f"Starting curation of {original_count} entries...")

        # Pipeline: filter → mask PII → deduplicate
        df = self.filter_quality(df)
        df = self.apply_pii_masking(df)
        df = self.deduplicate(df)  # Also computes and caches embeddings

        final_count = len(df)
        removed = original_count - final_count

        logger.info(
            f"Curation complete: {original_count} → {final_count} entries "
            f"({removed} removed, {final_count/original_count*100:.0f}% retained)"
        )

        # Return both the DataFrame and the cached embeddings
        # (computed during deduplication, no need to recompute for clustering)
        embeddings = getattr(self, "_cached_embeddings", None)
        if embeddings is None:
            # Edge case: if dedup was skipped (< 2 entries), compute embeddings now
            embedder = self._get_embedder()
            embeddings = embedder.encode(
                df["prompt"].tolist(),
                normalize_embeddings=True,
                show_progress_bar=False
            )

        return df, embeddings

    def get_stats(self, df: pd.DataFrame) -> dict:
        """Return curation statistics for CLI display."""
        return {
            "total_rows":    len(df),
            "unique_nodes":  df["node_name"].nunique() if "node_name" in df.columns else 0,
            "nodes":         df["node_name"].value_counts().to_dict() if "node_name" in df.columns else {},
            "avg_prompt_len": int(df["prompt"].str.len().mean()),
            "date_range": {
                "first": df["timestamp"].min() if "timestamp" in df.columns else None,
                "last":  df["timestamp"].max() if "timestamp" in df.columns else None,
            }
        }
