import json
import pathlib
import threading
import time
import uuid
from typing import Any


def slugify_name(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in (value or "cluster"))
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "cluster"


def recommended_model_name(cluster_name: str) -> str:
    return f"agentshrink-{slugify_name(cluster_name)}-ft"


def recommended_display_name(cluster_name: str) -> str:
    words = [part for part in slugify_name(cluster_name).split("-") if part]
    return f"{' '.join(word.capitalize() for word in words) or 'Cluster'} FT"


class FineTuneJobStore:
    def __init__(self, output_dir: pathlib.Path):
        self.base_dir = pathlib.Path(output_dir) / "finetune_jobs"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _job_path(self, job_id: str) -> pathlib.Path:
        return self.base_dir / f"{job_id}.json"

    def _read(self, path: pathlib.Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, path: pathlib.Path, payload: dict[str, Any]) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        tmp.replace(path)

    def create_job(
        self,
        *,
        cluster_id: int,
        cluster_name: str,
        backend: str,
        config: dict[str, Any],
        dataset_path: pathlib.Path,
        sample_count: int,
        base_model: str,
        deploy_base_model: str,
    ) -> dict[str, Any]:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        job_id = f"ft_{uuid.uuid4().hex[:12]}"
        payload = {
            "job_id": job_id,
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "backend": backend,
            "status": "queued",
            "phase": "queued",
            "progress": 0,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "ended_at": None,
            "config": config,
            "dataset_path": str(dataset_path),
            "sample_count": sample_count,
            "base_model": base_model,
            "deploy_base_model": deploy_base_model,
            "recommended_model_name": recommended_model_name(cluster_name),
            "recommended_display_name": recommended_display_name(cluster_name),
            "logs": [],
            "metrics": [],
            "artifacts": {},
            "result": {},
            "error": None,
            "stop_requested": False,
            "can_register": False,
            "registered_model": None,
        }
        with self._lock:
            self._write(self._job_path(job_id), payload)
        return payload

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = []
            for path in sorted(self.base_dir.glob("ft_*.json")):
                job = self._read(path)
                if job:
                    jobs.append(job)
            jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            return jobs

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._read(self._job_path(job_id))

    def latest_for_cluster(self, cluster_id: int) -> dict[str, Any] | None:
        jobs = [job for job in self.list_jobs() if int(job.get("cluster_id", -1)) == int(cluster_id)]
        return jobs[0] if jobs else None

    def save_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._write(self._job_path(payload["job_id"]), payload)
        return payload

    def update_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            payload = self._read(self._job_path(job_id))
            if not payload:
                raise KeyError(job_id)
            payload.update(changes)
            payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._write(self._job_path(job_id), payload)
            return payload

    def append_log(self, job_id: str, message: str, *, level: str = "info") -> dict[str, Any]:
        with self._lock:
            payload = self._read(self._job_path(job_id))
            if not payload:
                raise KeyError(job_id)
            logs = payload.setdefault("logs", [])
            logs.append({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "level": level,
                "message": message,
            })
            payload["logs"] = logs[-200:]
            payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._write(self._job_path(job_id), payload)
            return payload

    def append_metric(self, job_id: str, metric: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = self._read(self._job_path(job_id))
            if not payload:
                raise KeyError(job_id)
            metrics = payload.setdefault("metrics", [])
            metrics.append(metric)
            payload["metrics"] = metrics[-500:]
            payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._write(self._job_path(job_id), payload)
            return payload
