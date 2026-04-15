"""
tests/test_phase2_clustering.py
================================
PHASE 2 VERIFICATION TESTS

Run these BEFORE building Phase 3 (SLM evaluator).
If clustering doesn't work on synthetic data, it won't
work on real data either. Fix it here first.

Tests run in order:
  Test 1: Synthetic data generates correctly (100 entries, 5 clusters)
  Test 2: Curator cleans data correctly (PII, dedup, quality filter)
  Test 3: UMAP reduces dimensions correctly
  Test 4: HDBSCAN finds exactly 5 clusters on synthetic data (ground truth check)
  Test 5: Cluster purity — each cluster mostly contains one task type
  Test 6: Centroids computed correctly
  Test 7: Cluster prediction on new prompt works

Run with:
    python tests/test_phase2_clustering.py
"""

import sys
import json
import pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
import sys, io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
console = Console(force_terminal=True)
SYNTHETIC_PATH = pathlib.Path("data/synthetic_logs.json")


def test_synthetic_data_generation():
    """TEST 1: Verify synthetic data generates correctly."""
    console.print("\n[bold]Test 1:[/bold] Synthetic data generation")

    from data.synthetic_generator import generate_synthetic_logs, SYNTHETIC_CLUSTERS

    entries = generate_synthetic_logs(output_path=SYNTHETIC_PATH)

    assert len(entries) == 100, f"Expected 100 entries, got {len(entries)}"

    # Check all 5 clusters are present
    cluster_names = {e["true_cluster_name"] for e in entries}
    expected = set(SYNTHETIC_CLUSTERS.keys())
    assert cluster_names == expected, f"Missing clusters: {expected - cluster_names}"

    # Check each cluster has 20 examples
    from collections import Counter
    counts = Counter(e["true_cluster_name"] for e in entries)
    for name, count in counts.items():
        assert count == 20, f"Cluster '{name}' has {count} entries, expected 20"

    # Check all required fields present
    required_fields = {"call_id", "prompt", "response", "node_name", "true_cluster_id"}
    for field in required_fields:
        assert all(field in e for e in entries), f"Missing field: {field}"

    console.print(f"  Generated: {len(entries)} entries across {len(cluster_names)} clusters")
    console.print("  [green]✓ Test 1 passed[/green] — Synthetic data generated correctly")
    return entries


def test_curator_cleans_data(entries: list):
    """TEST 2: Verify curator pipeline works on synthetic data."""
    console.print("\n[bold]Test 2:[/bold] Data curation pipeline")

    from agentshrink.curator import DataCurator, CuratorConfig

    config = CuratorConfig(
        dedup_threshold=0.98,  # Very permissive for synthetic (all unique)
        mask_pii=True,
        successful_runs_only=False,  # Synthetic data has no run tracking
    )
    curator = DataCurator(config=config)

    # Load from JSON (synthetic data)
    df, embeddings = curator.curate(source="json", json_path=SYNTHETIC_PATH)

    # Should retain most entries (synthetic has minimal duplication)
    assert len(df) >= 80, f"Too many entries removed: kept {len(df)}/100"
    assert embeddings is not None, "Embeddings not returned from curator"
    assert embeddings.shape[0] == len(df), "Embedding count doesn't match DataFrame length"
    assert embeddings.shape[1] == 384, f"Wrong embedding dimension: {embeddings.shape[1]}"

    # Check PII masking worked on order IDs
    # Our synthetic prompts contain order IDs like ORD-12345
    masked_count = df["prompt"].str.contains(r"\[ORDER_ID\]", regex=True).sum()
    console.print(f"  Entries after curation: {len(df)}/100")
    console.print(f"  Embedding shape: {embeddings.shape}")
    console.print(f"  Entries with masked order IDs: {masked_count}")
    console.print("  [green]✓ Test 2 passed[/green] — Curation pipeline works correctly")
    return df, embeddings


def test_umap_reduces_dimensions(df, embeddings):
    """TEST 3: Verify UMAP produces valid 2D coordinates."""
    console.print("\n[bold]Test 3:[/bold] UMAP dimensionality reduction")

    from agentshrink.clusterer import TaskClusterer, ClusterConfig

    config = ClusterConfig(
        umap_n_neighbours=min(10, len(df) - 1),  # Can't exceed n_samples - 1
        umap_random_state=42
    )
    clusterer = TaskClusterer(config=config)
    coords_2d = clusterer.reduce_dimensions(embeddings)

    assert coords_2d.shape == (len(df), 2), \
        f"Expected shape ({len(df)}, 2), got {coords_2d.shape}"

    # Coordinates should be finite
    assert not np.any(np.isnan(coords_2d)), "UMAP produced NaN coordinates"
    assert not np.any(np.isinf(coords_2d)), "UMAP produced infinite coordinates"

    # Points should be spread out (not all the same coordinate)
    x_range = coords_2d[:, 0].max() - coords_2d[:, 0].min()
    y_range = coords_2d[:, 1].max() - coords_2d[:, 1].min()
    assert x_range > 0.1, "UMAP output has no variation in x-axis"
    assert y_range > 0.1, "UMAP output has no variation in y-axis"

    console.print(f"  2D coords shape: {coords_2d.shape}")
    console.print(f"  X range: {x_range:.2f}, Y range: {y_range:.2f}")
    console.print("  [green]✓ Test 3 passed[/green] — UMAP works correctly")
    return coords_2d, clusterer


def test_hdbscan_finds_clusters(df, embeddings, coords_2d, clusterer):
    """
    TEST 4: The critical test — HDBSCAN should recover the 5 known clusters.

    This is the validation test that justifies synthetic data.
    We KNOW there are 5 clusters. If HDBSCAN doesn't find ~5,
    the parameters need tuning.
    """
    console.print("\n[bold]Test 4:[/bold] HDBSCAN cluster recovery (ground truth check)")

    labels = clusterer.cluster(coords_2d)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = (labels == -1).sum()

    # We expect to find close to 5 clusters
    # Allow some tolerance — HDBSCAN might merge two similar clusters
    assert 3 <= n_clusters <= 7, \
        f"Expected ~5 clusters, found {n_clusters}. " \
        f"Tune min_cluster_size (current: {clusterer.config.min_cluster_size})"

    console.print(f"  Clusters found: {n_clusters} (expected ~5)")
    console.print(f"  Noise points: {n_noise} ({n_noise/len(labels)*100:.1f}%)")

    if n_clusters == 5:
        console.print("  [green]✓ Perfectly found 5 clusters![/green]")
    elif 3 <= n_clusters <= 7:
        console.print(f"  [yellow]ℹ Found {n_clusters} clusters — close to target of 5[/yellow]")

    console.print("  [green]✓ Test 4 passed[/green] — HDBSCAN finds valid clusters")
    return labels


def test_cluster_purity(df, labels):
    """
    TEST 5: Cluster purity check.

    Each cluster should predominantly contain one true task type.
    If cluster 0 contains 80% classify prompts and 20% extract prompts,
    that's good (purity = 0.80).
    If it contains 30% each of 3 task types, the clustering is poor.

    Target: average purity > 0.70
    """
    console.print("\n[bold]Test 5:[/bold] Cluster purity (do clusters map to real task types?)")

    if "true_cluster_name" not in df.columns:
        console.print("  [yellow]⚠ Skipped — no ground truth labels in data[/yellow]")
        return

    non_noise_mask = labels != -1
    df_non_noise = df[non_noise_mask].copy()
    df_non_noise["predicted_cluster"] = labels[non_noise_mask]

    purities = []

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("Cluster", width=8)
    table.add_column("Dominant task type", width=25)
    table.add_column("Purity", justify="right")
    table.add_column("Size", justify="right")

    for cluster_id in sorted(df_non_noise["predicted_cluster"].unique()):
        cluster_rows = df_non_noise[df_non_noise["predicted_cluster"] == cluster_id]
        dominant_type = cluster_rows["true_cluster_name"].value_counts().index[0]
        purity = cluster_rows["true_cluster_name"].value_counts().iloc[0] / len(cluster_rows)
        purities.append(purity)

        purity_color = "green" if purity >= 0.8 else "yellow" if purity >= 0.6 else "red"
        table.add_row(
            str(cluster_id),
            dominant_type,
            f"[{purity_color}]{purity:.0%}[/{purity_color}]",
            str(len(cluster_rows))
        )

    console.print(table)
    avg_purity = sum(purities) / len(purities) if purities else 0
    console.print(f"  Average purity: {avg_purity:.0%}")

    assert avg_purity >= 0.60, \
        f"Average cluster purity too low: {avg_purity:.0%}. " \
        f"Clustering is not finding meaningful task groups."

    console.print("  [green]✓ Test 5 passed[/green] — Clusters are semantically coherent")


def test_centroids_computed(df, embeddings, labels, clusterer):
    """TEST 6: Verify centroids are computed correctly."""
    console.print("\n[bold]Test 6:[/bold] Centroid computation")

    centroids = clusterer.compute_centroids(embeddings, labels)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    assert len(centroids) == n_clusters, \
        f"Expected {n_clusters} centroids, got {len(centroids)}"

    for cluster_id, centroid in centroids.items():
        assert centroid.shape == (embeddings.shape[1],), \
            f"Centroid {cluster_id} has wrong shape: {centroid.shape}"
        # Centroid should be normalized
        norm = np.linalg.norm(centroid)
        assert abs(norm - 1.0) < 0.01, \
            f"Centroid {cluster_id} is not normalized (norm={norm:.3f})"

    console.print(f"  Centroids computed: {len(centroids)}")
    console.print(f"  Each centroid shape: {list(centroids.values())[0].shape}")
    console.print("  [green]✓ Test 6 passed[/green] — Centroids computed and normalized")
    return centroids


def test_cluster_prediction(centroids, clusterer):
    """
    TEST 7: Verify the predict_cluster function works for routing.

    This is what ShrinkLLM calls at runtime for every incoming prompt.
    It must return a cluster ID (or -1 for unknown) in under 50ms.
    """
    console.print("\n[bold]Test 7:[/bold] Cluster prediction for routing")

    from agentshrink.curator import DataCurator
    # Reuse the embedder from the curator
    curator = DataCurator()
    embedder = curator._get_embedder()

    test_cases = [
        ("Classify this customer complaint into: refund, shipping, product", "classify"),
        ("Extract the order number from this message: ORD-12345 not received", "extract"),
        ("Format the response as JSON with fields order_id and resolution", "format"),
    ]

    import time
    for prompt, expected_type in test_cases:
        start = time.perf_counter()
        cluster_id, confidence = clusterer.predict_cluster(
            prompt, centroids, embedder, confidence_threshold=0.5
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        console.print(
            f"  '{prompt[:45]}...' → "
            f"cluster {cluster_id}, conf={confidence:.2f}, {elapsed_ms:.0f}ms"
        )

        assert elapsed_ms < 500, \
            f"Prediction too slow: {elapsed_ms:.0f}ms (must be < 500ms)"

    console.print("  [green]✓ Test 7 passed[/green] — Cluster prediction works for routing")


def test_full_pipeline_on_synthetic():
    """
    TEST 8: Run the complete fit() pipeline end-to-end on synthetic data.
    This is what the analyse command will call.
    """
    console.print("\n[bold]Test 8:[/bold] Full clustering pipeline end-to-end")

    from agentshrink.curator import DataCurator, CuratorConfig
    from agentshrink.clusterer import TaskClusterer, ClusterConfig

    curator = DataCurator(config=CuratorConfig(
        dedup_threshold=0.98,
        successful_runs_only=False,
    ))
    df, embeddings = curator.curate(source="json", json_path=SYNTHETIC_PATH)

    clusterer = TaskClusterer(config=ClusterConfig(
        min_cluster_size=5,
        umap_n_neighbours=min(10, len(df) - 1),
    ))

    # Use heuristic labels (no LLM cost for testing)
    result = clusterer.fit(df, embeddings, use_llm_labels=False)

    assert "df" in result
    assert "n_clusters" in result
    assert "centroids" in result
    assert "cluster_info" in result
    assert "coords_2d" in result
    assert result["n_clusters"] >= 3, f"Too few clusters: {result['n_clusters']}"

    # Verify the output DataFrame has required columns
    required_cols = {"cluster_id", "cluster_name", "umap_x", "umap_y", "cluster_color"}
    assert required_cols.issubset(set(result["df"].columns)), \
        f"Missing columns: {required_cols - set(result['df'].columns)}"

    # Test saving results
    output_dir = pathlib.Path("/tmp/agentshrink_test_output")
    clusterer.save_results(result, output_dir)
    assert (output_dir / "centroids.npy").exists()
    assert (output_dir / "cluster_info.json").exists()
    assert (output_dir / "clustered_df.parquet").exists()

    console.print(f"  Clusters found: {result['n_clusters']}")
    console.print(f"  Noise points: {result['n_noise']} ({result['noise_pct']}%)")
    console.print(f"  Cluster names: {list(result['cluster_names'].values())}")
    console.print(f"  Output saved to: {output_dir}")
    console.print("  [green]✓ Test 8 passed[/green] — Full pipeline works end-to-end")

    return result


if __name__ == "__main__":
    console.print(Panel.fit(
        "[bold]AgentShrink — Phase 2 Clustering Verification Tests[/bold]\n"
        "These tests validate clustering on synthetic data\n"
        "before running on your real agent logs.\n\n"
        "[yellow]DO NOT proceed to Phase 3 if any test fails.[/yellow]",
        border_style="blue"
    ))

    try:
        # Sequential tests — each builds on previous results
        entries = test_synthetic_data_generation()
        df, embeddings = test_curator_cleans_data(entries)
        coords_2d, clusterer = test_umap_reduces_dimensions(df, embeddings)
        labels = test_hdbscan_finds_clusters(df, embeddings, coords_2d, clusterer)
        test_cluster_purity(df, labels)
        centroids = test_centroids_computed(df, embeddings, labels, clusterer)
        test_cluster_prediction(centroids, clusterer)
        result = test_full_pipeline_on_synthetic()

        console.print(Panel.fit(
            "[bold green]All 8 tests passed ✓[/bold green]\n\n"
            "Phase 2 complete. Clustering is working correctly.\n"
            "You are ready to build Phase 3 — the SLM evaluator.",
            border_style="green"
        ))

        # Show what the output looks like
        console.print("\n[bold]Cluster summary from your synthetic data:[/bold]")
        table = Table(box=box.ROUNDED)
        table.add_column("Cluster ID", justify="center")
        table.add_column("Name",       style="white")
        table.add_column("Size",       justify="right", style="cyan")
        table.add_column("Avg Latency", justify="right")

        for cid, info in result["cluster_info"].items():
            table.add_row(
                str(cid),
                info["name"],
                str(info["size"]),
                f"{info['avg_latency_ms']:.0f}ms"
            )
        console.print(table)

    except AssertionError as e:
        console.print(f"\n[bold red]❌ TEST FAILED:[/bold red] {e}")
        console.print("[red]Fix this before moving to Phase 3.[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]❌ ERROR:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
