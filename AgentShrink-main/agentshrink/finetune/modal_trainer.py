"""
Modal-backed cloud fine-tuning.

Uses Unsloth for 2x faster training with 70% less VRAM on Modal cloud GPUs.
Modal requires decorated functions to live at module scope, so the remote
training function is defined globally and reused by the dashboard backend.

Based on: https://modal.com/docs/examples/unsloth_finetune
"""

from __future__ import annotations

import os
from typing import Any, Callable

try:  # pragma: no cover - optional dependency
    import modal
except Exception:  # pragma: no cover - optional dependency
    modal = None


# All linear projection layers — best practice per Unsloth / Modal examples
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


if modal is not None:  # pragma: no branch
    modal_app = modal.App("agentshrink-finetune")
    modal_image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "torch>=2.4.0",
            "transformers>=4.48.0",
            "peft>=0.14.0",
            "trl>=0.12.0",
            "bitsandbytes>=0.44.0",
            "datasets>=2.21.0",
            "accelerate>=1.2.0",
        )
    )

    @modal_app.function(
        image=modal_image,
        gpu="A10G",
        timeout=3600,
        memory=16384,
    )
    def modal_train_remote(remote_config: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
        import base64
        from pathlib import Path

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

        base_model = remote_config["base_model"]
        ollama_base_model = remote_config["deploy_base_model"]
        hf_token = remote_config.get("hf_token") or None
        epochs = int(remote_config.get("epochs", 2))
        batch_size = int(remote_config.get("batch_size", 2))
        lr = float(remote_config.get("learning_rate", 2e-4))
        grad_accum = int(remote_config.get("gradient_accumulation_steps", 4))
        lora_r = int(remote_config.get("lora_r", 16))
        max_seq_length = int(remote_config.get("max_seq_length", 512))

        # --- Load tokenizer and format with chat template ---
        tokenizer = AutoTokenizer.from_pretrained(
            base_model, token=hf_token, trust_remote_code=True
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        conversations = []
        for row in rows:
            conversations.append({
                "conversations": [
                    {"role": "user", "content": row["prompt"]},
                    {"role": "assistant", "content": row["completion"]},
                ]
            })

        def _apply_chat_template(example):
            text = tokenizer.apply_chat_template(
                example["conversations"],
                tokenize=False,
                add_generation_prompt=False,
            )
            return {"text": text}

        dataset = Dataset.from_list(conversations)
        dataset = dataset.map(_apply_chat_template, remove_columns=["conversations"])

        # --- Load model with 4-bit quantization ---
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=bnb_config,
            device_map="auto",
            token=hf_token,
            trust_remote_code=True,
        )

        # --- Apply LoRA to ALL linear layers ---
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

        metrics_log: list[dict[str, Any]] = []

        class MetricsCallback(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs and "loss" in logs:
                    metrics_log.append({
                        "step": state.global_step,
                        "epoch": round(state.epoch or 0, 2),
                        "loss": round(float(logs["loss"]), 4),
                    })

        out_dir = Path("/tmp/adapter")
        out_dir.mkdir(parents=True, exist_ok=True)

        use_bf16 = torch.cuda.is_bf16_supported()
        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=dataset,
            args=SFTConfig(
                output_dir="/tmp/checkpoints",
                dataset_text_field="text",
                max_length=max_seq_length,
                packing=False,
                num_train_epochs=epochs,
                per_device_train_batch_size=batch_size,
                gradient_accumulation_steps=grad_accum,
                learning_rate=lr,
                optim="adamw_8bit",
                warmup_steps=5,
                fp16=not use_bf16,
                bf16=use_bf16,
                gradient_checkpointing=True,
                logging_steps=1,
                save_strategy="no",
                report_to="none",
            ),
            callbacks=[MetricsCallback()],
        )
        trainer.train()
        model.save_pretrained(str(out_dir))
        tokenizer.save_pretrained(str(out_dir))

        artifacts: dict[str, str] = {}
        for file in out_dir.iterdir():
            if file.is_file():
                artifacts[file.name] = base64.b64encode(file.read_bytes()).decode("utf-8")

        return {
            "success": True,
            "metrics": metrics_log,
            "artifacts": artifacts,
            "artifact_kind": "adapter",
            "deploy_base_model": ollama_base_model,
        }


def run_modal_training(
    config: dict[str, Any],
    training_rows: list[dict[str, str]],
    *,
    on_status: Callable[[str, int], None] | None = None,
    on_log: Callable[[str], None] | None = None,
    on_call: Callable[[Any], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if modal is None:
        raise RuntimeError("Modal dependency not installed. Run: pip install modal")

    token_id = os.getenv("MODAL_TOKEN_ID", "").strip()
    token_secret = os.getenv("MODAL_TOKEN_SECRET", "").strip()
    if not token_id or not token_secret:
        raise RuntimeError("Modal credentials are missing. Add MODAL_TOKEN_ID and MODAL_TOKEN_SECRET in .env.")

    if on_status:
        on_status("Preparing Modal training image...", 20)
    if on_log:
        on_log("Connecting to Modal and dispatching remote training job on A10G GPU...")

    remote_config = dict(config)
    remote_config.setdefault("gpu", "A10G")
    remote_config.setdefault("timeout_seconds", 3600)
    remote_config.setdefault("memory_mb", 16384)

    if on_status:
        on_status("Training on Modal GPU...", 45)

    with modal_app.run():
        call = modal_train_remote.spawn(remote_config, training_rows)
        if on_call:
            on_call(call)
        while True:
            if should_stop and should_stop():
                try:
                    call.cancel(terminate_containers=True)
                except Exception:
                    pass
                raise RuntimeError("Training stopped by user.")
            try:
                result = call.get(timeout=5)
                break
            except TimeoutError:
                if on_log:
                    on_log("Modal training still running...")
                continue

    if on_status:
        on_status("Downloading trained artifacts from Modal...", 80)
    if on_log:
        on_log(f"Modal training finished with {len(result.get('metrics', []))} metric updates.")

    return result
