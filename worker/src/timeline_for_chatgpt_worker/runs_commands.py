from __future__ import annotations

from pathlib import Path

from .fs_utils import load_json
from .refresh import load_runtime_config


def runs_list_payload(settings_path: Path) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    runs: list[dict[str, object]] = []
    if config.run_root.exists():
        for run_dir in sorted(config.run_root.glob("run-*")):
            status_path = run_dir / "status.json"
            result_path = run_dir / "result.json"
            status = load_json(status_path) if status_path.exists() else {}
            result = load_json(result_path) if result_path.exists() else {}
            runs.append(
                {
                    "run_id": run_dir.name,
                    "state": result.get("state") or status.get("state") or "unknown",
                    "run_dir": str(run_dir),
                    "completed_at": status.get("completed_at"),
                    "processed_count": result.get("processed_count"),
                }
            )
    return {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "run_root": str(config.run_root),
        "run_count": len(runs),
        "runs": runs,
        "summary": f"{len(runs)} runs",
    }


def runs_show_payload(settings_path: Path, run_id: str) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    run_dir = (config.run_root / run_id).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"Run does not exist: {run_dir}")
    payload: dict[str, object] = {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "summary": str(run_dir),
    }
    for name in ("request", "status", "result", "manifest"):
        path = run_dir / f"{name}.json"
        payload[name] = load_json(path) if path.exists() else None
    return payload
