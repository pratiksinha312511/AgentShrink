"""
Modal-backed cloud fine-tuning.

Modal requires decorated functions to live at module scope, so the remote
training function is defined globally and reused by the dashboard backend.
"""

from __future__ import annotations

import os
from typing import Any, Callable

try:  # pragma: no cover - optional dependency
    import modal
except Exception:  # pragma: no cover - optional dependency
    modal = None


if modal is not None:  # pragma: no branch
    modal_app = modal.App("agentshrink-finetune")
    modal_image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "torch==2.3.0",
            "transformers==4.44.0",
            "peft==0.12.0",
            "trl==0.10.1",
            "bitsandbytes==0.43.3",
            "datasets==2.21.0",
            "accelerate==0.33.0",
            "python-dotenv==1.0.1",
            "rich==13.8.1",
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
            TrainingArguments,
        )
        from trl import SFTTrainer

        base_model = remote_config["base_model"]
        ollama_base_model = remote_config["deploy_base_model"]
        hf_token = remote_config.get("hf_token") or None
        epochs = int(remote_config.get("epochs", 2))
        batch_size = int(remote_config.get("batch_size", 2))
        lr = float(remote_config.get("learning_rate", 2e-4))
        lora_r = int(remote_config.get("lora_r", 16))
        max_seq_length = int(remote_config.get("max_seq_length", 512))

        dataset = Dataset.from_dict({
            "text": [
                f"### Input:\n{row['prompt']}\n\n### Response:\n{row['completion']}"
                for row in rows
            ]
        })

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(base_model, token=hf_token)
        tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=bnb_config,
            device_map="auto",
            token=hf_token,
        )
        model = get_peft_model(
            model,
            LoraConfig(
                r=lora_r,
                lora_alpha=lora_r * 2,
                target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
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
        trainer = SFTTrainer(
            model=model,
            args=TrainingArguments(
                output_dir="/tmp/checkpoints",
                num_train_epochs=epochs,
                per_device_train_batch_size=batch_size,
                gradient_accumulation_steps=4,
                learning_rate=lr,
                fp16=True,
                logging_steps=1,
                save_strategy="no",
                report_to="none",
            ),
            train_dataset=dataset,
            tokenizer=tokenizer,
            dataset_text_field="text",
            max_seq_length=max_seq_length,
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
        on_log("Connecting to Modal and dispatching remote training job...")

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
