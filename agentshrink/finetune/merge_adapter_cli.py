from __future__ import annotations

import argparse
import os
import pathlib


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge a PEFT adapter into its base model.")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cache-root", required=True)
    args = parser.parse_args()

    cache_root = pathlib.Path(args.cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(cache_root)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache_root / "hub")
    os.environ["TRANSFORMERS_CACHE"] = str(cache_root / "transformers")
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "1800")

    import torch
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer

    adapter_dir = pathlib.Path(args.adapter_dir)
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading adapter from {adapter_dir}", flush=True)
    print(f"Using Hugging Face cache root {cache_root}", flush=True)
    print(
        f"HF transfer settings: disable_xet={os.environ.get('HF_HUB_DISABLE_XET')} "
        f"etag_timeout={os.environ.get('HF_HUB_ETAG_TIMEOUT')} "
        f"download_timeout={os.environ.get('HF_HUB_DOWNLOAD_TIMEOUT')}",
        flush=True,
    )
    model = AutoPeftModelForCausalLM.from_pretrained(
        str(adapter_dir),
        low_cpu_mem_usage=True,
        torch_dtype="auto",
    )
    print("Merging adapter into base model", flush=True)
    merged = model.merge_and_unload()
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    print(f"Saving merged model to {output_dir}", flush=True)
    merged.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))
    print("Merge complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
