from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable


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
            DataCollatorForLanguageModeling,
            Trainer,
            TrainerCallback,
            TrainingArguments,
        )
    except Exception as exc:  # pragma: no cover - depends on optional local deps
        raise RuntimeError(
            "Local fine-tuning dependencies are missing. Install them with "
            "`venv\\Scripts\\python.exe -m pip install -r dashboard\\backend\\requirements-finetune.txt`, "
            "then restart the AgentShrink backend/stack. "
            f"Import detail: {type(exc).__name__}: {exc}"
        ) from exc

    out_dir = Path(config["artifact_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    adapter_dir = out_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    base_model = config["base_model"]
    deploy_base_model = config["deploy_base_model"]
    epochs = int(config.get("epochs", 2))
    batch_size = int(config.get("batch_size", 1))
    lr = float(config.get("learning_rate", 2e-4))
    grad_accum = int(config.get("gradient_accumulation_steps", 8))
    lora_r = int(config.get("lora_r", 16))
    max_seq_length = int(config.get("max_seq_length", 512))

    if on_status:
        on_status("Preparing local fine-tune dataset", 15)
    if on_log:
        on_log(
            "Starting local LoRA training. This uses local compute and can be slow on CPU-only machines."
        )
        on_log(f"Preparing {len(training_rows)} training rows for local SFT.")

    dataset = Dataset.from_dict(
        {
            "text": [
                f"### Input:\n{row['prompt']}\n\n### Response:\n{row['completion']}"
                for row in training_rows
            ]
        }
    )

    if should_stop and should_stop():
        raise RuntimeError("Training stopped by user.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if on_log:
        on_log(f"Detected training device: {device}")
        if device != "cuda":
            on_log(
                "No CUDA GPU detected. Local training will still run, but Llama 3.2 3B may be very slow and memory-heavy."
            )

    token = (hf_token or config.get("hf_token") or os.environ.get("HF_TOKEN") or "").strip() or None

    # Respect SSL bypass for corporate proxies
    if os.environ.get("HF_HUB_DISABLE_SSL_VERIFY") == "1":
        os.environ.setdefault("CURL_CA_BUNDLE", "")
        os.environ.setdefault("REQUESTS_CA_BUNDLE", "")

    if on_status:
        on_status("Loading tokenizer", 22)
    if on_log:
        on_log(f"Loading tokenizer for {base_model}")

    try:
        tokenizer = AutoTokenizer.from_pretrained(base_model, token=token, trust_remote_code=True)
    except Exception as tok_err:
        err_msg = str(tok_err)
        if "gated" in err_msg.lower() or "access" in err_msg.lower() or "config.json" in err_msg.lower():
            raise RuntimeError(
                f"Cannot download model '{base_model}'. This may be a gated model requiring "
                f"HuggingFace access approval. Try a non-gated model like 'Qwen/Qwen2.5-1.5B-Instruct' "
                f"or 'HuggingFaceTB/SmolLM2-1.7B-Instruct' instead. Detail: {err_msg}"
            ) from tok_err
        raise
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if on_status:
        on_status("Loading base model", 30)
    if on_log:
        on_log(f"Loading base model weights for {base_model}")
    try:
        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            token=token,
            low_cpu_mem_usage=True,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            trust_remote_code=True,
        )
    except Exception as model_err:
        err_msg = str(model_err)
        if "gated" in err_msg.lower() or "access" in err_msg.lower() or "config.json" in err_msg.lower():
            raise RuntimeError(
                f"Cannot download model '{base_model}'. Try a non-gated model like "
                f"'Qwen/Qwen2.5-1.5B-Instruct' or 'HuggingFaceTB/SmolLM2-1.7B-Instruct'. "
                f"Detail: {err_msg}"
            ) from model_err
        raise
    if device == "cuda":
        model = model.to("cuda")

    target_modules = _infer_target_modules(base_model)
    if on_status:
        on_status("Applying LoRA adapters", 38)
    if on_log:
        on_log(f"Applying LoRA to target modules: {', '.join(target_modules)}")
    model = get_peft_model(
        model,
        LoraConfig(
            r=lora_r,
            lora_alpha=lora_r * 2,
            target_modules=target_modules,
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        ),
    )

    def tokenize(batch: dict[str, list[str]]) -> dict[str, Any]:
        encoded = tokenizer(
            batch["text"],
            truncation=True,
            padding="max_length",
            max_length=max_seq_length,
        )
        encoded["labels"] = [ids[:] for ids in encoded["input_ids"]]
        return encoded

    if on_status:
        on_status("Tokenizing training dataset", 42)
    if on_log:
        on_log("Tokenizing prompts and completions for supervised fine-tuning")
    tokenized_dataset = dataset.map(tokenize, batched=True, remove_columns=["text"])

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
            f"Trainer configured with epochs={epochs}, batch_size={batch_size}, gradient_accumulation={grad_accum}, learning_rate={lr}"
        )

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(out_dir / "checkpoints"),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            learning_rate=lr,
            logging_steps=1,
            save_strategy="no",
            report_to="none",
            fp16=device == "cuda",
            bf16=False,
            remove_unused_columns=False,
        ),
        train_dataset=tokenized_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
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


def _infer_target_modules(base_model: str) -> list[str]:
    model_name = base_model.lower()
    if "phi" in model_name:
        return ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    return ["q_proj", "k_proj", "v_proj", "o_proj"]
