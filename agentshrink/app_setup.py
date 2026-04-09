from __future__ import annotations

import json
import os
import pathlib
import secrets
import shutil
import time
import urllib.request
from dataclasses import dataclass

from agentshrink.provider_registry import (
    get_provider_config,
    resolve_provider_api_key,
    resolve_provider_base_url,
)
from agentshrink.provider_runtime import provider_api_version


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / ".agentshrink"
PRODUCT_CONFIG_PATH = STATE_DIR / "project.json"
RUNTIME_STATE_PATH = STATE_DIR / "runtime.json"
RUNTIME_LOG_DIR = STATE_DIR / "logs"
PROJECT_REGISTRY_PATH = STATE_DIR / "projects.json"
SESSION_PATH = STATE_DIR / "session.json"
HOSTED_CONFIG_PATH = STATE_DIR / "hosted.json"
EMAIL_OUTBOX_DIR = STATE_DIR / "emails"
HOSTED_TENANTS_DIR = PROJECT_ROOT / ".agentshrink_hosted" / "tenants"


DEFAULT_PRODUCT_CONFIG = {
    "account": {
        "id": "acct_local_default",
        "name": "Local AgentShrink Workspace",
        "slug": "local-workspace",
    },
    "project": {
        "id": "proj_local_default",
        "name": "AgentShrink Project",
        "slug": "agentshrink-project",
        "environment": "local",
        "team_id": "team_local_default",
    },
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

DEFAULT_HOSTED_CONFIG = {
    "deployment": {
        "mode": "local-hosted",
        "public_app_url": "http://localhost:3000",
        "public_api_url": "http://127.0.0.1:8000",
        "gateway_url": "http://127.0.0.1:8100/v1",
    },
    "auth": {
        "mode": "session",
        "provider": "local-session",
        "allow_self_signup": True,
        "auth0": {
            "domain": "",
            "client_id": "",
            "client_secret": "",
            "audience": "",
            "redirect_path": "/auth",
        },
    },
    "billing": {
        "provider": "manual",
        "plan": "beta",
        "currency": "USD",
        "seat_price_usd": 0.0,
        "usage_price_per_1k_calls_usd": 0.0,
        "stripe": {
            "secret_key": "",
            "price_id": "",
            "success_path": "/billing",
            "cancel_path": "/billing",
        },
    },
    "tenancy": {
        "isolation_mode": "team-scoped",
        "project_token_scope": "project",
    },
}

ROLE_RANK = {
    "viewer": 10,
    "member": 20,
    "admin": 30,
    "owner": 40,
}


def generate_project_token() -> str:
    return f"as_live_{secrets.token_urlsafe(18)}"


def ensure_state_dir() -> pathlib.Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
    EMAIL_OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    HOSTED_TENANTS_DIR.mkdir(parents=True, exist_ok=True)
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


def load_hosted_config() -> dict:
    ensure_state_dir()
    if not HOSTED_CONFIG_PATH.exists():
        return json.loads(json.dumps(DEFAULT_HOSTED_CONFIG))
    with open(HOSTED_CONFIG_PATH, encoding="utf-8") as f:
        loaded = json.load(f)
    merged = json.loads(json.dumps(DEFAULT_HOSTED_CONFIG))
    _deep_update(merged, loaded if isinstance(loaded, dict) else {})
    return merged


def save_hosted_config(config: dict) -> dict:
    ensure_state_dir()
    merged = json.loads(json.dumps(DEFAULT_HOSTED_CONFIG))
    _deep_update(merged, config or {})
    with open(HOSTED_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    return merged


def tenant_storage_root(tenant_id: str) -> pathlib.Path:
    ensure_state_dir()
    safe = _slugify(tenant_id) or "tenant-local-default"
    root = HOSTED_TENANTS_DIR / safe
    root.mkdir(parents=True, exist_ok=True)
    return root


def tenant_billing_ledger_path(tenant_id: str) -> pathlib.Path:
    return tenant_storage_root(tenant_id) / "billing_ledger.json"


def load_tenant_billing_ledger(tenant_id: str) -> dict:
    path = tenant_billing_ledger_path(tenant_id)
    if not path.exists():
        return {
            "tenant_id": tenant_id,
            "currency": "USD",
            "entries": [],
            "last_synced_at": None,
        }
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"tenant_id": tenant_id, "currency": "USD", "entries": [], "last_synced_at": None}
    data.setdefault("tenant_id", tenant_id)
    data.setdefault("currency", "USD")
    data.setdefault("entries", [])
    data.setdefault("last_synced_at", None)
    return data


def save_tenant_billing_ledger(tenant_id: str, ledger: dict) -> dict:
    path = tenant_billing_ledger_path(tenant_id)
    merged = load_tenant_billing_ledger(tenant_id)
    _deep_update(merged, ledger or {})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    return merged


def record_tenant_billing_snapshot(tenant_id: str, snapshot: dict) -> dict:
    ledger = load_tenant_billing_ledger(tenant_id)
    entries = ledger.setdefault("entries", [])
    snapshot_copy = _deep_copy(snapshot or {})
    snapshot_copy.setdefault("captured_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    entries.append(snapshot_copy)
    ledger["last_synced_at"] = snapshot_copy.get("captured_at")
    return save_tenant_billing_ledger(tenant_id, ledger)


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
        config.setdefault("project", {})
        config["project"]["name"] = project_name
        config["project"]["slug"] = _slugify(project_name) or "agentshrink-project"
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


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


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
    provider_config = get_provider_config(upstream_provider)

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

    if provider_config is None:
        checks.append(DoctorCheck(
            "provider_registry",
            False,
            f"Unknown upstream provider '{upstream_provider}'",
            "Pick a saved provider from Settings or add a BYOK provider in the provider registry section first.",
            "provider",
            "error",
        ))
    elif (provider_config.get("adapter") or "").strip().lower() == "mock":
        checks.append(DoctorCheck("provider_mock_mode", True, "Mock upstream is active. Local testing costs $0.", category="provider", severity="info"))
    elif upstream_provider == "ollama":
        ollama_base = resolve_provider_base_url(provider_config) or "http://localhost:11434/v1"
        ollama_base = ollama_base.removesuffix("/v1").rstrip("/")
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
    elif (provider_config.get("adapter") or "").strip().lower() == "huggingface_chat":
        hf_token = resolve_provider_api_key(provider_config)
        checks.append(DoctorCheck(
            "provider_hf_token",
            bool(hf_token),
            f"{provider_config.get('name')} token is set" if hf_token else f"Missing token for {provider_config.get('name')}",
            "" if hf_token else "Add a Hugging Face token in Settings or set the configured HF token env var. Gated models also require access approval.",
            "provider",
            "info" if hf_token else "error",
            [] if hf_token else [
                "$env:HF_TOKEN=\"your_hf_token\"",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack down",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
                ],
            ))
    elif (provider_config.get("adapter") or "").strip().lower() == "gemini_native":
        google_api_key = resolve_provider_api_key(provider_config)
        checks.append(DoctorCheck(
            "provider_gemini_key",
            bool(google_api_key),
            f"{provider_config.get('name')} API key is set" if google_api_key else f"Missing API key for {provider_config.get('name')}",
            "" if google_api_key else "Add a Google API key in Settings or set the configured GOOGLE_API_KEY env var, then restart the stack.",
            "provider",
            "info" if google_api_key else "error",
            [] if google_api_key else [
                "$env:GOOGLE_API_KEY=\"your_google_api_key\"",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack down",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
            ],
        ))
    elif (provider_config.get("adapter") or "").strip().lower() == "anthropic_native":
        anthropic_key = resolve_provider_api_key(provider_config)
        checks.append(DoctorCheck(
            "provider_anthropic_key",
            bool(anthropic_key),
            f"{provider_config.get('name')} API key is set" if anthropic_key else f"Missing API key for {provider_config.get('name')}",
            "" if anthropic_key else "Add an Anthropic API key in Settings or set ANTHROPIC_API_KEY, then restart the stack.",
            "provider",
            "info" if anthropic_key else "error",
            [] if anthropic_key else [
                "$env:ANTHROPIC_API_KEY=\"your_anthropic_key\"",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack down",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
            ],
        ))
    elif (provider_config.get("adapter") or "").strip().lower() == "azure_openai":
        azure_key = resolve_provider_api_key(provider_config)
        azure_endpoint = resolve_provider_base_url(provider_config)
        missing = []
        commands: list[str] = []
        if not azure_key:
            missing.append(f"Missing API key for {provider_config.get('name')}")
            commands.append("$env:AZURE_OPENAI_API_KEY=\"your_azure_openai_key\"")
        if not azure_endpoint:
            missing.append(f"Missing endpoint for {provider_config.get('name')}")
            commands.append("$env:AZURE_OPENAI_ENDPOINT=\"https://your-resource.openai.azure.com\"")
        if missing:
            commands.extend([
                "$env:AZURE_OPENAI_API_VERSION=\"2024-10-21\"",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack down",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
            ])
            checks.append(DoctorCheck(
                "provider_azure_credentials",
                False,
                "; ".join(missing),
                "Save the Azure endpoint and API key in Settings or export AZURE_OPENAI_* env vars before starting the stack.",
                "provider",
                "error",
                commands,
            ))
        else:
            checks.append(DoctorCheck(
                "provider_azure_credentials",
                True,
                f"{provider_config.get('name')} is configured ({azure_endpoint}, api-version {provider_api_version(provider_config)})",
                category="provider",
                severity="info",
            ))
    elif (provider_config.get("adapter") or "").strip().lower() == "custom_http":
        api_key = resolve_provider_api_key(provider_config)
        base_url = resolve_provider_base_url(provider_config)
        missing = []
        commands: list[str] = []
        if not base_url:
            missing.append(f"Missing endpoint URL for {provider_config.get('name')}")
            commands.append("$env:CUSTOM_PROVIDER_URL=\"https://provider.example/api/chat\"")
        if not api_key and str(provider_config.get("api_key_env") or "").strip():
            missing.append(f"Missing API key for {provider_config.get('name')}")
            commands.append(f"$env:{provider_config.get('api_key_env')}=\"your_provider_key\"")
        if missing:
            checks.append(DoctorCheck(
                "provider_custom_http",
                False,
                "; ".join(missing),
                "Save the provider endpoint and any required auth settings in Settings -> provider registry before starting the stack.",
                "provider",
                "error",
                commands,
            ))
        else:
            checks.append(DoctorCheck(
                "provider_custom_http",
                True,
                f"{provider_config.get('name')} custom HTTP endpoint is configured ({base_url})",
                category="provider",
                severity="info",
            ))
    elif (provider_config.get("adapter") or "").strip().lower() == "openai_compatible":
        api_key = resolve_provider_api_key(provider_config)
        base_url = resolve_provider_base_url(provider_config)
        key_env = provider_config.get("api_key_env") or "PROVIDER_API_KEY"
        base_url_env = provider_config.get("base_url_env") or "PROVIDER_BASE_URL"
        requires_base_url = not bool(provider_config.get("builtin"))
        missing_reasons = []
        commands: list[str] = []
        if not api_key:
            missing_reasons.append(f"Missing API key for {provider_config.get('name')}")
            commands.append(f"$env:{key_env}=\"your_provider_key\"")
        if requires_base_url and not base_url:
            missing_reasons.append(f"Missing base URL for {provider_config.get('name')}")
            commands.append(f"$env:{base_url_env}=\"https://your-provider.example/v1\"")
        if missing_reasons:
            commands.extend([
                "venv\\Scripts\\python.exe -m agentshrink.cli stack down",
                "venv\\Scripts\\python.exe -m agentshrink.cli stack up",
            ])
            checks.append(DoctorCheck(
                "provider_api_credentials",
                False,
                "; ".join(missing_reasons),
                "Save the provider's base URL and API key in Settings -> provider registry or export the matching env vars before starting the stack.",
                "provider",
                "error",
                commands,
            ))
        else:
            detail = f"{provider_config.get('name')} is configured"
            if base_url:
                detail += f" ({base_url})"
            checks.append(DoctorCheck(
                "provider_api_credentials",
                True,
                detail,
                category="provider",
                severity="info",
            ))
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


def _deep_copy(data: dict) -> dict:
    return json.loads(json.dumps(data))


def _project_registry_default() -> dict:
    config = load_product_config()
    account = _deep_copy(config.get("account") or DEFAULT_PRODUCT_CONFIG["account"])
    account.setdefault("tenant_id", "tenant_local_default")
    account.setdefault("billing_plan", "beta")
    project = _deep_copy(config.get("project") or DEFAULT_PRODUCT_CONFIG["project"])
    project["name"] = config.get("project_name") or project.get("name") or "AgentShrink Project"
    return {
        "account": account,
        "users": [
            {
                "name": "Local Owner",
                "email": "local-owner@agentshrink.local",
            }
        ],
        "teams": [
            {
                "id": "team_local_default",
                "name": "Core Team",
                "slug": "core-team",
                "role": "owner",
            }
        ],
        "memberships": [
            {
                "team_id": "team_local_default",
                "user_name": "Local Owner",
                "user_email": "local-owner@agentshrink.local",
                "role": "owner",
            }
        ],
        "active_project_id": project.get("id") or "proj_local_default",
        "projects": [
            {
                "id": project.get("id") or "proj_local_default",
                "name": project.get("name") or config.get("project_name") or "AgentShrink Project",
                "slug": project.get("slug") or "agentshrink-project",
                "environment": project.get("environment") or "local",
                "team_id": project.get("team_id") or "team_local_default",
                "config": config,
            }
        ],
        "invites": [],
        "magic_links": [],
        "billing": {
            "plan": "beta",
            "seat_count": 1,
            "included_projects": 5,
            "currency": "USD",
        },
    }


def load_project_registry() -> dict:
    ensure_state_dir()
    if not PROJECT_REGISTRY_PATH.exists():
        registry = _project_registry_default()
        save_project_registry(registry)
        return registry
    with open(PROJECT_REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = _project_registry_default()
    data.setdefault("account", _deep_copy(DEFAULT_PRODUCT_CONFIG["account"]))
    data["account"].setdefault("tenant_id", "tenant_local_default")
    data["account"].setdefault("billing_plan", "beta")
    data.setdefault("users", [{"name": "Local Owner", "email": "local-owner@agentshrink.local"}])
    data.setdefault("teams", [{"id": "team_local_default", "name": "Core Team", "slug": "core-team", "role": "owner"}])
    data.setdefault("memberships", [{"team_id": "team_local_default", "user_name": "Local Owner", "user_email": "local-owner@agentshrink.local", "role": "owner"}])
    data.setdefault("active_project_id", "proj_local_default")
    data.setdefault("projects", [])
    data.setdefault("invites", [])
    data.setdefault("magic_links", [])
    data.setdefault("billing", {"plan": "beta", "seat_count": 1, "included_projects": 5, "currency": "USD"})
    return data


def save_project_registry(registry: dict) -> dict:
    ensure_state_dir()
    with open(PROJECT_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    return registry


def sync_active_project_to_registry(config: dict | None = None) -> dict:
    config = config or load_product_config()
    registry = load_project_registry()
    account = _deep_copy(config.get("account") or DEFAULT_PRODUCT_CONFIG["account"])
    project_meta = _deep_copy(config.get("project") or DEFAULT_PRODUCT_CONFIG["project"])
    project_id = project_meta.get("id") or "proj_local_default"
    project_record = {
        "id": project_id,
        "name": project_meta.get("name") or config.get("project_name") or "AgentShrink Project",
        "slug": project_meta.get("slug") or _slugify(config.get("project_name") or "agentshrink-project") or "agentshrink-project",
        "environment": project_meta.get("environment") or "local",
        "team_id": project_meta.get("team_id") or "team_local_default",
        "config": config,
    }
    projects = registry.get("projects") or []
    updated = False
    for idx, existing in enumerate(projects):
        if existing.get("id") == project_id:
            projects[idx] = project_record
            updated = True
            break
    if not updated:
        projects.append(project_record)
    registry["account"] = account
    registry["projects"] = projects
    registry["active_project_id"] = project_id
    save_project_registry(registry)
    return registry


def _next_available_ports(registry: dict) -> tuple[int, int, int]:
    used_gateway = set()
    used_backend = set()
    used_frontend = set()
    for project in registry.get("projects", []):
        cfg = project.get("config") or {}
        used_gateway.add(int(((cfg.get("gateway") or {}).get("port") or 8100)))
        used_backend.add(int(((cfg.get("dashboard_backend") or {}).get("port") or 8000)))
        used_frontend.add(int(((cfg.get("dashboard_frontend") or {}).get("port") or 3000)))

    gateway = 8100
    backend = 8000
    frontend = 3000
    while gateway in used_gateway:
        gateway += 10
    while backend in used_backend:
        backend += 10
    while frontend in used_frontend:
        frontend += 10
    return gateway, backend, frontend


def create_product_project(
    *,
    project_name: str,
    environment: str = "local",
    upstream_provider: str = "mock",
    team_id: str | None = None,
) -> dict:
    registry = load_project_registry()
    account = registry.get("account") or _deep_copy(DEFAULT_PRODUCT_CONFIG["account"])
    teams = registry.get("teams") or [{"id": "team_local_default", "name": "Core Team", "slug": "core-team", "role": "owner"}]
    session = load_session()
    default_team = next(
        (team for team in teams if team.get("id") == (team_id or session.get("active_team_id"))),
        None,
    ) or teams[0]
    gateway_port, backend_port, frontend_port = _next_available_ports(registry)
    slug = _slugify(project_name) or f"project-{len(registry.get('projects', [])) + 1}"
    project_id = f"proj_{secrets.token_urlsafe(8)}"
    config = _deep_copy(DEFAULT_PRODUCT_CONFIG)
    config["account"] = account
    config["project"] = {
        "id": project_id,
        "name": project_name,
        "slug": slug,
        "environment": environment or "local",
        "team_id": default_team.get("id") or "team_local_default",
    }
    config["project_name"] = project_name
    config["gateway"]["upstream_provider"] = upstream_provider or "mock"
    config["gateway"]["port"] = gateway_port
    config["dashboard_backend"]["port"] = backend_port
    config["dashboard_frontend"]["port"] = frontend_port
    config["defaults"]["gateway_api_key"] = generate_project_token()
    tenant_id = (account.get("tenant_id") or "tenant_local_default").strip()
    if (environment or "local").strip().lower() in {"hosted", "public", "production", "staging"}:
        project_output_dir = (tenant_storage_root(tenant_id) / "projects" / slug).resolve()
    else:
        project_output_dir = (PROJECT_ROOT / ".agentshrink_output" / slug).resolve()
    config["output_dir"] = str(project_output_dir)
    config["db_path"] = str((project_output_dir / "logs.db").resolve())
    pathlib.Path(config["db_path"]).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(config["output_dir"]).mkdir(parents=True, exist_ok=True)
    save_product_config(config)
    registry = sync_active_project_to_registry(config)
    return {
        "account": registry.get("account") or {},
        "teams": registry.get("teams") or [],
        "memberships": registry.get("memberships") or [],
        "active_project_id": registry.get("active_project_id"),
        "projects": registry.get("projects") or [],
        "active_config": config,
    }


def activate_product_project(project_id: str) -> dict:
    registry = load_project_registry()
    for project in registry.get("projects", []):
        if project.get("id") == project_id:
            config = _deep_copy(project.get("config") or {})
            save_product_config(config)
            registry["active_project_id"] = project_id
            save_project_registry(registry)
            session = load_session()
            session["active_project_id"] = project_id
            session["active_team_id"] = (project.get("team_id") or session.get("active_team_id") or "team_local_default")
            save_session(session)
            return {
                "account": registry.get("account") or {},
                "teams": registry.get("teams") or [],
                "memberships": registry.get("memberships") or [],
                "active_project_id": project_id,
                "projects": registry.get("projects") or [],
                "active_config": config,
            }
    raise KeyError(project_id)


def _default_session(registry: dict | None = None) -> dict:
    registry = registry or load_project_registry()
    active_project_id = registry.get("active_project_id") or "proj_local_default"
    active_project = next((project for project in (registry.get("projects") or []) if project.get("id") == active_project_id), None) or {}
    return {
        "authenticated": True,
        "user": {
            "name": "Local Owner",
            "email": "local-owner@agentshrink.local",
        },
        "account_id": (registry.get("account") or {}).get("id", "acct_local_default"),
        "active_team_id": active_project.get("team_id") or "team_local_default",
        "active_project_id": active_project_id,
    }


def load_session() -> dict:
    ensure_state_dir()
    if not SESSION_PATH.exists():
        session = _default_session()
        save_session(session)
        return session
    with open(SESSION_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = _default_session()
    data.setdefault("authenticated", True)
    data.setdefault("user", {"name": "Local Owner", "email": "local-owner@agentshrink.local"})
    return data


def save_session(session: dict) -> dict:
    ensure_state_dir()
    with open(SESSION_PATH, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)
    return session


def create_team(*, name: str, slug: str | None = None) -> dict:
    registry = load_project_registry()
    session = load_session()
    team_slug = _slugify(slug or name) or f"team-{len(registry.get('teams', [])) + 1}"
    team_id = f"team_{secrets.token_urlsafe(8)}"
    team = {
        "id": team_id,
        "name": name,
        "slug": team_slug,
        "role": "owner",
    }
    membership = {
        "team_id": team_id,
        "user_name": (session.get("user") or {}).get("name", "Local Owner"),
        "user_email": (session.get("user") or {}).get("email", "local-owner@agentshrink.local"),
        "role": "owner",
    }
    registry.setdefault("teams", []).append(team)
    registry.setdefault("memberships", []).append(membership)
    _ensure_user_record(registry, membership["user_name"], membership["user_email"])
    save_project_registry(registry)
    session["active_team_id"] = team_id
    save_session(session)
    return {"team": team, "membership": membership, "registry": registry, "session": session}


def invite_team_member(*, team_id: str, user_name: str, user_email: str, role: str = "member") -> dict:
    registry = load_project_registry()
    invites = registry.setdefault("invites", [])
    existing = next(
        (
            invite for invite in invites
            if invite.get("team_id") == team_id
            and invite.get("user_email", "").lower() == user_email.lower()
            and invite.get("status") == "pending"
        ),
        None,
    )
    if existing:
        existing["user_name"] = user_name
        existing["role"] = role
        invite = existing
    else:
        invite = {
            "id": f"inv_{secrets.token_urlsafe(8)}",
            "token": secrets.token_urlsafe(18),
            "team_id": team_id,
            "user_name": user_name,
            "user_email": user_email,
            "role": role,
            "status": "pending",
        }
        invites.append(invite)
    save_project_registry(registry)
    team = next((item for item in (registry.get("teams") or []) if item.get("id") == team_id), None) or {}
    delivery_path = _write_email_delivery(
        kind="team_invite",
        to_email=user_email,
        subject=f"Invitation to join {team.get('name') or 'an AgentShrink team'}",
        body=(
            f"Hello {user_name},\n\n"
            f"You have been invited to join the AgentShrink team '{team.get('name') or team_id}' as {role}.\n"
            f"Invite token:\n\n{invite['token']}\n\n"
            f"Direct accept URL:\n{public_app_base_url().rstrip('/')}/auth?invite_token={invite['token']}\n\n"
            "Sign in to AgentShrink and accept the invite from the Account page, or open the direct accept URL.\n"
        ),
    )
    return {"invite": invite, "registry": registry, "delivery_path": delivery_path}


def update_team_member_role(*, team_id: str, user_email: str, role: str) -> dict:
    registry = load_project_registry()
    for membership in registry.setdefault("memberships", []):
        if membership.get("team_id") == team_id and membership.get("user_email") == user_email:
            membership["role"] = role
            save_project_registry(registry)
    return {"membership": membership, "registry": registry}
    raise KeyError(user_email)


def create_session(*, user_name: str, user_email: str) -> dict:
    registry = load_project_registry()
    session = _default_session(registry)
    session["authenticated"] = True
    session["user"] = {"name": user_name, "email": user_email}
    _ensure_user_record(registry, user_name, user_email)
    memberships = [
        membership for membership in (registry.get("memberships") or [])
        if membership.get("user_email", "").lower() == user_email.lower()
    ]
    if memberships:
        session["active_team_id"] = memberships[0].get("team_id") or session.get("active_team_id")
    save_session(session)
    save_project_registry(registry)
    return session


def clear_session() -> dict:
    session = _default_session()
    session["authenticated"] = False
    save_session(session)
    return session


def _write_email_delivery(*, kind: str, to_email: str, subject: str, body: str) -> str:
    ensure_state_dir()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = EMAIL_OUTBOX_DIR / f"{stamp}_{kind}_{_slugify(to_email)}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"To: {to_email}\n")
        f.write(f"Subject: {subject}\n\n")
        f.write(body)
    return str(path)


def public_app_base_url() -> str:
    hosted = load_hosted_config()
    return (hosted.get("deployment") or {}).get("public_app_url") or "http://localhost:3000"


def request_magic_link(*, user_email: str, user_name: str | None = None) -> dict:
    registry = load_project_registry()
    token = secrets.token_urlsafe(24)
    entry = {
        "id": f"ml_{secrets.token_urlsafe(8)}",
        "token": token,
        "user_email": user_email.strip().lower(),
        "user_name": (user_name or "").strip(),
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    registry.setdefault("magic_links", []).append(entry)
    save_project_registry(registry)
    delivery_path = _write_email_delivery(
        kind="magic_link",
        to_email=entry["user_email"],
        subject="Your AgentShrink sign-in link",
        body=(
            f"Hello {entry['user_name'] or entry['user_email']},\n\n"
            f"Use this magic-link token to sign in to AgentShrink:\n\n{token}\n\n"
            f"Direct sign-in URL:\n{public_app_base_url().rstrip('/')}/auth?magic_token={token}\n\n"
            "Open the link above or /auth in the local product and paste the token.\n"
        ),
    )
    return {"magic_link": entry, "delivery_path": delivery_path}


def consume_magic_link(*, token: str) -> dict:
    registry = load_project_registry()
    entry = next((item for item in (registry.get("magic_links") or []) if item.get("token") == token), None)
    if not entry:
        raise KeyError("magic_link")
    if entry.get("status") != "pending":
        raise ValueError("Magic link is no longer pending.")
    entry["status"] = "used"
    entry["used_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    user_name = entry.get("user_name") or entry.get("user_email", "").split("@")[0] or "User"
    user_email = entry.get("user_email") or ""
    _ensure_user_record(registry, user_name, user_email)
    save_project_registry(registry)
    session = create_session(user_name=user_name, user_email=user_email)
    return {"magic_link": entry, "session": session}


def _ensure_user_record(registry: dict, user_name: str, user_email: str) -> dict:
    users = registry.setdefault("users", [])
    existing = next((user for user in users if user.get("email", "").lower() == user_email.lower()), None)
    if existing:
        existing["name"] = user_name
        return existing
    user = {"name": user_name, "email": user_email}
    users.append(user)
    return user


def get_team_membership(team_id: str, user_email: str) -> dict | None:
    registry = load_project_registry()
    return next(
        (
            membership for membership in (registry.get("memberships") or [])
            if membership.get("team_id") == team_id
            and membership.get("user_email", "").lower() == user_email.lower()
        ),
        None,
    )


def user_team_memberships(user_email: str) -> list[dict]:
    registry = load_project_registry()
    return [
        membership for membership in (registry.get("memberships") or [])
        if membership.get("user_email", "").lower() == user_email.lower()
    ]


def role_meets_minimum(role: str, minimum_role: str) -> bool:
    return ROLE_RANK.get(role or "viewer", 0) >= ROLE_RANK.get(minimum_role or "viewer", 0)


def list_pending_invites(*, user_email: str | None = None) -> list[dict]:
    registry = load_project_registry()
    invites = [invite for invite in (registry.get("invites") or []) if invite.get("status") == "pending"]
    if user_email:
        invites = [invite for invite in invites if invite.get("user_email", "").lower() == user_email.lower()]
    return invites


def accept_team_invite(*, token: str, user_name: str, user_email: str) -> dict:
    registry = load_project_registry()
    invite = next(
        (
            entry for entry in (registry.get("invites") or [])
            if entry.get("token") == token
        ),
        None,
    )
    if not invite:
        raise KeyError("invite_token")
    if invite.get("status") != "pending":
        raise ValueError("Invite is no longer pending.")
    if invite.get("user_email", "").lower() != user_email.lower():
        raise PermissionError("Invite email does not match the signed-in user.")

    memberships = registry.setdefault("memberships", [])
    membership = next(
        (
            item for item in memberships
            if item.get("team_id") == invite.get("team_id")
            and item.get("user_email", "").lower() == user_email.lower()
        ),
        None,
    )
    if membership:
        membership["user_name"] = user_name
        membership["role"] = invite.get("role") or membership.get("role") or "member"
    else:
        membership = {
            "team_id": invite.get("team_id"),
            "user_name": user_name,
            "user_email": user_email,
            "role": invite.get("role") or "member",
        }
        memberships.append(membership)

    invite["status"] = "accepted"
    invite["accepted_by"] = user_email
    _ensure_user_record(registry, user_name, user_email)
    save_project_registry(registry)

    session = load_session()
    session["authenticated"] = True
    session["user"] = {"name": user_name, "email": user_email}
    session["active_team_id"] = invite.get("team_id") or session.get("active_team_id")
    save_session(session)
    return {"invite": invite, "membership": membership, "registry": registry, "session": session}
