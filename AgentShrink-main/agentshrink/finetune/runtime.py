from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from difflib import SequenceMatcher
from statistics import mean
from typing import Any, Callable

from agentshrink.finetune.jobs import recommended_display_name, recommended_model_name


ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _clean_console_line(value: str) -> str:
    cleaned = ANSI_ESCAPE_RE.sub("", value or "")
    cleaned = cleaned.replace("\r", " ").replace("\u001b", "")
    return " ".join(cleaned.split())


BACKEND_OPTIONS = [
    {
        "id": "local",
        "label": "Local machine",
        "subtitle": "PEFT / LoRA on this machine",
        "time": "Hardware-dependent",
        "cost": "Local compute only",
        "recommended": False,
        "setup_note": "Needs local fine-tune deps; HF_TOKEN only for gated base models",
    },
    {
        "id": "modal",
        "label": "Modal.com",
        "subtitle": "GPU - A10G 24GB VRAM",
        "time": "~10 min",
        "cost": "Cloud usage",
        "recommended": True,
        "setup_note": "Needs MODAL_TOKEN_ID and MODAL_TOKEN_SECRET",
    },
    {
        "id": "huggingface",
        "label": "HuggingFace",
        "subtitle": "AutoTrain / Hub backend",
        "time": "~60 min",
        "cost": "Free or paid depending on backend",
        "recommended": False,
        "setup_note": "Needs HF_TOKEN with write access",
    },
]


BACKEND_MODELS = {
    "local": [
        {
            "id": "Qwen/Qwen2.5-1.5B-Instruct",
            "label": "Qwen 2.5 1.5B (recommended)",
            "deploy_base_model": "qwen2.5:1.5b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
            "label": "SmolLM2 1.7B",
            "deploy_base_model": "smollm2:1.7b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "microsoft/Phi-3.5-mini-instruct",
            "label": "Phi 3.5 Mini",
            "deploy_base_model": "phi3.5:3.8b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "meta-llama/Llama-3.2-3B-Instruct",
            "label": "Llama 3.2 3B (HF gated access)",
            "deploy_base_model": "llama3.2:3b",
            "gated": True,
            "requires_hf_token": True,
        },
    ],
    "modal": [
        {
            "id": "Qwen/Qwen2.5-1.5B-Instruct",
            "label": "Qwen 2.5 1.5B (recommended)",
            "deploy_base_model": "qwen2.5:1.5b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
            "label": "SmolLM2 1.7B",
            "deploy_base_model": "smollm2:1.7b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "microsoft/Phi-3.5-mini-instruct",
            "label": "Phi 3.5 Mini",
            "deploy_base_model": "phi3.5:3.8b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "meta-llama/Llama-3.2-3B-Instruct",
            "label": "Llama 3.2 3B (HF gated access)",
            "deploy_base_model": "llama3.2:3b",
            "gated": True,
            "requires_hf_token": True,
        },
    ],
    "huggingface": [
        {
            "id": "Qwen/Qwen2.5-1.5B-Instruct",
            "label": "Qwen 2.5 1.5B (recommended)",
            "deploy_base_model": "qwen2.5:1.5b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
            "label": "SmolLM2 1.7B",
            "deploy_base_model": "smollm2:1.7b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "microsoft/Phi-3.5-mini-instruct",
            "label": "Phi 3.5 Mini",
            "deploy_base_model": "phi3.5:3.8b",
            "gated": False,
            "requires_hf_token": False,
        },
        {
            "id": "meta-llama/Llama-3.2-3B-Instruct",
            "label": "Llama 3.2 3B (HF gated access)",
            "deploy_base_model": "llama3.2:3b",
            "gated": True,
            "requires_hf_token": True,
        },
    ],
}


def backend_statuses() -> list[dict[str, Any]]:
    result = []
    for backend in BACKEND_OPTIONS:
        item = dict(backend)
        if backend["id"] == "local":
            configured, detail = _local_backend_ready()
            item["configured"] = configured
            if detail:
                item["health_detail"] = detail
                if not configured:
                    item["setup_note"] = detail
        elif backend["id"] == "modal":
            item["configured"] = bool(os.getenv("MODAL_TOKEN_ID", "").strip() and os.getenv("MODAL_TOKEN_SECRET", "").strip())
        elif backend["id"] == "huggingface":
            item["configured"] = bool(os.getenv("HF_TOKEN", "").strip())
        else:
            item["configured"] = False
        item["models"] = BACKEND_MODELS.get(backend["id"], [])
        result.append(item)
    return result


def _local_backend_ready() -> tuple[bool, str]:
    check_code = (
        "import torch\n"
        "from datasets import Dataset\n"
        "from peft import LoraConfig\n"
        "from transformers import AutoTokenizer\n"
        "print('ok')\n"
    )
    env = os.environ.copy()
    env.setdefault("PYTHONNOUSERSITE", "1")
    try:
        result = subprocess.run(
            [sys.executable, "-c", check_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            env=env,
        )
    except Exception as exc:
        return False, f"Local trainer health check could not start: {type(exc).__name__}: {exc}"

    if result.returncode == 0:
        return True, "Local trainer runtime is healthy in the active backend interpreter."

    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    detail = stderr or stdout or f"Health check failed with exit code {result.returncode}."
    detail = detail.splitlines()[-1]
    return False, f"Local trainer runtime failed in this backend interpreter: {detail}"


def choose_default_model(backend: str) -> dict[str, Any]:
    models = BACKEND_MODELS.get(backend, [])
    if not models:
        raise ValueError(f"No models configured for backend '{backend}'")
    for model in models:
        if not model.get("gated"):
            return model
    return models[0]


def lookup_backend_model(backend: str, model_id: str) -> dict[str, Any] | None:
    for model in BACKEND_MODELS.get(backend, []):
        if model.get("id") == model_id:
            return model
    return None


def write_training_artifacts(result: dict[str, Any], artifact_dir: pathlib.Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_kind = result.get("artifact_kind", "adapter")

    if "artifacts" in result:
        if artifact_kind == "adapter":
            adapter_dir = artifact_dir / "adapter"
            adapter_dir.mkdir(parents=True, exist_ok=True)
            import base64

            for filename, encoded in result["artifacts"].items():
                (adapter_dir / filename).write_bytes(base64.b64decode(encoded))
            return {"artifact_kind": "adapter", "artifact_dir": str(adapter_dir)}

        if artifact_kind == "gguf":
            import base64
            for filename, encoded in result["artifacts"].items():
                (artifact_dir / filename).write_bytes(base64.b64decode(encoded))
            return {"artifact_kind": "gguf", "artifact_dir": str(artifact_dir)}

    if result.get("artifact_dir"):
        source = pathlib.Path(result["artifact_dir"])
        if not source.exists():
            raise FileNotFoundError(f"Expected artifact directory not found: {source}")
        target = artifact_dir / "adapter"
        # If source and target are the same path (local trainer saves directly
        # into artifact_dir/adapter), skip the copy — artifacts are already in place.
        if source.resolve() == target.resolve():
            return {"artifact_kind": artifact_kind, "artifact_dir": str(target)}
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        return {"artifact_kind": artifact_kind, "artifact_dir": str(target)}

    raise RuntimeError("Trainer finished without producing artifacts.")


def deploy_to_ollama(
    *,
    cluster_name: str,
    cluster_id: int,
    artifact_info: dict[str, Any],
    deploy_base_model: str,
    output_dir: pathlib.Path,
    on_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    model_name = recommended_model_name(cluster_name)
    display_name = recommended_display_name(cluster_name)
    artifact_dir = pathlib.Path(artifact_info["artifact_dir"])
    deploy_dir = output_dir / "finetuned" / f"cluster_{cluster_id}_{cluster_name}"
    deploy_dir.mkdir(parents=True, exist_ok=True)

    if artifact_info["artifact_kind"] == "adapter":
        target_adapter_dir = deploy_dir / "adapter"
        if target_adapter_dir.exists():
            shutil.rmtree(target_adapter_dir)
        shutil.copytree(artifact_dir, target_adapter_dir)
        adapter_weights = target_adapter_dir / "adapter_model.safetensors"
        if not adapter_weights.exists():
            raise FileNotFoundError(f"Expected adapter weights not found at {adapter_weights}")
        merged_model_dir = deploy_dir / "merged_model"
        merged_safetensors = list(merged_model_dir.glob("*.safetensors")) if merged_model_dir.exists() else []
        if merged_model_dir.exists() and merged_safetensors:
            if on_log:
                on_log(
                    f"Reusing existing merged model at {merged_model_dir} instead of merging again."
                )
        else:
            if merged_model_dir.exists():
                shutil.rmtree(merged_model_dir)
            _merge_adapter_with_base_model(
                base_model=deploy_base_model,
                adapter_dir=target_adapter_dir,
                output_dir=merged_model_dir,
                on_log=on_log,
            )
        modelfile = deploy_dir / "Modelfile"
        modelfile.write_text(
            "FROM ./merged_model\n"
            "PARAMETER temperature 0.7\n"
            "PARAMETER top_p 0.9\n"
            "PARAMETER num_ctx 2048\n",
            encoding="utf-8",
        )
    else:
        gguf_files = list(artifact_dir.glob("*.gguf"))
        if not gguf_files:
            raise FileNotFoundError(f"No GGUF file found in {artifact_dir}")
        gguf_name = gguf_files[0].name
        shutil.copy2(gguf_files[0], deploy_dir / gguf_name)
        modelfile = deploy_dir / "Modelfile"
        modelfile.write_text(f"FROM ./{gguf_name}\n", encoding="utf-8")

    if on_log:
        on_log(f"Creating Ollama model '{model_name}' from {modelfile}")

    cmd = ["ollama", "create", model_name, "-f", "Modelfile"]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(deploy_dir),
    )
    stdout_lines: list[str] = []
    last_logged_line = ""
    assert process.stdout is not None
    last_heartbeat = time.time()
    while True:
        line = process.stdout.readline()
        if line:
            clean = _clean_console_line(line)
            if clean:
                if clean == last_logged_line:
                    last_heartbeat = time.time()
                    continue
                last_logged_line = clean
                stdout_lines.append(clean)
                if on_log:
                    on_log(clean)
            last_heartbeat = time.time()
            continue
        if process.poll() is not None:
            break
        if time.time() - last_heartbeat >= 30:
            if on_log:
                on_log("Ollama is still importing the merged model...")
            last_heartbeat = time.time()
        time.sleep(1.0)

    result_code = process.wait()
    stdout_text = "\n".join(stdout_lines).strip()
    if result_code != 0:
        raise RuntimeError(stdout_text or "ollama create failed")

    registered_name = f"{model_name}:latest"
    return {
        "ollama_name": registered_name,
        "display_name": display_name,
        "deploy_dir": str(deploy_dir),
        "stdout": stdout_text,
    }


def evaluate_deployed_model(
    model_name: str,
    training_rows: list[dict[str, Any]],
    *,
    sample_size: int = 2,
    on_log: Callable[[str], None] | None = None,
) -> float:
    try:
        import ollama
    except Exception as exc:
        raise RuntimeError("Ollama Python client is not available for post-train evaluation.") from exc

    rows = training_rows[:sample_size]
    if not rows:
        return 0.0

    scores = []
    for index, row in enumerate(rows, start=1):
        if on_log:
            on_log(f"Evaluating deployed model sample {index}/{len(rows)}")
        try:
            response = ollama.generate(
                model=model_name,
                prompt=row["prompt"],
                options={
                    "temperature": 0,
                    "num_predict": 96,
                    "num_ctx": 512,
                },
                keep_alive="5m",
            )
        except Exception as eval_exc:
            if on_log:
                on_log(f"Ollama inference failed for sample {index}: {eval_exc}")
            continue
        text = ""
        if isinstance(response, dict):
            text = response.get("response", "")
        else:
            text = getattr(response, "response", "")
        scores.append(SequenceMatcher(None, text.strip(), row["completion"].strip()).ratio())
    if on_log:
        on_log("Post-train accuracy check complete")
    return round(mean(scores) * 100, 1) if scores else 0.0


def load_training_rows_from_dataset(dataset_path: pathlib.Path) -> list[dict[str, str]]:
    with open(dataset_path, encoding="utf-8") as f:
        rows = json.load(f)
    if rows and "conversations" in rows[0]:
        converted = []
        for row in rows:
            conv = row.get("conversations", [])
            prompt = conv[0].get("value", "") if len(conv) > 0 else ""
            completion = conv[1].get("value", "") if len(conv) > 1 else ""
            converted.append({"prompt": prompt, "completion": completion})
        return converted
    return rows


def _merge_adapter_with_base_model(
    *,
    base_model: str,
    adapter_dir: pathlib.Path,
    output_dir: pathlib.Path,
    on_log: Callable[[str], None] | None = None,
) -> None:
    configured_cache_root = os.getenv("AGENTSHRINK_HF_CACHE_ROOT", "").strip()
    if configured_cache_root:
        cache_root = pathlib.Path(configured_cache_root).expanduser()
    else:
        # Keep this path short on Windows; deep Hugging Face cache paths can exceed
        # practical limits during adapter merge/download flows.
        cache_root = pathlib.Path(tempfile.gettempdir()) / "agentshrink_hf"
    cache_root.mkdir(parents=True, exist_ok=True)
    hf_base_model = _ollama_base_to_hf_model(base_model)
    if on_log:
        on_log(
            f"Merging adapter into base model {hf_base_model}. "
            "This can take a few minutes on CPU and may download base-model files from Hugging Face on first run."
        )
        on_log(f"Using Hugging Face cache root: {cache_root}")
    env = os.environ.copy()
    env["HF_HOME"] = str(cache_root)
    env["HUGGINGFACE_HUB_CACHE"] = str(cache_root / "hub")
    env["TRANSFORMERS_CACHE"] = str(cache_root / "transformers")
    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    env["HF_HUB_DISABLE_XET"] = "1"
    env["HF_HUB_ETAG_TIMEOUT"] = os.getenv("HF_HUB_ETAG_TIMEOUT", "60")
    env["HF_HUB_DOWNLOAD_TIMEOUT"] = os.getenv("HF_HUB_DOWNLOAD_TIMEOUT", "1800")
    # Propagate SSL bypass for corporate proxies
    env.setdefault("HF_HUB_DISABLE_SSL_VERIFY", os.getenv("HF_HUB_DISABLE_SSL_VERIFY", "0"))
    cmd = [
        sys.executable,
        "-m",
        "agentshrink.finetune.merge_adapter_cli",
        "--base-model",
        hf_base_model,
        "--adapter-dir",
        str(adapter_dir),
        "--output-dir",
        str(output_dir),
        "--cache-root",
        str(cache_root),
    ]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    stdout_lines: list[str] = []
    last_logged_line = ""
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = _clean_console_line(raw_line)
        if not line:
            continue
        if line == last_logged_line:
            continue
        last_logged_line = line
        stdout_lines.append(line)
        if on_log:
            on_log(line)
    result_code = process.wait()
    if result_code != 0:
        detail = "\n".join(stdout_lines).strip() or "unknown error"
        if "couldn't connect to 'https://huggingface.co'" in detail or "Failed to establish a new connection" in detail:
            detail = (
                "Local adapter deployment merge failed because the base model could not be downloaded from "
                "Hugging Face. This first deploy needs internet access to fetch the base weights for "
                f"{hf_base_model}, then it will merge the adapter and create the Ollama model."
            )
        raise RuntimeError(f"Local adapter deployment merge failed: {detail}")


def _ollama_base_to_hf_model(base_model: str) -> str:
    mapping = {
        "llama3.2:3b": "meta-llama/Llama-3.2-3B-Instruct",
        "qwen2.5:1.5b": "Qwen/Qwen2.5-1.5B-Instruct",
        "smollm2:1.7b": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
        "phi3.5:3.8b": "microsoft/Phi-3.5-mini-instruct",
    }
    return mapping.get(base_model, base_model)
