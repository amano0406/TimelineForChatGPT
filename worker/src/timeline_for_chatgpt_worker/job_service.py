from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any

from .contracts import RunStatus
from .fs_utils import ensure_dir, load_json, now_iso, write_json
from .item_service import items_refresh_from_file
from .refresh import load_runtime_config
from .run_requests import build_run_id

PRODUCT_ID = "chatgpt"
PRODUCT_NAME = "TimelineForChatGPT"
CANCEL_REQUEST_FILE = ".cancel-requested"

_ACTIVE_JOBS: set[str] = set()
_ACTIVE_LOCK = threading.Lock()


def start_refresh_job(
    *,
    file_path: Path,
    settings_path: Path,
    download_to: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    config = load_runtime_config(settings_path)
    ensure_dir(config.run_root)
    resolved_file = file_path.expanduser().resolve()
    run_id = build_run_id(resolved_file)
    run_dir = ensure_dir(config.run_root / run_id)
    created_at = now_iso()
    write_json(
        run_dir / "job_options.json",
        {
            "schema_version": 1,
            "type": "refresh",
            "file_path": str(resolved_file),
            "download_to": str(download_to.expanduser().resolve()) if download_to else "",
            "overwrite": overwrite,
            "settings_path": str(settings_path),
            "created_at": created_at,
        },
    )
    write_json(
        run_dir / "status.json",
        RunStatus(
            run_id=run_id,
            state="queued",
            current_stage="queued",
            message="ChatGPT export ZIP import has been queued.",
            updated_at=created_at,
        ).to_dict(),
    )

    with _ACTIVE_LOCK:
        _ACTIVE_JOBS.add(run_id)

    thread = threading.Thread(
        target=_run_refresh_job,
        kwargs={
            "run_id": run_id,
            "file_path": resolved_file,
            "settings_path": settings_path,
            "download_to": download_to,
            "overwrite": overwrite,
        },
        name=f"chatgpt-refresh-{run_id}",
        daemon=True,
    )
    thread.start()
    return job_status_payload(settings_path, run_id)


def job_status_payload(settings_path: Path, job_id: str) -> dict[str, Any]:
    config = load_runtime_config(settings_path)
    run_dir = config.run_root / job_id
    status = _read_json(run_dir / "status.json")
    result = _read_json(run_dir / "job_result.json") or _read_json(run_dir / "result.json")
    options = _read_json(run_dir / "job_options.json")
    if status is None:
        return _empty_job_payload(
            state="missing",
            message="ChatGPT import job was not found.",
            job_id=job_id,
        )

    state = str(status.get("state") or "").strip()
    stage = str(status.get("current_stage") or status.get("stage") or "").strip()
    total = _int_value(status.get("conversations_total"))
    done = _int_value(status.get("conversations_done"))
    failed = _int_value(status.get("conversations_failed"))
    percent = _float_value(status.get("progress_percent"))
    error = str(status.get("message") or "") if state.lower() == "failed" else ""
    payload: dict[str, Any] = {
        "schemaVersion": "timeline.product_job.v1",
        "productId": PRODUCT_ID,
        "productName": PRODUCT_NAME,
        "type": "refresh",
        "jobId": str(status.get("run_id") or job_id),
        "state": state or "unknown",
        "phase": stage,
        "stage": stage,
        "message": str(status.get("message") or ""),
        "progress": {
            "percent": percent,
            "current": done,
            "total": total,
            "unit": "conversations",
            "currentItem": str(status.get("current_conversation") or ""),
            "estimatedRemainingSeconds": status.get("estimated_remaining_sec"),
        },
        "startedAt": str(status.get("started_at") or ""),
        "updatedAt": str(status.get("updated_at") or ""),
        "completedAt": str(status.get("completed_at") or ""),
        "error": error,
        "warnings": status.get("warnings") if isinstance(status.get("warnings"), list) else [],
        "result": result or {},
        "details": {
            "conversationsSkipped": _int_value(status.get("conversations_skipped")),
            "conversationsFailed": failed,
            "inputPath": str(options.get("file_path") or "") if isinstance(options, dict) else "",
            "runDirectory": str(run_dir),
        },
    }
    return payload


def active_job_payload(settings_path: Path) -> dict[str, Any]:
    active = active_job_id(settings_path)
    if active:
        return job_status_payload(settings_path, active)
    return _empty_job_payload("none", "No active ChatGPT import job exists.")


def cancel_job(settings_path: Path, job_id: str) -> dict[str, Any]:
    config = load_runtime_config(settings_path)
    run_dir = config.run_root / job_id
    if not run_dir.exists():
        return _empty_job_payload("missing", "ChatGPT import job was not found.", job_id=job_id)
    now = now_iso()
    status = _read_json(run_dir / "status.json") or {"schema_version": 1, "run_id": job_id}
    if not _is_active_state(str(status.get("state") or "")):
        return job_status_payload(settings_path, job_id)
    write_json(run_dir / CANCEL_REQUEST_FILE, {"requested_at": now, "message": "Cancellation requested."})
    status["state"] = "canceling"
    status["current_stage"] = "canceling"
    status["message"] = "ChatGPT import cancellation was requested."
    status["updated_at"] = now
    write_json(run_dir / "status.json", status)
    return job_status_payload(settings_path, job_id)


def jobs_list_payload(settings_path: Path, limit: int = 20) -> dict[str, Any]:
    config = load_runtime_config(settings_path)
    jobs = [
        job_status_payload(settings_path, path.name)
        for path in _iter_run_dirs(config.run_root)[: max(1, limit)]
    ]
    return {
        "schemaVersion": 1,
        "productId": PRODUCT_ID,
        "productName": PRODUCT_NAME,
        "jobs": jobs,
    }


def active_job_id(settings_path: Path) -> str:
    config = load_runtime_config(settings_path)
    with _ACTIVE_LOCK:
        for job_id in list(_ACTIVE_JOBS):
            status = _read_json(config.run_root / job_id / "status.json")
            if _is_active_state(str((status or {}).get("state") or "")):
                return job_id
            _ACTIVE_JOBS.discard(job_id)

    for run_dir in _iter_run_dirs(config.run_root):
        status = _read_json(run_dir / "status.json")
        if _is_active_state(str((status or {}).get("state") or "")):
            return run_dir.name
    return ""


def _run_refresh_job(
    *,
    run_id: str,
    file_path: Path,
    settings_path: Path,
    download_to: Path | None,
    overwrite: bool,
) -> None:
    try:
        result = items_refresh_from_file(
            file_path=file_path,
            settings_path=settings_path,
            download_to=download_to,
            overwrite=overwrite,
            run_id=run_id,
        )
        config = load_runtime_config(settings_path)
        write_json(config.run_root / run_id / "job_result.json", result)
    except Exception as exc:  # noqa: BLE001
        _write_failed_status(settings_path, run_id, str(exc))
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_JOBS.discard(run_id)


def _write_failed_status(settings_path: Path, run_id: str, message: str) -> None:
    config = load_runtime_config(settings_path)
    run_dir = ensure_dir(config.run_root / run_id)
    status_path = run_dir / "status.json"
    status = _read_json(status_path) or {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": None,
    }
    status["run_id"] = str(status.get("run_id") or run_id)
    status["state"] = "failed"
    status["current_stage"] = str(status.get("current_stage") or "failed")
    status["message"] = message
    status["updated_at"] = now_iso()
    status["completed_at"] = status["updated_at"]
    warnings = status.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    if message and message not in warnings:
        warnings.append(message)
    status["warnings"] = warnings
    write_json(status_path, status)
    write_json(
        run_dir / "job_result.json",
        {
            "schema_version": 1,
            "state": "failed",
            "message": message,
        },
    )


def _empty_job_payload(state: str, message: str, job_id: str = "") -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schemaVersion": "timeline.product_job.v1",
        "productId": PRODUCT_ID,
        "productName": PRODUCT_NAME,
        "type": "refresh",
        "jobId": job_id,
        "state": state,
        "phase": "",
        "stage": "",
        "message": message,
        "progress": {
            "percent": 0,
            "current": 0,
            "total": 0,
            "unit": "conversations",
            "currentItem": "",
            "estimatedRemainingSeconds": None,
        },
        "startedAt": "",
        "updatedAt": now,
        "completedAt": "",
        "error": message if state == "failed" else "",
        "warnings": [],
        "result": {},
        "details": {},
    }


def _iter_run_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        [path for path in root.iterdir() if path.is_dir() and path.name.startswith("run-")],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = load_json(path)
    except (FileNotFoundError, OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _is_active_state(state: str) -> bool:
    return state.lower() in {"pending", "queued", "running", "processing", "starting", "canceling"}


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
