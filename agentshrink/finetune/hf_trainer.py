"""
HuggingFace-backed fine-tuning runner.

This path shells out to autotrain-advanced so we can stream stdout lines back
into the persistent dashboard job record.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


SUPPORTED_CPU_MODELS = [
    {
        "id": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "label": "SmolLM2 1.7B (recommended for CPU)",
        "deploy_base_model": "smollm2:1.7b",
    },
    {
        "id": "Qwen/Qwen2.5-1.5B-Instruct",
        "label": "Qwen 2.5 1.5B",
        "deploy_base_model": "qwen2.5:1.5b",
    },
]


def run_hf_training(
    config: dict[str, Any],
    training_rows: list[dict[str, str]],
    *,
    hf_token: str,
    on_status: Callable[[str, int], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    on_metric: Callable[[dict[str, Any]], None] | None = None,
    on_process: Callable[[subprocess.Popen], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    out_dir = Path(config["artifact_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    data_csv = out_dir / "train.csv"

    import csv

    with open(data_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text"])
        writer.writeheader()
        for row in training_rows:
            text = f"### Input:\n{row['prompt']}\n\n### Response:\n{row['completion']}"
            writer.writerow({"text": text})

    if on_status:
        on_status("Preparing HuggingFace AutoTrain input...", 20)
    if on_log:
        on_log(f"Wrote {len(training_rows)} rows to {data_csv}")

    repo_id = f"agentshrink-cluster-{config['cluster_id']}-{int(time.time())}"
    cmd = [
        sys.executable, "-m", "autotrain", "llm",
        "--train",
        "--model", config["base_model"],
        "--data-path", str(out_dir),
        "--output", str(out_dir / "adapter"),
        "--epochs", str(config.get("epochs", 2)),
        "--lr", str(config.get("learning_rate", 2e-4)),
        "--batch-size", str(config.get("batch_size", 1)),
        "--gradient-accumulation", str(config.get("gradient_accumulation_steps", 8)),
        "--peft",
        "--quantization", "int4",
        "--trainer", "sft",
        "--token", hf_token,
        "--username", "agentshrink-finetune",
        "--push-to-hub",
        "--repo-id", repo_id,
    ]

    if on_status:
        on_status("Training on HuggingFace backend...", 45)
    if on_log:
        on_log("Starting autotrain-advanced process...")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, "HF_TOKEN": hf_token},
    )
    if on_process:
        on_process(proc)

    metrics: list[dict[str, Any]] = []
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        if should_stop and should_stop():
            proc.terminate()
            raise RuntimeError("Training stopped by user.")

        line = raw_line.strip()
        if not line:
            continue
        if on_log:
            on_log(line)
        lowered = line.lower()
        if "loss" in lowered:
            try:
                parsed = json.loads(line)
                metric = {
                    "step": parsed.get("step", len(metrics) + 1),
                    "epoch": parsed.get("epoch", 0),
                    "loss": parsed.get("loss", 0),
                }
                metrics.append(metric)
                if on_metric:
                    on_metric(metric)
            except Exception:
                pass

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("autotrain-advanced process failed. Check the fine-tune log output for details.")

    if on_status:
        on_status("Collecting HuggingFace training artifacts...", 80)

    adapter_dir = out_dir / "adapter"
    return {
        "success": True,
        "metrics": metrics,
        "artifact_kind": "adapter",
        "artifact_dir": str(adapter_dir),
        "deploy_base_model": config["deploy_base_model"],
    }
