"""
agentshrink/cli.py - CLI interface for AgentShrink.

Commands:
  agentshrink status     -> Show captured call summary (Phase 1)
  agentshrink analyse    -> Run clustering + report (Phase 2+3)
  agentshrink gateway    -> Run OpenAI-compatible AgentShrink gateway
  agentshrink shrink     -> Apply routing (Phase 4 - coming soon)
  agentshrink monitor    -> Quality check (Phase 4+ - coming soon)
"""

import sys
import pathlib
import json
import os
import time
import subprocess
import signal
import urllib.request
import socket
from contextlib import suppress

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentshrink.app_setup import (
    PRODUCT_CONFIG_PATH,
    RUNTIME_LOG_DIR,
    RUNTIME_STATE_PATH,
    initialize_product_config,
    load_runtime_state,
    load_product_config,
    run_doctor_checks,
    save_runtime_state,
)
from agentshrink.project_config import get_eval_samples_per_cluster
from agentshrink.project_config import get_judge_min_interval_s, get_remote_min_interval_s

console = Console()


def _project_python_executable() -> str:
    project_root = pathlib.Path.cwd().resolve()
    if os.name == "nt":
        candidate = project_root / "venv" / "Scripts" / "python.exe"
    else:
        candidate = project_root / "venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate.resolve())
    return sys.executable


def _frontend_command(frontend_dir: pathlib.Path, port: int) -> list[str]:
    next_cmd = frontend_dir / "node_modules" / ".bin" / ("next.cmd" if os.name == "nt" else "next")
    if next_cmd.exists():
        return [str(next_cmd.resolve()), "dev", "--hostname", "127.0.0.1", "--port", str(port)]
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    return [npm_cmd, "run", "dev", "--", "--hostname", "127.0.0.1", "--port", str(port)]


def _frontend_server_command(frontend_dir: pathlib.Path, port: int) -> list[str]:
    next_cmd = frontend_dir / "node_modules" / ".bin" / ("next.cmd" if os.name == "nt" else "next")
    if next_cmd.exists():
        return [str(next_cmd.resolve()), "start", "--hostname", "127.0.0.1", "--port", str(port)]
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    return [npm_cmd, "run", "start", "--", "--hostname", "127.0.0.1", "--port", str(port)]


def _normalize_background_command(command: list[str]) -> list[str]:
    if os.name != "nt" or not command:
        return command
    exe = command[0]
    try:
        exe_path = pathlib.Path(exe)
        if exe_path.is_absolute() and exe_path.name.lower().startswith("python"):
            command = [os.path.relpath(str(exe_path), str(pathlib.Path.cwd().resolve()))] + command[1:]
    except Exception:
        pass
    return command


def _launch_background_process(*, name: str, command: list[str], cwd: pathlib.Path, env: dict[str, str]) -> dict:
    RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = RUNTIME_LOG_DIR / f"{name}.out.log"
    stderr_path = RUNTIME_LOG_DIR / f"{name}.err.log"
    cwd = cwd.resolve()

    if os.name == "nt":
        script_path = RUNTIME_LOG_DIR / f"{name}.launch.cmd"
        command = _normalize_background_command(command)
        env_lines = []
        for key, value in sorted(env.items()):
            if os.environ.get(key) == value:
                continue
            safe_value = value.replace('"', '""')
            env_lines.append(f'set "{key}={safe_value}"')
        script_lines = [
            "@echo off",
            "setlocal",
            f'cd /d "{cwd}"',
            *env_lines,
            f'call {subprocess.list2cmdline(command)} 1>>"{stdout_path.resolve()}" 2>>"{stderr_path.resolve()}"',
        ]
        script_path.write_text("\n".join(script_lines) + "\n", encoding="utf-8")
        creationflags = 0
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        creationflags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
        process = subprocess.Popen(
            ["cmd.exe", "/c", str(script_path.resolve())],
            cwd=str(pathlib.Path.cwd().resolve()),
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        pid = process.pid
    else:
        stdout_file = open(stdout_path, "w", encoding="utf-8")
        stderr_file = open(stderr_path, "w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        pid = process.pid

    return {
        "pid": pid,
        "command": command,
        "cwd": str(cwd),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _pid_is_running(pid: int) -> bool:
    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($p) {{ 'running' }}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return "running" in (result.stdout or "")
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _terminate_pid(pid: int):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
    else:
        with suppress(Exception):  # type: ignore[name-defined]
            os.kill(pid, signal.SIGTERM)


def _probe_http(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= getattr(response, "status", 0) < 500
    except Exception:
        return False


def _port_is_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _reserve_log_path(path: pathlib.Path) -> pathlib.Path:
    try:
        with open(path, "a", encoding="utf-8"):
            pass
        return path
    except PermissionError:
        stamped = path.with_name(f"{path.stem}-{int(time.time())}{path.suffix}")
        with open(stamped, "a", encoding="utf-8"):
            pass
        return stamped


def _launch_supervised_process(*, command: list[str], cwd: pathlib.Path, env: dict[str, str], name: str) -> tuple[subprocess.Popen, dict]:
    RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = _reserve_log_path(RUNTIME_LOG_DIR / f"{name}.out.log")
    stderr_path = _reserve_log_path(RUNTIME_LOG_DIR / f"{name}.err.log")
    stdout_file = open(stdout_path, "w", encoding="utf-8")
    stderr_file = open(stderr_path, "w", encoding="utf-8")
    cwd = cwd.resolve()

    kwargs = {
        "cwd": str(cwd),
        "env": env,
        "stdout": stdout_file,
        "stderr": stderr_file,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **kwargs)
    info = {
        "pid": process.pid,
        "command": command,
        "cwd": str(cwd),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return process, info


def _wait_for_service(name: str, url: str, process: subprocess.Popen, timeout_s: float = 20.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        if _probe_http(url):
            return True
        time.sleep(0.5)
    return False


def _write_frontend_runtime_env(config: dict) -> bool:
    frontend_dir = pathlib.Path("dashboard") / "frontend"
    env_path = frontend_dir / ".env.local"
    backend_url = f"http://127.0.0.1:{config['dashboard_backend']['port']}"
    gateway_url = f"http://{config['gateway']['host']}:{config['gateway']['port']}/v1"
    content = (
        f"NEXT_PUBLIC_API_BASE_URL={backend_url}\n"
        f"NEXT_PUBLIC_GATEWAY_BASE_URL={gateway_url}\n"
    )
    previous = env_path.read_text(encoding="utf-8") if env_path.exists() else None
    if previous == content:
        return False
    env_path.write_text(content, encoding="utf-8")
    return True


def _dominant_node(cluster_info: dict) -> str:
    node_dist = cluster_info.get("node_distribution", {}) or {}
    if not node_dist:
        return ""
    return max(node_dist.items(), key=lambda kv: kv[1])[0]


def _can_load_existing_snapshot(output_path: pathlib.Path) -> bool:
    """Check if a valid clustering snapshot exists on disk."""
    return (
        (output_path / "cluster_info.json").exists()
        and (output_path / "centroids.npy").exists()
        and (output_path / "clustered_df.parquet").exists()
    )


def _load_existing_snapshot(output_path: pathlib.Path) -> dict | None:
    """Load an existing clustering snapshot from disk without re-running curation or clustering."""
    import numpy as np
    import pandas as pd

    try:
        with open(output_path / "cluster_info.json", encoding="utf-8") as f:
            cluster_info_raw = json.load(f)

        centroids_array = np.load(output_path / "centroids.npy")
        df = pd.read_parquet(output_path / "clustered_df.parquet")

        # Reconstruct centroids dict
        centroid_ids = cluster_info_raw.get("centroid_ids", sorted(int(k) for k in cluster_info_raw["clusters"].keys()))
        centroids = {cid: centroids_array[i] for i, cid in enumerate(centroid_ids)}

        # Reconstruct cluster_info
        cluster_info = {}
        for cid_str, info in cluster_info_raw["clusters"].items():
            cluster_info[int(cid_str)] = info

        # Build embeddings from the dataframe if available, else use empty
        embeddings = None

        return {
            "n_clusters": cluster_info_raw["n_clusters"],
            "n_noise": cluster_info_raw.get("n_noise", 0),
            "cluster_info": cluster_info,
            "cluster_names": {int(k): v for k, v in cluster_info_raw.get("cluster_names", {}).items()},
            "centroids": centroids,
            "df": df,
            "embeddings": embeddings,
        }
    except Exception:
        return None


def _build_heuristic_report(cluster_result: dict) -> dict:
    """Create a local-only heuristic report when full evaluator is skipped."""
    local_model = os.getenv("TARGET_AGENT_OLLAMA_MODEL", "llama3.2:3b")
    local_display = f"Local ({local_model})"
    clusters = []

    for cluster_id, info in cluster_result["cluster_info"].items():
        dominant = _dominant_node(info).lower()
        recommendation = "fine_tune"
        best_score = 0.72
        best_slm = local_model
        best_slm_display = local_display
        needs_fine_tuning = True
        fine_tune_base_model = local_model

        if any(key in dominant for key in ("classify", "extract", "format")):
            recommendation = "replace_now"
            best_score = 0.92
            needs_fine_tuning = False
            fine_tune_base_model = None
        elif "draft_reply" in dominant:
            recommendation = "keep_llm"
            best_score = 0.58
            best_slm = None
            best_slm_display = None
            needs_fine_tuning = False
            fine_tune_base_model = None
        elif "check_policy" in dominant:
            recommendation = "fine_tune"
            best_score = 0.74
            needs_fine_tuning = True
            fine_tune_base_model = local_model

        clusters.append({
            "cluster_id": int(cluster_id),
            "cluster_name": info["name"],
            "cluster_size": int(info["size"]),
            "recommendation": recommendation,
            "best_slm": best_slm,
            "best_slm_display": best_slm_display,
            "best_score": best_score,
            "needs_fine_tuning": needs_fine_tuning,
            "fine_tune_base_model": fine_tune_base_model,
            "estimated_cost_saving_pct": 100.0 if recommendation == "replace_now" else (45.0 if recommendation == "fine_tune" else 0.0),
            "node_distribution": info.get("node_distribution", {}),
            "evaluations": [{
                "slm_name": best_slm or "fallback",
                "slm_display": best_slm_display or "Fallback",
                "correctness_score": best_score,
                "format_score": best_score,
                "completeness_score": max(best_score - 0.05, 0.0),
                "composite_score": best_score,
                "avg_latency_ms": round(info.get("avg_latency_ms", 0), 1),
                "p95_latency_ms": round(info.get("avg_latency_ms", 0) * 1.15, 1),
                "n_evaluated": min(info.get("size", 0), 20),
                "sample_comparisons": [{
                    "prompt": (info.get("sample_prompts") or [""])[0][:180],
                    "reference": "Original response captured in logs.",
                    "candidate": f"Heuristic local recommendation for {info['name']}.",
                }],
            }],
        })

    total_clusters = len(clusters)
    replace_now = [c for c in clusters if c["recommendation"] == "replace_now"]
    fine_tune = [c for c in clusters if c["recommendation"] == "fine_tune"]
    keep_llm = [c for c in clusters if c["recommendation"] == "keep_llm"]
    total_calls = sum(c["cluster_size"] for c in clusters) or 1
    replace_calls = sum(c["cluster_size"] for c in replace_now)
    finetune_calls = sum(c["cluster_size"] for c in fine_tune)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "heuristic": True,
        "summary": {
            "total_clusters": total_clusters,
            "replace_now_count": len(replace_now),
            "fine_tune_count": len(fine_tune),
            "keep_llm_count": len(keep_llm),
            "pct_calls_replaceable_now": round(replace_calls / total_calls * 100, 1),
            "pct_calls_replaceable_with_finetune": round((replace_calls + finetune_calls) / total_calls * 100, 1),
            "models_evaluated": [local_model],
        },
        "clusters": clusters,
    }


@click.group()
@click.version_option(package_name="agentshrink")
def cli():
    """AgentShrink - Automatically convert LLM agents to use cheaper local SLMs.
    Based on NVIDIA arXiv:2506.02153 (June 2025)."""
    pass


@cli.command()
@click.option("--project-name", default="AgentShrink Project", show_default=True, help="Friendly name for this local AgentShrink project")
@click.option("--db", "db_path", default=None, help="SQLite path for traces/logs")
@click.option("--output-dir", default=None, help="Directory for analysis/routing outputs")
@click.option("--gateway-port", default=8100, type=int, show_default=True)
@click.option("--backend-port", default=8000, type=int, show_default=True)
@click.option("--frontend-port", default=3000, type=int, show_default=True)
@click.option(
    "--upstream-provider",
    default="mock",
    show_default=True,
    type=str,
)
def init(project_name, db_path, output_dir, gateway_port, backend_port, frontend_port, upstream_provider):
    """Create a local AgentShrink project manifest for easier startup."""
    config = initialize_product_config(
        project_name=project_name,
        db_path=db_path,
        output_dir=output_dir,
        gateway_port=gateway_port,
        backend_port=backend_port,
        frontend_port=frontend_port,
        upstream_provider=upstream_provider,
    )
    console.print(
        Panel.fit(
            "[bold]AgentShrink Initialized[/bold]\n"
            f"Project: {config['project_name']}\n"
            f"Config: {PRODUCT_CONFIG_PATH}",
            border_style="green",
        )
    )
    # On Windows, check if the Scripts dir is on PATH
    if os.name == "nt":
        import sysconfig
        scripts_dir = sysconfig.get_path("scripts", "nt_user")
        if scripts_dir and scripts_dir not in os.environ.get("PATH", ""):
            console.print(
                f"\n[yellow]Tip:[/yellow] The [bold]agentshrink[/bold] command is installed at:\n"
                f"  {scripts_dir}\n"
                f"Add it to your PATH to use [bold]agentshrink[/bold] directly, or use:\n"
                f"  [bold]python -m agentshrink[/bold]\n"
            )
    console.print("Next:")
    console.print("  1. [bold]agentshrink doctor[/bold]")
    console.print("  2. [bold]agentshrink stack up[/bold]")
    console.print("  3. Point your OpenAI-compatible app at the gateway URL")


@cli.command()
def doctor():
    """Check whether the local AgentShrink project is ready to run."""
    checks = run_doctor_checks()
    table = Table(title="AgentShrink Doctor", box=box.ROUNDED, header_style="bold dim")
    table.add_column("Check", style="white")
    table.add_column("Status", style="cyan")
    table.add_column("Detail", style="yellow")
    failures = 0
    for check in checks:
        status = "[green]OK[/green]" if check.ok else "[red]FAIL[/red]"
        if not check.ok:
            failures += 1
        table.add_row(check.name, status, check.detail)
    console.print(table)
    if failures:
        console.print(f"[yellow]{failures} check(s) need attention before a smooth first run.[/yellow]")
    else:
        console.print("[green]All local AgentShrink checks passed.[/green]")


@cli.group()
def start():
    """Start one local AgentShrink service using the saved project manifest."""
    pass


@start.command("gateway")
def start_gateway():
    """Start the gateway using saved project settings."""
    config = load_product_config()
    ctx = click.get_current_context()
    ctx.invoke(
        gateway,
        host=config["gateway"]["host"],
        port=int(config["gateway"]["port"]),
        upstream_provider=config["gateway"]["upstream_provider"],
        output_dir=config["output_dir"],
        db=config["db_path"],
        confidence_threshold=float(config["defaults"]["confidence_threshold"]),
    )


@start.command("backend")
def start_backend():
    """Start the dashboard backend using the saved project DB path."""
    config = load_product_config()
    backend_dir = pathlib.Path("dashboard") / "backend"
    env = os.environ.copy()
    env["AGENTSHRINK_DB_PATH"] = config["db_path"]
    port = str(config["dashboard_backend"]["port"])
    console.print(
        Panel.fit(
            "[bold]AgentShrink Dashboard Backend[/bold]\n"
            f"DB: {config['db_path']}\n"
            f"Listening on http://{config['dashboard_backend']['host']}:{port}",
            border_style="blue",
        )
    )
    raise SystemExit(
        subprocess.call(
            [_project_python_executable(), "-m", "uvicorn", "main:app", "--port", port],
            cwd=str(backend_dir),
            env=env,
        )
    )


@start.command("frontend")
def start_frontend():
    """Start the dashboard frontend."""
    config = load_product_config()
    frontend_dir = pathlib.Path("dashboard") / "frontend"
    port = int(config["dashboard_frontend"]["port"])
    _write_frontend_runtime_env(config)
    frontend_env = os.environ.copy()
    frontend_env["NEXT_PUBLIC_API_BASE_URL"] = f"http://127.0.0.1:{config['dashboard_backend']['port']}"
    frontend_env["NEXT_PUBLIC_GATEWAY_BASE_URL"] = f"http://{config['gateway']['host']}:{config['gateway']['port']}/v1"
    console.print(
        Panel.fit(
            "[bold]AgentShrink Dashboard Frontend[/bold]\n"
            f"Open http://localhost:{port}",
            border_style="blue",
        )
    )
    raise SystemExit(
        subprocess.call(
            _frontend_command(frontend_dir.resolve(), port),
            cwd=str(frontend_dir),
            env=frontend_env,
        )
    )


@start.command("guide")
def start_guide():
    """Print the saved one-copy local run guide."""
    config = load_product_config()
    gateway_url = f"http://{config['gateway']['host']}:{config['gateway']['port']}/v1"
    panel = Panel.fit(
        "[bold]AgentShrink Quickstart[/bold]\n"
        f"1. agentshrink init --project-name \"{config.get('project_name', 'My AgentShrink Project')}\"\n"
        f"2. agentshrink doctor\n"
        f"3. agentshrink stack up\n\n"
        f"Gateway URL: {gateway_url}\n"
        f"DB Path: {config['db_path']}\n"
        f"Dashboard: http://localhost:{config['dashboard_frontend']['port']}/welcome",
        border_style="green",
    )
    console.print(panel)


@cli.group()
def stack():
    """Manage the full local AgentShrink stack."""
    pass


@stack.command("up")
@click.option("--skip-frontend", is_flag=True, default=False, help="Start gateway + backend only")
def stack_up(skip_frontend):
    """Start the full local AgentShrink stack in a foreground supervisor."""
    config = load_product_config()
    state = load_runtime_state()
    existing = state.get("services", {})
    running = {name: svc for name, svc in existing.items() if _pid_is_running(int(svc.get("pid", 0)))}
    if running:
        console.print("[yellow]Some stack services are already running.[/yellow]")
        for name, svc in running.items():
            console.print(f"  {name}: pid {svc['pid']}")
        console.print("Use [bold]agentshrink stack down[/bold] first if you want a clean restart.")
        return

    services = {}
    processes: dict[str, subprocess.Popen] = {}
    db_path = config["db_path"]
    output_dir = config["output_dir"]
    gateway_url = f"http://{config['gateway']['host']}:{config['gateway']['port']}"
    backend_url = f"http://127.0.0.1:{config['dashboard_backend']['port']}"
    frontend_url = f"http://127.0.0.1:{config['dashboard_frontend']['port']}"

    preflight_ports = [
        ("gateway", config["gateway"]["host"], int(config["gateway"]["port"])),
        ("backend", "127.0.0.1", int(config["dashboard_backend"]["port"])),
    ]
    if not skip_frontend:
        preflight_ports.append(("frontend", "127.0.0.1", int(config["dashboard_frontend"]["port"])))

    busy_ports = [
        (name, host, port)
        for name, host, port in preflight_ports
        if _port_is_in_use(host, port)
    ]
    if busy_ports:
        console.print("[red]AgentShrink stack could not start because one or more ports are already in use.[/red]")
        for name, host, port in busy_ports:
            console.print(f"  {name}: {host}:{port}")
        console.print("Recommended recovery:")
        console.print("  1. [bold]agentshrink stack status[/bold]")
        console.print("  2. [bold]agentshrink stack down[/bold] if an older local stack is still recorded")
        console.print("  3. Or run [bold]agentshrink init[/bold] again with different ports")
        return

    try:
        gateway_proc, gateway_info = _launch_supervised_process(
            name="gateway",
            command=[
                _project_python_executable(), "-m", "agentshrink.cli", "gateway",
                "--host", config["gateway"]["host"],
                "--port", str(config["gateway"]["port"]),
                "--upstream-provider", config["gateway"]["upstream_provider"],
                "--output-dir", output_dir,
                "--db", db_path,
                "--confidence-threshold", str(config["defaults"]["confidence_threshold"]),
            ],
            cwd=pathlib.Path.cwd(),
            env=os.environ.copy(),
        )
        processes["gateway"] = gateway_proc
        services["gateway"] = gateway_info

        backend_env = os.environ.copy()
        backend_env["AGENTSHRINK_DB_PATH"] = db_path
        backend_proc, backend_info = _launch_supervised_process(
            name="backend",
            command=[
                _project_python_executable(),
                "-m",
                "uvicorn",
                "main:app",
                "--app-dir",
                str(pathlib.Path("dashboard") / "backend"),
                "--port",
                str(config["dashboard_backend"]["port"]),
            ],
            cwd=pathlib.Path.cwd(),
            env=backend_env,
        )
        processes["backend"] = backend_proc
        services["backend"] = backend_info

        if not _wait_for_service("gateway", f"{gateway_url}/health", gateway_proc):
            console.print("[red]Gateway failed to become healthy. Check .agentshrink/logs/gateway.err.log[/red]")
            return
        if not _wait_for_service("backend", f"{backend_url}/api/health", backend_proc):
            console.print("[red]Backend failed to become healthy. Check .agentshrink/logs/backend.err.log[/red]")
            return

        if not skip_frontend:
            frontend_cmd = "npm.cmd" if os.name == "nt" else "npm"
            frontend_dir = pathlib.Path("dashboard") / "frontend"
            env_changed = _write_frontend_runtime_env(config)
            build_id_path = frontend_dir / ".next" / "BUILD_ID"
            if build_id_path.exists() and not env_changed:
                console.print("Using existing frontend production build for local stack.")
            else:
                console.print("Building frontend for local stack...")
                build_result = subprocess.call(
                    [frontend_cmd, "run", "build"],
                    cwd=str(frontend_dir.resolve()),
                    env=os.environ.copy(),
                )
                if build_result != 0:
                    console.print("[red]Frontend build failed before startup.[/red]")
                    if os.name == "nt":
                        console.print(
                            "[yellow]Tip:[/yellow] run [bold]npm.cmd run build[/bold] once inside "
                            "[bold]dashboard\\frontend[/bold], then re-run [bold]agentshrink stack up[/bold]."
                        )
                    return

            frontend_proc, frontend_info = _launch_supervised_process(
                name="frontend",
                command=_frontend_server_command(frontend_dir.resolve(), int(config["dashboard_frontend"]["port"])),
                cwd=frontend_dir,
                env={
                    **os.environ.copy(),
                    "NEXT_PUBLIC_API_BASE_URL": backend_url,
                    "NEXT_PUBLIC_GATEWAY_BASE_URL": gateway_url + "/v1" if not gateway_url.endswith("/v1") else gateway_url,
                },
            )
            processes["frontend"] = frontend_proc
            services["frontend"] = frontend_info

            if not _wait_for_service("frontend", f"{frontend_url}/", frontend_proc, timeout_s=25.0):
                console.print("[red]Frontend failed to become healthy. Check .agentshrink/logs/frontend.err.log[/red]")
                return

        save_runtime_state({"services": services})
        console.print(
            Panel.fit(
                "[bold]AgentShrink Stack Started[/bold]\n"
                f"Gateway:   {gateway_url}\n"
                f"Backend:   {backend_url}\n"
                f"Frontend:  http://localhost:{config['dashboard_frontend']['port']}",
                border_style="green",
            )
        )
        console.print("Foreground supervisor is active. Press [bold]Ctrl+C[/bold] to stop the stack.")

        while True:
            dead = [name for name, process in processes.items() if process.poll() is not None]
            if dead:
                console.print(f"[red]Service exited unexpectedly:[/red] {', '.join(dead)}")
                for name in dead:
                    log_path = services.get(name, {}).get("stderr_log") or services.get(name, {}).get("stdout_log")
                    if log_path:
                        console.print(f"Check logs: [bold]{log_path}[/bold]")
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping AgentShrink stack...[/yellow]")
    finally:
        for process in processes.values():
            if process.poll() is None:
                with suppress(Exception):
                    if os.name == "nt":
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        process.terminate()
        deadline = time.time() + 8
        while time.time() < deadline:
            alive = [process for process in processes.values() if process.poll() is None]
            if not alive:
                break
            time.sleep(0.2)
        for process in processes.values():
            if process.poll() is None:
                with suppress(Exception):
                    process.kill()
        save_runtime_state({"services": {}})


@stack.command("status")
def stack_status():
    """Show local stack process status."""
    state = load_runtime_state()
    services = state.get("services", {})
    table = Table(title="AgentShrink Stack", box=box.ROUNDED, header_style="bold dim")
    table.add_column("Service")
    table.add_column("PID")
    table.add_column("Status")
    table.add_column("Logs")
    if not services:
        console.print("[yellow]No saved stack services found. Start with `agentshrink stack up`.[/yellow]")
        return
    for name, svc in services.items():
        pid = int(svc.get("pid", 0) or 0)
        running = _pid_is_running(pid)
        table.add_row(
            name,
            str(pid),
            "[green]running[/green]" if running else "[red]stopped[/red]",
            svc.get("stdout_log", ""),
        )
    console.print(table)


@stack.command("down")
def stack_down():
    """Stop the local AgentShrink stack."""
    state = load_runtime_state()
    services = state.get("services", {})
    if not services:
        console.print("[yellow]No running stack services were recorded.[/yellow]")
        return
    for name, svc in services.items():
        pid = int(svc.get("pid", 0) or 0)
        if pid and _pid_is_running(pid):
            _terminate_pid(pid)
            console.print(f"Stopped {name} (pid {pid})")
    save_runtime_state({"services": {}})


@cli.command()
@click.option("--db", default=None, help="Path to logs.db")
def status(db):
    """Show summary of captured LLM calls."""
    from agentshrink.logger import AgentShrinkLogger

    db_path = pathlib.Path(db).expanduser() if db else None
    logger_instance = AgentShrinkLogger.from_db(db_path=db_path)
    summary = logger_instance.get_summary()

    if "error" in summary:
        console.print(f"[red]{summary['error']}[/red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold]AgentShrink Status[/bold]\nDB: {summary['db_path']}",
        border_style="blue",
    ))
    console.print(f"  Total calls:  [bold]{summary['total_calls']}[/bold]")
    console.print(f"  Unique runs:  [bold]{summary['total_runs']}[/bold]")
    console.print(f"  Total tokens: [bold]{summary['total_tokens']:,}[/bold]")
    console.print(f"  Est. cost:    [bold]${summary['total_cost_usd']:.4f}[/bold]")

    total = summary["total_calls"]
    if total < 50:
        console.print(f"\n  [yellow]! Need 100+ calls for clustering. Have {total}.[/yellow]")
    elif total < 200:
        console.print(f"\n  [yellow]i {total} calls - 200+ gives better clusters.[/yellow]")
    else:
        console.print("\n  [green]OK Ready for: agentshrink analyse[/green]")

    if summary["nodes"]:
        table = Table(title="Calls per Node", box=box.ROUNDED, header_style="bold dim")
        table.add_column("Node", style="white", min_width=20)
        table.add_column("Calls", style="cyan", justify="right")
        table.add_column("Avg Latency", style="yellow", justify="right")
        for node in summary["nodes"]:
            table.add_row(node["name"], str(node["count"]), f"{node['avg_latency_ms']}ms")
        console.print(table)


@cli.command()
@click.option("--db", default=None, help="Path to logs.db")
@click.option("--output-dir", default=".agentshrink_output", help="Where to save results")
@click.option("--no-llm-labels", is_flag=True, default=False, help="Use heuristic labels")
@click.option("--skip-eval", is_flag=True, default=False, help="Only cluster, skip SLM evaluation")
@click.option("--min-cluster-size", default=5, type=int, help="HDBSCAN min_cluster_size")
@click.option("--cluster-id", "cluster_ids", multiple=True, type=int, help="Evaluate/report only the specified cluster_id. Can be passed multiple times.")
def analyse(db, output_dir, no_llm_labels, skip_eval, min_cluster_size, cluster_ids):
    """[Phase 2+3] Cluster captured calls and generate Replaceability Report."""
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    output_path = pathlib.Path(output_dir)
    db_path = pathlib.Path(db).expanduser() if db else None

    # ── Targeted evaluation: reuse existing clustering snapshot ──
    if cluster_ids and _can_load_existing_snapshot(output_path):
        console.print(Panel.fit(
            "[bold]AgentShrink - Targeted Re-evaluation[/bold]\n"
            f"Reusing existing clustering snapshot for cluster_id(s): {', '.join(str(c) for c in cluster_ids)}",
            border_style="cyan",
        ))
        cluster_result = _load_existing_snapshot(output_path)
        if cluster_result is None:
            console.print("[red]Failed to load existing snapshot. Run full analysis first.[/red]")
            sys.exit(1)

        # Validate requested cluster IDs exist
        existing_ids = {int(cid) for cid in cluster_result["cluster_info"].keys()}
        missing = {int(c) for c in cluster_ids} - existing_ids
        if missing:
            console.print(f"[red]Cluster IDs not found in snapshot: {sorted(missing)}[/red]")
            console.print(f"  Available cluster IDs: {sorted(existing_ids)}")
            sys.exit(1)

        console.print(f"  [green]OK[/green] Loaded {cluster_result['n_clusters']} clusters from existing snapshot")
        for cid, info in cluster_result["cluster_info"].items():
            marker = " [cyan]<- targeted[/cyan]" if int(cid) in {int(c) for c in cluster_ids} else ""
            console.print(f"    {cid}: '{info['name']}' ({info['size']} entries){marker}")
    else:
        # ── Full analysis: curate + cluster from scratch ──
        console.print(Panel.fit(
            "[bold]AgentShrink - Analysis Pipeline[/bold]\n"
            "curate -> cluster -> evaluate -> report",
            border_style="blue",
        ))

        console.print("\n[bold]Step 1/4[/bold] Curating logs...")
        from agentshrink.curator import CuratorConfig, DataCurator

        curator = DataCurator(db_path=db_path, config=CuratorConfig())
        try:
            df, embeddings = curator.curate(source="db")
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)

        if len(df) < 20:
            console.print(f"[red]Only {len(df)} entries after curation - need 20+.[/red]")
            sys.exit(1)
        console.print(f"  [green]OK[/green] {len(df)} clean entries")

        console.print("\n[bold]Step 2/4[/bold] Discovering task clusters...")
        from agentshrink.clusterer import ClusterConfig, TaskClusterer

        clusterer = TaskClusterer(config=ClusterConfig(
            min_cluster_size=min_cluster_size,
            umap_n_neighbours=min(10, len(df) - 1),
        ))

        with console.status("UMAP + HDBSCAN running..."):
            cluster_result = clusterer.fit(df, embeddings, use_llm_labels=not no_llm_labels)

        if cluster_result["n_clusters"] == 0:
            console.print("[red]0 clusters found. Try: --min-cluster-size 3[/red]")
            sys.exit(1)

        console.print(f"  [green]OK[/green] Found {cluster_result['n_clusters']} clusters:")
        for cid, info in cluster_result["cluster_info"].items():
            console.print(f"    {cid}: '{info['name']}' ({info['size']} entries)")

        if cluster_ids:
            console.print(
                f"  [cyan]Targeted evaluation enabled for cluster_id(s): {', '.join(str(cid) for cid in cluster_ids)}[/cyan]"
            )

        clusterer.save_results(cluster_result, output_path)

        # Persist TF-IDF vectorizer when sentence-transformers is unavailable.
        if hasattr(curator, "_embedder") and hasattr(curator._embedder, "vectorizer"):
            import joblib
            joblib.dump(curator._embedder.vectorizer, output_path / "tfidf_vectorizer.joblib")
            with open(output_path / "embedder_info.json", "w", encoding="utf-8") as f:
                json.dump({"type": "tfidf"}, f, indent=2)

    if skip_eval:
        heuristic_report = _build_heuristic_report(cluster_result)
        with open(output_path / "replaceability_report.json", "w", encoding="utf-8") as f:
            json.dump(heuristic_report, f, indent=2)
        console.print("\n[yellow]Skipped SLM evaluation (--skip-eval)[/yellow]")
        console.print("[green]OK Heuristic local report generated[/green]")
        console.print(f"[green]OK Results saved to {output_path}[/green]")
        return

    console.print("\n[bold]Step 3/4[/bold] Evaluating clusters against local SLMs...")
    console.print("  [dim]Loading models one at a time - safe for 8GB RAM[/dim]")

    from agentshrink.evaluator import EvaluatorConfig, SLMEvaluator

    evaluator = SLMEvaluator(
        config=EvaluatorConfig(
            n_samples_per_cluster=get_eval_samples_per_cluster(),
            remote_min_interval_s=get_remote_min_interval_s(),
            judge_min_interval_s=get_judge_min_interval_s(),
            verbose=True,
        )
    )

    try:
        with console.status("Evaluating... (~5-15 minutes)"):
            reports = evaluator.evaluate_all_clusters(cluster_result, cluster_ids=list(cluster_ids))
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Fix: ollama serve && ollama pull gemma2:2b")
        console.print("Or skip: agentshrink analyse --skip-eval")
        sys.exit(1)

    console.print("\n[bold]Step 4/4[/bold] Generating report...")
    report_filename = (
        f"replaceability_report_cluster_{cluster_ids[0]}.json"
        if len(cluster_ids) == 1 else
        "replaceability_report.json"
    )
    if len(cluster_ids) > 1:
        joined = "_".join(str(cid) for cid in cluster_ids)
        report_filename = f"replaceability_report_clusters_{joined}.json"
    report_path = evaluator.save_report(reports, output_path, filename=report_filename)
    evaluator.print_report(reports)

    console.print(f"\n[green]OK Report: {report_path}[/green]")
    console.print("Next: [bold]agentshrink shrink[/bold] (Phase 4 - coming soon)")


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind the gateway server to")
@click.option("--port", default=8100, type=int, show_default=True, help="Port to bind the gateway server to")
@click.option(
    "--upstream-provider",
    default=lambda: os.getenv("AGENTSHRINK_GATEWAY_UPSTREAM_PROVIDER", "mock"),
    show_default="mock",
    type=str,
    help="Remote upstream for unmatched/fallback calls. Use 'mock' for free local testing.",
)
@click.option("--output-dir", default=".agentshrink_output", show_default=True, help="Routing config output directory")
@click.option("--db", default=None, help="Path to gateway trace database (defaults to ~/.agentshrink/logs.db)")
@click.option("--confidence-threshold", default=0.75, type=float, show_default=True, help="Routing confidence threshold")
def gateway(host, port, upstream_provider, output_dir, db, confidence_threshold):
    """Run the OpenAI-compatible AgentShrink gateway locally."""
    import uvicorn

    from agentshrink.gateway.app import create_gateway_app
    from agentshrink.gateway.router import GatewayRouter
    from agentshrink.gateway.upstream import OpenAICompatibleUpstream

    db_path = pathlib.Path(db).expanduser() if db else None
    product_config = load_product_config()
    expected_api_key = (
        os.getenv("AGENTSHRINK_PROJECT_TOKEN")
        or ((product_config.get("defaults") or {}).get("gateway_api_key"))
        or "agentshrink-local"
    )
    configured_fallback_provider = (
        os.getenv("AGENTSHRINK_GATEWAY_UPSTREAM_PROVIDER")
        or upstream_provider
        or ((product_config.get("gateway") or {}).get("upstream_provider"))
        or "mock"
    )
    configured_fallback_model = (
        os.getenv("AGENTSHRINK_GATEWAY_FALLBACK_MODEL")
        or ((product_config.get("defaults") or {}).get("gateway_model"))
        or os.getenv("TARGET_AGENT_OPENAI_MODEL")
        or "gpt-4o-mini"
    )
    router = GatewayRouter(
        output_dir=output_dir,
        confidence_threshold=confidence_threshold,
        fallback_provider=configured_fallback_provider,
        fallback_model=configured_fallback_model,
    )
    upstream = OpenAICompatibleUpstream(provider=upstream_provider)
    app = create_gateway_app(upstream=upstream, db_path=db_path, router=router, expected_api_key=expected_api_key)

    console.print(Panel.fit(
        "[bold]AgentShrink Gateway[/bold]\n"
        f"Listening on http://{host}:{port}\n"
        f"Upstream provider: {upstream_provider}\n"
        f"Routing output_dir: {output_dir}",
        border_style="blue",
    ))
    if upstream_provider == "mock":
        console.print("[green]Mock upstream is enabled - local testing costs $0.[/green]")

    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.command()
@click.option("--apply-report", default=None)
@click.option("--dry-run", is_flag=True, default=False)
def shrink(apply_report, dry_run):
    """[Phase 4] Apply routing config - replace LLM calls with SLMs. Coming soon."""
    console.print("[yellow]Phase 4 (ShrinkLLM router) coming next.[/yellow]")


@cli.command()
def monitor():
    """[Phase 4+] Weekly quality check. Coming soon."""
    console.print("[yellow]Phase 4+ (monitor) coming next.[/yellow]")


if __name__ == "__main__":
    cli()
