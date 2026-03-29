import json
import os
import pathlib
import time
import uuid


CATALOG_FILENAME = "models_catalog.json"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _default_model_entries() -> list[dict]:
    entries: list[dict] = []

    target_provider = os.getenv("TARGET_AGENT_PROVIDER", "openai").strip().lower()
    target_openai_model = os.getenv("TARGET_AGENT_OPENAI_MODEL", "gpt-4o-mini")
    target_nvidia_model = os.getenv("TARGET_AGENT_NVIDIA_MODEL", "moonshotai/kimi-k2-instruct")
    target_gemini_model = os.getenv("TARGET_AGENT_GEMINI_MODEL", "gemini-2.0-flash-lite")
    target_ollama_model = os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b")

    entries.append({
        "id": "local-default",
        "provider": "ollama",
        "model_name": target_ollama_model,
        "display_name": f"Local ({target_ollama_model})",
        "enabled": True,
        "candidate_enabled": True,
        "judge_eligible": True,
        "local": True,
        "supports": ["simple", "general"],
        "quality_tier": 2,
        "cost_in_per_1k": 0.0,
        "cost_out_per_1k": 0.0,
        "source": "default",
    })

    default_remote = {
        "openai": {
            "model_name": target_openai_model,
            "display_name": f"OpenAI ({target_openai_model})",
            "quality_tier": 5,
            "cost_in_per_1k": _env_float("AGENTSHRINK_PRICE_IN_PER_1K", 0.00015 if "mini" in target_openai_model else 0.0025),
            "cost_out_per_1k": _env_float("AGENTSHRINK_PRICE_OUT_PER_1K", 0.0006 if "mini" in target_openai_model else 0.010),
        },
        "nvidia": {
            "model_name": target_nvidia_model,
            "display_name": f"NVIDIA ({target_nvidia_model})",
            "quality_tier": 5,
            "cost_in_per_1k": _env_float("AGENTSHRINK_PRICE_IN_PER_1K", 0.00014),
            "cost_out_per_1k": _env_float("AGENTSHRINK_PRICE_OUT_PER_1K", 0.00056),
        },
        "gemini": {
            "model_name": target_gemini_model,
            "display_name": f"Gemini ({target_gemini_model})",
            "quality_tier": 4,
            "cost_in_per_1k": _env_float("AGENTSHRINK_PRICE_IN_PER_1K", 0.000075),
            "cost_out_per_1k": _env_float("AGENTSHRINK_PRICE_OUT_PER_1K", 0.0003),
        },
    }.get(target_provider, {
        "model_name": target_openai_model,
        "display_name": f"OpenAI ({target_openai_model})",
        "quality_tier": 5,
        "cost_in_per_1k": 0.00015,
        "cost_out_per_1k": 0.0006,
    })

    entries.append({
        "id": "primary-default",
        "provider": target_provider if target_provider in {"openai", "nvidia", "gemini"} else "openai",
        "enabled": True,
        "candidate_enabled": True,
        "judge_eligible": True,
        "local": False,
        "supports": ["simple", "reasoning", "writing", "general"],
        "source": "default",
        **default_remote,
    })

    return entries


def default_costs_for_model(provider: str, model_name: str) -> tuple[float, float]:
    provider = provider.strip().lower()
    model_name = model_name.strip().lower()

    if provider == "ollama":
        return 0.0, 0.0
    if provider == "nvidia":
        return 0.00014, 0.00056
    if provider == "gemini":
        if "flash-lite" in model_name:
            return 0.000075, 0.0003
        if "flash" in model_name:
            return 0.0003, 0.0025
    if provider == "anthropic":
        if "haiku" in model_name:
            return 0.0008, 0.004
        if "sonnet" in model_name:
            return 0.003, 0.015
    if provider == "openai":
        if "mini" in model_name:
            return 0.00015, 0.0006
        if "4o" in model_name:
            return 0.0025, 0.010
    return 0.001, 0.002


def normalize_model_entry(entry: dict) -> dict:
    provider = str(entry.get("provider", "ollama")).strip().lower()
    model_name = str(entry.get("model_name", "")).strip()
    display_name = str(entry.get("display_name", model_name or provider)).strip() or model_name or provider
    supports = entry.get("supports") or ["general"]
    if isinstance(supports, str):
        supports = [item.strip() for item in supports.split(",") if item.strip()]
    supports = [str(item).strip().lower() for item in supports if str(item).strip()]
    if not supports:
        supports = ["general"]

    default_in, default_out = default_costs_for_model(provider, model_name)
    return {
        "id": str(entry.get("id") or uuid.uuid4().hex[:12]),
        "provider": provider,
        "model_name": model_name,
        "display_name": display_name,
        "enabled": bool(entry.get("enabled", True)),
        "candidate_enabled": bool(entry.get("candidate_enabled", entry.get("enabled", True))),
        "judge_eligible": bool(entry.get("judge_eligible", True)),
        "local": bool(entry.get("local", provider == "ollama")),
        "supports": supports,
        "quality_tier": int(entry.get("quality_tier", 3)),
        "cost_in_per_1k": float(entry.get("cost_in_per_1k", default_in)),
        "cost_out_per_1k": float(entry.get("cost_out_per_1k", default_out)),
        "source": str(entry.get("source", "user")),
    }


def catalog_path(output_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(output_dir) / CATALOG_FILENAME


def default_catalog() -> dict:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "version": 1,
        "updated_at": now,
        "models": [normalize_model_entry(entry) for entry in _default_model_entries()],
    }


def load_model_catalog(output_dir: pathlib.Path) -> dict:
    path = catalog_path(output_dir)
    if not path.exists():
        catalog = default_catalog()
        save_model_catalog(output_dir, catalog)
        return catalog

    with open(path, encoding="utf-8") as f:
        saved = json.load(f)

    catalog = {
        "version": int(saved.get("version", 1)),
        "updated_at": saved.get("updated_at"),
        "models": [normalize_model_entry(entry) for entry in saved.get("models", [])],
    }
    if not catalog["models"]:
        catalog = default_catalog()
        save_model_catalog(output_dir, catalog)
    return catalog


def save_model_catalog(output_dir: pathlib.Path, catalog: dict) -> dict:
    path = catalog_path(output_dir)
    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
    normalized = {
        "version": int(catalog.get("version", 1)),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models": [normalize_model_entry(entry) for entry in catalog.get("models", [])],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2)
    return normalized


def upsert_model(output_dir: pathlib.Path, entry: dict) -> dict:
    catalog = load_model_catalog(output_dir)
    normalized = normalize_model_entry(entry)
    models = [model for model in catalog["models"] if model["id"] != normalized["id"]]
    models.append(normalized)
    catalog["models"] = sorted(models, key=lambda model: (not model["enabled"], model["display_name"].lower()))
    return save_model_catalog(output_dir, catalog)


def delete_model(output_dir: pathlib.Path, model_id: str) -> dict:
    catalog = load_model_catalog(output_dir)
    catalog["models"] = [model for model in catalog["models"] if model["id"] != model_id]
    return save_model_catalog(output_dir, catalog)


def cluster_task_kind(cluster_meta: dict) -> str:
    node_dist = cluster_meta.get("node_distribution", {}) or {}
    dominant = max(node_dist.items(), key=lambda kv: kv[1])[0].lower() if node_dist else ""
    if any(token in dominant for token in ("classify", "extract", "format")):
        return "simple"
    if "draft_reply" in dominant:
        return "writing"
    if "check_policy" in dominant:
        return "reasoning"
    return "general"


def _min_quality_for_task(task_kind: str) -> int:
    return {
        "simple": 1,
        "general": 2,
        "writing": 4,
        "reasoning": 4,
    }.get(task_kind, 2)


def _blended_cost(model: dict) -> float:
    return float(model.get("cost_in_per_1k", 0.0)) + float(model.get("cost_out_per_1k", 0.0))


def selection_score(
    evaluation_score: float,
    quality_tier: int,
    cost_in_per_1k: float,
    cost_out_per_1k: float,
    max_cost_reference: float,
) -> float:
    quality_component = max(0.0, min(int(quality_tier), 5)) / 5
    cost_total = float(cost_in_per_1k) + float(cost_out_per_1k)
    if max_cost_reference <= 0:
        cost_component = 1.0
    else:
        cost_component = max(0.0, min(1.0, 1.0 - (cost_total / max_cost_reference)))
    return round(evaluation_score * 0.7 + quality_component * 0.2 + cost_component * 0.1, 4)


def choose_best_model(cluster_meta: dict, catalog: dict) -> dict | None:
    task_kind = cluster_task_kind(cluster_meta)
    min_quality = _min_quality_for_task(task_kind)

    enabled = [model for model in catalog.get("models", []) if model.get("enabled")]
    enabled = [model for model in enabled if model.get("candidate_enabled", True)]
    candidates = [
        model for model in enabled
        if ("general" in model.get("supports", []) or task_kind in model.get("supports", []))
        and int(model.get("quality_tier", 0)) >= min_quality
    ]
    if not candidates:
        candidates = [
            model for model in enabled
            if int(model.get("quality_tier", 0)) >= min_quality
        ]
    if not candidates:
        return None

    return min(
        candidates,
        key=lambda model: (
            _blended_cost(model),
            not bool(model.get("local")),
            -int(model.get("quality_tier", 0)),
            model.get("display_name", model.get("model_name", "")),
        ),
    )
