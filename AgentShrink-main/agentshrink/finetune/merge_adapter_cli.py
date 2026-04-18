from __future__ import annotations

import argparse
import os
import pathlib
import ssl
import sys

# Fix TRL encoding bug on Windows
if sys.platform == "win32":
    _orig_read_text = pathlib.Path.read_text

    def _read_text_utf8(self, *args, encoding=None, errors=None, **kwargs):
        return _orig_read_text(self, *args, encoding=encoding or "utf-8", errors=errors, **kwargs)

    pathlib.Path.read_text = _read_text_utf8  # type: ignore[assignment]

# Fix SSL for corporate proxies — httpx ignores HF_HUB_DISABLE_SSL_VERIFY
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
        trust_remote_code=True,
    )
    print("Merging adapter into base model", flush=True)
    merged = model.merge_and_unload()
    # Load tokenizer from adapter dir (saved during training) to avoid
    # needing HF auth for gated models like Llama.
    tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir), trust_remote_code=False)
    print(f"Saving merged model to {output_dir}", flush=True)
    merged.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))
    print("Merge complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
