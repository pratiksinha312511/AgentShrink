from __future__ import annotations

import json
import os
import pathlib
import secrets
import shutil
import urllib.request
from dataclasses import dataclass


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / ".agentshrink"
PRODUCT_CONFIG_PATH = STATE_DIR / "project.json"
RUNTIME_STATE_PATH = STATE_DIR / "runtime.json"
RUNTIME_LOG_DIR = STATE_DIR / "logs"


DEFAULT_PRODUCT_CONFIG = {
    "project_name": "AgentShrink Project",
    "db_path": str((PROJECT_ROOT / ".agentshrink_output" / "gateway_demo.db").resolve()),
    "output_dir": str((PROJECT_ROOT / ".agentshrink_output").resolve()),
    "gateway": {
        "host": "127.0.0.1",
        "port": 8100,
        "upstream_provider": "mock",
    },
    "dashboard_backend": {
        "host": "127.0.0.1",
        "port": 8000,
    },
    "dashboard_frontend": {
        "port": 3000,
    },
    "defaults": {
        "gateway_model": "mock-model",
        "gateway_api_key": "agentshrink-local",
        "confidence_threshold": 0.75,
    },
}


def generate_project_token() -> str:
    return f"as_live_{secrets.token_urlsafe(18)}"


def ensure_state_dir() -> pathlib.Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def load_product_config() -> dict:
    ensure_state_dir()
    if not PRODUCT_CONFIG_PATH.exists():
        return json.loads(json.dumps(DEFAULT_PRODUCT_CONFIG))
    with open(PRODUCT_CONFIG_PATH, encoding="utf-8") as f:
        loaded = json.load(f)
    merged = json.loads(json.dumps(DEFAULT_PRODUCT_CONFIG))
    _deep_update(merged, loaded if isinstance(loaded, dict) else {})
    return merged


def save_product_config(config: dict) -> dict:
    ensure_state_dir()
    merged = json.loads(json.dumps(DEFAULT_PRODUCT_CONFIG))
    _deep_update(merged, config or {})
    with open(PRODUCT_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    return merged


def initialize_product_config(
    *,
    project_name: str | None = None,
    db_path: str | None = None,
    output_dir: str | None = None,
    gateway_port: int | None = None,
    backend_port: int | None = None,
    frontend_port: int | None = None,
    upstream_provider: str | None = None,
) -> dict:
    config = load_product_config()
    if project_name:
        config["project_name"] = project_name
    if db_path:
        config["db_path"] = str(pathlib.Path(db_path).expanduser().resolve())
    if output_dir:
        config["output_dir"] = str(pathlib.Path(output_dir).expanduser().resolve())
    if gateway_port:
        config["gateway"]["port"] = int(gateway_port)
    if backend_port:
        config["dashboard_backend"]["port"] = int(backend_port)
    if frontend_port:
        config["dashboard_frontend"]["port"] = int(frontend_port)
    if upstream_provider:
        config["gateway"]["upstream_provider"] = upstream_provider
    gateway_key = ((config.get("defaults") or {}).get("gateway_api_key") or "").strip()
    if not gateway_key or gateway_key == "agentshrink-local":
        config.setdefault("defaults", {})
        config["defaults"]["gateway_api_key"] = generate_project_token()

    pathlib.Path(config["db_path"]).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(config["output_dir"]).mkdir(parents=True, exist_ok=True)
    return save_product_config(config)


def _deep_update(base: dict, updates: dict):
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    remedy: str = ""
    category: str = "general"
    severity: str = "info"
    commands: list[str] | None = None


def run_doctor_checks() -> list[DoctorCheck]:
    config = load_product_config()
    checks: list[DoctorCheck] = []
    upstream_provider = ((config.get("gateway") or {}).get("upstream_provider") or "mock").strip().lower()

    checks.append(
        DoctorCheck(
            name="project_config",
            ok=PRODUCT_CONFIG_PATH.exists(),
            detail=str(PRODUCT_CONFIG_PATH if PRODUCT_CONFIG_PATH.exists() else "Run `agentshrink init` first."),
            remedy="Create a local AgentShrink project manifest with `agentshrink init`." if not PRODUCT_CONFIG_PATH.exists() else "",
            category="project",
            severity="error" if not PRODUCT_CONFIG_PATH.exists() else "info",
            commands=["venv\\Scripts\\python.exe -m agentshrink.cli init"] if not PRODUCT_CONFIG_PATH.exists() else [],
        )
    )

    db_path = pathlib.Path(config["db_path"])
    output_dir = pathlib.Path(config["output_dir"])
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ok = os.access(db_path.parent, os.W_OK)
        checks.append(DoctorCheck("db_directory", ok, str(db_path.parent), "" if ok else "Choose a writable database directory in Settings.", "storage", "info" if ok else "error"))
    except Exception as exc:
        checks.append(DoctorCheck("db_directory", False, str(exc), "Choose a writable database directory in Settings.", "storage", "error"))

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        ok = os.access(output_dir, os.W_OK)
        checks.append(DoctorCheck("output_directory", ok, str(output_dir), "" if ok else "Choose a writable output directory in Settings.", "storage", "info" if ok else "error"))
    except Exception as exc:
        checks.append(DoctorCheck("output_directory", False, str(exc), "Choose a writable output directory in Settings.", "storage", "error"))

    python_ok = shutil.which("python") is not None or shutil.which("python.exe") is not None
    npm_ok = shutil.which("npm") is not None or shutil.which("npm.cmd") is not None
    ollama_ok = shutil.which("ollama") is not None or shutil.which("ollama.exe") is not None
    checks.append(DoctorCheck("python", python_ok, "Python available on PATH", "" if python_ok else "Install Python and restart your terminal.", "runtime", "info" if python_ok else "error"))
    checks.append(DoctorCheck("npm", npm_ok, "Needed for dashboard frontend", "" if npm_ok else "Install Node.js/npm so the frontend can run.", "runtime", "info" if npm_ok else "error"))
    checks.append(DoctorCheck("ollama", ollama_ok, "Needed for local-model routing", "" if ollama_ok else "Install Ollama if you want local-model routing.", "provider", "info" if ollama_ok else "warning", ["ollama list"] if ollama_ok else ["ollama --version"]))

    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401

        checks.append(DoctorCheck("backend_deps", True, "FastAPI/Uvicorn import OK", category="runtime", severity="info"))
    except Exception as exc:
        checks.append(DoctorCheck("backend_deps", False, str(exc), "Install backend dependencies from requirements.txt.", "runtime", "error", ["venv\\Scripts\\python.exe -m pip install -r requirements.txt"]))

    try:
        import openai  # noqa: F401
        checks.append(DoctorCheck("openai_sdk", True, "OpenAI SDK import OK", category="runtime", severity="info"))
    except Exception as exc:
        checks.append(DoctorCheck("openai_sdk", False, str(exc), "Install the OpenAI SDK in your environment.", "runtime", "error", ["venv\\Scripts\\python.exe -m pip install openai"]))

    if upstream_provider == "mock":
        checks.append(DoctorCheck("provider_mock_mode", True, "Mock upstream is active. Local testing costs $0.", category="provider", severity="info"))
    elif upstream_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        checks.append(DoctorCheck(
            "provider_openai_key",
            bool(api_key),
            "OPENAI_API_KEY is set" if api_key else "Missing OPENAI_API_KEY for OpenAI upstream",
            "" if api_key else "Add OPENAI_API_KEY to your environment, then restart the stack.",
            "provider",
            "info" if api_key else "error",
            [] if api_key else [
                "$env:OPENAI_API_KEY=\"your_openai_key\"",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack down",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
            ],
        ))
    elif upstream_provider == "nvidia":
        api_key = os.getenv("NVIDIA_API_KEY", "").strip()
        checks.append(DoctorCheck(
            "provider_nvidia_key",
            bool(api_key),
            "NVIDIA_API_KEY is set" if api_key else "Missing NVIDIA_API_KEY for NVIDIA upstream",
            "" if api_key else "Add NVIDIA_API_KEY to your environment, then restart the stack.",
            "provider",
            "info" if api_key else "error",
            [] if api_key else [
                "$env:NVIDIA_API_KEY=\"your_nvidia_key\"",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack down",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
            ],
        ))
    elif upstream_provider == "huggingface":
        hf_token = os.getenv("HF_TOKEN", "").strip()
        checks.append(DoctorCheck(
            "provider_hf_token",
            bool(hf_token),
            "HF_TOKEN is set" if hf_token else "Missing HF_TOKEN for Hugging Face upstream",
            "" if hf_token else "Add HF_TOKEN to your environment. Gated models also require Hugging Face access approval.",
            "provider",
            "info" if hf_token else "error",
            [] if hf_token else [
                "$env:HF_TOKEN=\"your_hf_token\"",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack down",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
            ],
        ))
    elif upstream_provider == "ollama":
        ollama_base = (os.getenv("AGENTSHRINK_GATEWAY_OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        ollama_url = f"{ollama_base}/api/tags"
        try:
            with urllib.request.urlopen(ollama_url, timeout=2.5) as response:
                ok = 200 <= getattr(response, "status", 0) < 300
            checks.append(DoctorCheck(
                "provider_ollama_reachable",
                ok,
                ollama_url,
                "" if ok else f"Start Ollama and confirm {ollama_url} is reachable.",
                "provider",
                "info" if ok else "error",
                ["ollama list"] if ok else [
                    "ollama serve",
                    "Invoke-WebRequest http://localhost:11434/api/tags",
                ],
            ))
        except Exception as exc:
            checks.append(DoctorCheck(
                "provider_ollama_reachable",
                False,
                f"{ollama_url} ({exc})",
                f"Start Ollama and confirm {ollama_url} is reachable.",
                "provider",
                "error",
                [
                    "ollama serve",
                    "Invoke-WebRequest http://localhost:11434/api/tags",
                ],
            ))

    return checks


def load_runtime_state() -> dict:
    ensure_state_dir()
    if not RUNTIME_STATE_PATH.exists():
        return {"services": {}}
    with open(RUNTIME_STATE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"services": {}}
    data.setdefault("services", {})
    return data


def save_runtime_state(state: dict) -> dict:
    ensure_state_dir()
    with open(RUNTIME_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state
