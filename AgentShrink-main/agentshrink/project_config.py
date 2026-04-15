import json
import pathlib


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "agentshrink.config.json"

DEFAULT_CONFIG = {
    "eval_samples_per_cluster": 10,
    "judge_model_id": None,
    "remote_min_interval_s": 0.75,
    "judge_min_interval_s": 1.0,
}


def load_project_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        loaded = json.load(f)

    config = dict(DEFAULT_CONFIG)
    if isinstance(loaded, dict):
        config.update(loaded)
    return config


def get_eval_samples_per_cluster() -> int:
    raw = load_project_config().get("eval_samples_per_cluster", DEFAULT_CONFIG["eval_samples_per_cluster"])
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_CONFIG["eval_samples_per_cluster"]
    return max(1, value)


def get_judge_model_id() -> str | None:
    value = load_project_config().get("judge_model_id", DEFAULT_CONFIG["judge_model_id"])
    return value if isinstance(value, str) and value.strip() else None


def get_remote_min_interval_s() -> float:
    raw = load_project_config().get("remote_min_interval_s", DEFAULT_CONFIG["remote_min_interval_s"])
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = DEFAULT_CONFIG["remote_min_interval_s"]
    return max(0.0, value)


def get_judge_min_interval_s() -> float:
    raw = load_project_config().get("judge_min_interval_s", DEFAULT_CONFIG["judge_min_interval_s"])
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = DEFAULT_CONFIG["judge_min_interval_s"]
    return max(0.0, value)


def save_project_config(updates: dict) -> dict:
    config = load_project_config()
    config.update(updates or {})
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return config
