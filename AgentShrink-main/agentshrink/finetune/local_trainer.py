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


# All linear projection layers — best practice per Unsloth / Modal examples.
# Targeting all layers gives best quality; cost is negligible with LoRA.
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


def _format_training_rows_chatml(training_rows: list[dict[str, str]]) -> list[dict]:
    """Convert prompt/completion rows to conversation dicts
    suitable for ``tokenizer.apply_chat_template``."""
    formatted = []
    for row in training_rows:
        formatted.append({
            "conversations": [
                {"role": "user", "content": row["prompt"]},
                {"role": "assistant", "content": row["completion"]},
            ]
        })
    return formatted


def run_local_training(
    config: dict[str, Any],
    training_rows: list[dict[str, str]],
    *,
    hf_token: str | None = None,
    on_status: Callable[[str, int], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    on_metric: Callable[[dict[str, Any]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainerCallback,
        )
        from trl import SFTConfig, SFTTrainer
    except Exception as exc:  # pragma: no cover - depends on optional local deps
        raise RuntimeError(
            "Local fine-tuning dependencies are missing. Install them with:\n"
            "  pip install torch datasets peft transformers trl accelerate bitsandbytes\n"
            "Then restart the AgentShrink backend/stack.\n"
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
        on_status("Preparing local fine-tune dataset", 15)
    if on_log:
        on_log(
            "Starting local LoRA + SFT training with trl.SFTTrainer and chat template formatting."
        )
        on_log(f"Preparing {len(training_rows)} training rows for supervised fine-tuning.")

    if should_stop and should_stop():
        raise RuntimeError("Training stopped by user.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if on_log:
        on_log(f"Detected training device: {device}")
        if device != "cuda":
            on_log(
                "WARNING: No CUDA GPU detected. Training will run on CPU — this will be very slow. "
                "Consider using the Modal.com backend for cloud GPU training instead."
            )

    token = (hf_token or config.get("hf_token") or os.environ.get("HF_TOKEN") or "").strip() or None

    if on_status:
        on_status("Loading tokenizer", 22)
    if on_log:
        on_log(f"Loading tokenizer for {base_model}")

    try:
        tokenizer = AutoTokenizer.from_pretrained(base_model, token=token, trust_remote_code=True)
    except Exception as tok_err:
        err_msg = str(tok_err).lower()
        if "gated" in err_msg or "access" in err_msg or "403" in err_msg or "config.json" in err_msg:
            raise RuntimeError(
                f"Cannot download model '{base_model}'. This may be a gated model requiring "
                f"HuggingFace access approval. Try a non-gated model like 'Qwen/Qwen2.5-1.5B-Instruct' "
                f"or 'HuggingFaceTB/SmolLM2-1.7B-Instruct' instead.\nDetail: {tok_err}"
            ) from tok_err
        if "ssl" in err_msg or "certificate" in err_msg:
            raise RuntimeError(
                f"SSL error downloading model '{base_model}'. If you are behind a corporate proxy, "
                f"set HF_HUB_DISABLE_SSL_VERIFY=1 in your .env file.\nDetail: {tok_err}"
            ) from tok_err
        raise

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # --- Build dataset using chat template ---
    if on_status:
        on_status("Formatting dataset with chat template", 26)

    conversations = _format_training_rows_chatml(training_rows)

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
        sample_text = dataset[0]["text"][:200] if len(dataset) > 0 else "(empty)"
        on_log(f"Chat template applied. Sample: {sample_text}...")

    if should_stop and should_stop():
        raise RuntimeError("Training stopped by user.")

    if on_status:
        on_status("Loading base model", 30)
    if on_log:
        on_log(f"Loading base model weights for {base_model}")

    # Determine precision — prefer bf16 when available
    use_bf16 = device == "cuda" and torch.cuda.is_bf16_supported()
    use_fp16 = device == "cuda" and not use_bf16
    model_dtype = torch.bfloat16 if use_bf16 else (torch.float16 if device == "cuda" else torch.float32)
    use_grad_ckpt = device == "cuda"
    optim_name = "adamw_8bit" if device == "cuda" else "adamw_torch"

    try:
        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            token=token,
            low_cpu_mem_usage=True,
            torch_dtype=model_dtype,
            trust_remote_code=True,
        )
    except Exception as model_err:
        err_msg = str(model_err).lower()
        if "gated" in err_msg or "access" in err_msg or "403" in err_msg or "config.json" in err_msg:
            raise RuntimeError(
                f"Cannot download model '{base_model}'. Try a non-gated model like "
                f"'Qwen/Qwen2.5-1.5B-Instruct' or 'HuggingFaceTB/SmolLM2-1.7B-Instruct'.\n"
                f"Detail: {model_err}"
            ) from model_err
        if "ssl" in err_msg or "certificate" in err_msg:
            raise RuntimeError(
                f"SSL error downloading model '{base_model}'. If you are behind a corporate proxy, "
                f"set HF_HUB_DISABLE_SSL_VERIFY=1 in your .env file.\nDetail: {model_err}"
            ) from model_err
        raise

    if device == "cuda":
        model = model.to("cuda")

    # Enable gradient checkpointing to reduce VRAM usage (~40% reduction) — CUDA only
    if use_grad_ckpt:
        model.gradient_checkpointing_enable()
        if on_log:
            on_log("Gradient checkpointing enabled (reduces VRAM ~40%)")

    if on_status:
        on_status("Applying LoRA adapters", 38)
    if on_log:
        on_log(f"Applying LoRA to ALL linear layers: {', '.join(LORA_TARGET_MODULES)}")

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

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    if on_log:
        on_log(f"Trainable: {trainable_params:,} / {total_params:,} ({100*trainable_params/total_params:.2f}%)")

    metrics_log: list[dict[str, Any]] = []
    last_progress = 45

    class MetricsCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):  # noqa: ANN001
            if not logs or "loss" not in logs:
                return
            metric = {
                "step": int(state.global_step or len(metrics_log) + 1),
                "epoch": round(float(state.epoch or 0), 2),
                "loss": round(float(logs["loss"]), 4),
            }
            metrics_log.append(metric)
            if on_metric:
                on_metric(metric)
            if on_log:
                on_log(
                    f"step={metric['step']} epoch={metric['epoch']} loss={metric['loss']}"
                )
            if should_stop and should_stop():
                control.should_training_stop = True

        def on_step_end(self, args, state, control, **kwargs):  # noqa: ANN001
            nonlocal last_progress
            if should_stop and should_stop():
                control.should_training_stop = True
                return
            if not on_status:
                return
            max_steps = int(getattr(state, "max_steps", 0) or 0)
            current_step = int(getattr(state, "global_step", 0) or 0)
            if max_steps <= 0:
                return
            progress = 45 + int((current_step / max_steps) * 33)
            progress = max(45, min(78, progress))
            if progress > last_progress:
                last_progress = progress
                epoch_value = round(float(state.epoch or 0), 2)
                on_status(f"Training locally · epoch {epoch_value}", progress)

    if on_status:
        on_status("Training locally", 45)
    if on_log:
        on_log(
            f"SFTTrainer: epochs={epochs}, batch={batch_size}, grad_accum={grad_accum}, "
            f"lr={lr}, optim={optim_name}, bf16={use_bf16}, fp16={use_fp16}"
        )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        peft_config=None,  # already applied via get_peft_model
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

    if on_status:
        on_status("Saving local adapter", 82)
    if on_log:
        on_log("Training finished. Saving adapter artifacts to disk.")
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    if on_log:
        on_log(f"Saved local adapter to {adapter_dir}")

    return {
        "success": True,
        "metrics": metrics_log,
        "artifact_kind": "adapter",
        "artifact_dir": str(adapter_dir),
        "deploy_base_model": deploy_base_model,
    }
