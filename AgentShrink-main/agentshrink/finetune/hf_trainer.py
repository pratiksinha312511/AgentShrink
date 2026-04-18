"""
HuggingFace-backed fine-tuning runner.

Uses HuggingFace Transformers + TRL SFTTrainer directly (not autotrain-advanced)
with proper chat template formatting. Trains locally and saves adapter artifacts.
Optionally pushes to HuggingFace Hub if HF_TOKEN has write access.
"""

from __future__ import annotations

import os
import ssl
import sys
from pathlib import Path
from typing import Any, Callable

# Fix TRL encoding bug on Windows — trl reads deepseekv3.jinja via
# Path.read_text() without encoding, which defaults to cp1252 on Windows.
# Monkey-patch so the default is utf-8 instead.
if sys.platform == "win32":
    _orig_read_text = Path.read_text

    def _read_text_utf8(self, *args, encoding=None, errors=None, **kwargs):
        return _orig_read_text(self, *args, encoding=encoding or "utf-8", errors=errors, **kwargs)

    Path.read_text = _read_text_utf8  # type: ignore[assignment]

# Fix SSL for corporate proxies — httpx (used by huggingface_hub >=1.x) ignores
# HF_HUB_DISABLE_SSL_VERIFY.  Monkey-patch ssl so it creates unverified contexts.
if os.environ.get("HF_HUB_DISABLE_SSL_VERIFY") == "1":
    os.environ.setdefault("CURL_CA_BUNDLE", "")
    os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
    _orig_create_default_context = ssl.create_default_context

    def _unverified_context(*args, **kwargs):
        ctx = _orig_create_default_context(*args, **kwargs)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    ssl.create_default_context = _unverified_context  # type: ignore[assignment]

    # Also patch httpx client to disable SSL verification
    try:
        import httpx as _httpx

        _orig_httpx_client_init = _httpx.Client.__init__

        def _patched_client_init(self, *a, **kw):
            kw["verify"] = False
            return _orig_httpx_client_init(self, *a, **kw)

        _httpx.Client.__init__ = _patched_client_init  # type: ignore[assignment]
    except Exception:
        pass


# All linear projection layers — consistent with local and modal trainers
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


def run_hf_training(
    config: dict[str, Any],
    training_rows: list[dict[str, str]],
    *,
    hf_token: str,
    on_status: Callable[[str, int], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    on_metric: Callable[[dict[str, Any]], None] | None = None,
    on_process: Callable[[Any], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainerCallback,
        )
        from trl import SFTConfig, SFTTrainer
    except Exception as exc:
        raise RuntimeError(
            "HuggingFace fine-tuning dependencies are missing. Install them with:\n"
            "  pip install torch datasets peft transformers trl accelerate bitsandbytes huggingface_hub\n"
            f"Import detail: {type(exc).__name__}: {exc}"
        ) from exc

    out_dir = Path(config["artifact_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    adapter_dir = out_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    base_model = config["base_model"]
    deploy_base_model = config["deploy_base_model"]
    epochs = int(config.get("epochs", 2))
    batch_size = int(config.get("batch_size", 2))
    lr = float(config.get("learning_rate", 2e-4))
    grad_accum = int(config.get("gradient_accumulation_steps", 4))
    lora_r = int(config.get("lora_r", 16))
    max_seq_length = int(config.get("max_seq_length", 512))

    if on_status:
        on_status("Preparing HuggingFace training dataset...", 15)
    if on_log:
        on_log(f"Starting HuggingFace SFT training with {len(training_rows)} rows.")

    if should_stop and should_stop():
        raise RuntimeError("Training stopped by user.")

    # --- Load tokenizer ---
    if on_status:
        on_status("Loading tokenizer", 20)

    token = hf_token.strip() if hf_token else None

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            base_model, token=token, trust_remote_code=True
        )
    except Exception as tok_err:
        err_msg = str(tok_err).lower()
        if "gated" in err_msg or "access" in err_msg or "403" in err_msg:
            raise RuntimeError(
                f"Cannot download model '{base_model}'. This may be a gated model. "
                f"Try 'Qwen/Qwen2.5-1.5B-Instruct' instead.\nDetail: {tok_err}"
            ) from tok_err
        if "ssl" in err_msg or "certificate" in err_msg:
            raise RuntimeError(
                f"SSL error downloading model '{base_model}'. If behind a corporate proxy, "
                f"set HF_HUB_DISABLE_SSL_VERIFY=1 in .env.\nDetail: {tok_err}"
            ) from tok_err
        raise
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # --- Build dataset using chat template ---
    if on_status:
        on_status("Formatting dataset with chat template", 25)

    conversations = []
    for row in training_rows:
        conversations.append({
            "conversations": [
                {"role": "user", "content": row["prompt"]},
                {"role": "assistant", "content": row["completion"]},
            ]
        })

    def _apply_chat_template(example: dict) -> dict:
        text = tokenizer.apply_chat_template(
            example["conversations"],
            tokenize=False,
            add_generation_prompt=False,
        )
        return {"text": text}

    dataset = Dataset.from_list(conversations)
    dataset = dataset.map(_apply_chat_template, remove_columns=["conversations"])

    if on_log:
        on_log(f"Chat template applied to {len(dataset)} rows.")

    if should_stop and should_stop():
        raise RuntimeError("Training stopped by user.")

    # --- Load model ---
    if on_status:
        on_status("Loading base model", 30)
    if on_log:
        on_log(f"Loading {base_model} with 4-bit quantization (QLoRA)")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    use_bf16 = device == "cuda" and torch.cuda.is_bf16_supported()
    use_fp16 = device == "cuda" and not use_bf16

    load_kwargs: dict[str, Any] = {
        "token": token,
        "trust_remote_code": True,
        "low_cpu_mem_usage": True,
    }

    # Use 4-bit quantization if CUDA is available
    if device == "cuda":
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16 if use_bf16 else torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        load_kwargs["device_map"] = "auto"
    else:
        load_kwargs["torch_dtype"] = torch.float32

    try:
        model = AutoModelForCausalLM.from_pretrained(base_model, **load_kwargs)
    except Exception as model_err:
        err_msg = str(model_err).lower()
        if "gated" in err_msg or "access" in err_msg or "403" in err_msg:
            raise RuntimeError(
                f"Cannot download model '{base_model}'. This may be a gated model. "
                f"Try 'Qwen/Qwen2.5-1.5B-Instruct' instead.\nDetail: {model_err}"
            ) from model_err
        if "ssl" in err_msg or "certificate" in err_msg:
            raise RuntimeError(
                f"SSL error downloading model '{base_model}'. If behind a corporate proxy, "
                f"set HF_HUB_DISABLE_SSL_VERIFY=1 in .env.\nDetail: {model_err}"
            ) from model_err
        raise

    # --- Apply LoRA ---
    if on_status:
        on_status("Applying LoRA adapters", 38)
    if on_log:
        on_log(f"LoRA r={lora_r}, targeting ALL linear layers")

    model = get_peft_model(
        model,
        LoraConfig(
            r=lora_r,
            lora_alpha=lora_r * 2,
            target_modules=LORA_TARGET_MODULES,
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        ),
    )

    # --- Train ---
    metrics: list[dict[str, Any]] = []

    class MetricsCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if not logs or "loss" not in logs:
                return
            metric = {
                "step": int(state.global_step or len(metrics) + 1),
                "epoch": round(float(state.epoch or 0), 2),
                "loss": round(float(logs["loss"]), 4),
            }
            metrics.append(metric)
            if on_metric:
                on_metric(metric)
            if on_log:
                on_log(f"step={metric['step']} epoch={metric['epoch']} loss={metric['loss']}")
            if should_stop and should_stop():
                control.should_training_stop = True

        def on_step_end(self, args, state, control, **kwargs):
            if should_stop and should_stop():
                control.should_training_stop = True

    optim_name = "adamw_8bit" if device == "cuda" else "adamw_torch"
    use_grad_ckpt = device == "cuda"

    if on_status:
        on_status("Training on HuggingFace backend...", 45)
    if on_log:
        on_log(
            f"SFTTrainer: epochs={epochs}, batch={batch_size}, grad_accum={grad_accum}, "
            f"lr={lr}, optim={optim_name}, bf16={use_bf16}"
        )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        peft_config=None,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=max_seq_length,
            packing=False,
            output_dir=str(out_dir / "checkpoints"),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            learning_rate=lr,
            optim=optim_name,
            warmup_steps=5,
            logging_steps=1,
            save_strategy="no",
            report_to="none",
            fp16=use_fp16,
            bf16=use_bf16,
            gradient_checkpointing=use_grad_ckpt,
            remove_unused_columns=False,
        ),
        callbacks=[MetricsCallback()],
    )
    trainer.train()

    if should_stop and should_stop():
        raise RuntimeError("Training stopped by user.")

    # --- Save adapter ---
    if on_status:
        on_status("Saving adapter artifacts...", 80)
    if on_log:
        on_log("Saving trained adapter to disk.")

    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    # --- Optionally push to Hub ---
    if token:
        try:
            from huggingface_hub import HfApi
            api = HfApi(token=token)
            user_info = api.whoami()
            username = user_info.get("name", "agentshrink")
            import time
            repo_id = f"{username}/agentshrink-cluster-{config.get('cluster_id', 0)}-{int(time.time())}"
            if on_log:
                on_log(f"Pushing adapter to HuggingFace Hub: {repo_id}")
            model.push_to_hub(repo_id, token=token, private=True)
            tokenizer.push_to_hub(repo_id, token=token, private=True)
            if on_log:
                on_log(f"Adapter pushed to https://huggingface.co/{repo_id}")
        except Exception as hub_err:
            if on_log:
                on_log(f"Hub push skipped (non-fatal): {hub_err}")

    if on_status:
        on_status("HuggingFace training complete", 85)

    return {
        "success": True,
        "metrics": metrics,
        "artifact_kind": "adapter",
        "artifact_dir": str(adapter_dir),
        "deploy_base_model": deploy_base_model,
    }
