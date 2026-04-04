from __future__ import annotations

import os
import traceback
from pathlib import Path

from .contracts import JobRequest, JobResult, JobStatus
from .fs_utils import append_log, ensure_dir, load_json, now_iso, write_json
from .parser import normalize_export


def outputs_root() -> Path:
    return Path(os.environ.get("CHATGPT2TIMELINE_OUTPUTS_ROOT", "/shared/outputs"))


def iter_pending_runs() -> list[Path]:
    root = outputs_root()
    if not root.exists():
        return []

    rows: list[Path] = []
    for run_dir in sorted(root.glob("job-*")):
        status_path = run_dir / "status.json"
        if not status_path.exists():
            continue
        status = load_json(status_path)
        if str(status.get("state") or "").lower() == "pending":
            rows.append(run_dir)
    return rows


def process_pending_jobs() -> int:
    processed = 0
    for run_dir in iter_pending_runs():
        process_job(run_dir)
        processed += 1
    return processed


def process_job(run_dir: Path) -> None:
    request = JobRequest.from_dict(load_json(run_dir / "request.json"))
    status = JobStatus(job_id=request.job_id, state="running", current_stage="starting", started_at=now_iso(), updated_at=now_iso())
    result = JobResult(
        job_id=request.job_id,
        state="running",
        run_dir=str(run_dir),
        output_root_id=request.output_root_id,
        output_root_path=request.output_root_path,
    )

    log_path = ensure_dir(run_dir / "logs") / "worker.log"
    append_log(log_path, f"[{now_iso()}] starting {request.job_id}")

    try:
        status.message = "Preparing export input."
        status.current_stage = "extract_zip"
        status.updated_at = now_iso()
        write_json(run_dir / "status.json", status.to_dict())
        append_log(log_path, f"[{now_iso()}] extract_zip Preparing export input.")

        last_logged_stage = status.current_stage
        last_logged_done = -1

        def handle_progress(payload: dict[str, object]) -> None:
            nonlocal last_logged_stage, last_logged_done
            status.current_stage = str(payload.get("stage") or status.current_stage)
            status.message = str(payload.get("message") or status.message)
            if "conversations_total" in payload:
                status.conversations_total = int(payload["conversations_total"] or 0)
            if "conversations_done" in payload:
                status.conversations_done = int(payload["conversations_done"] or 0)
            status.current_conversation = payload.get("current_conversation") or None
            if status.conversations_total > 0:
                completed = status.conversations_done + status.conversations_skipped + status.conversations_failed
                status.progress_percent = round((completed / status.conversations_total) * 100, 1)
            status.updated_at = now_iso()
            write_json(run_dir / "status.json", status.to_dict())
            should_log = status.current_stage != last_logged_stage
            if status.conversations_done in {1, status.conversations_total}:
                should_log = True
            if status.conversations_done > 0 and status.conversations_done - last_logged_done >= 250:
                should_log = True
            if should_log:
                suffix = f" current={status.current_conversation}" if status.current_conversation else ""
                append_log(
                    log_path,
                    f"[{now_iso()}] {status.current_stage} {status.message}{suffix}",
                )
                last_logged_stage = status.current_stage
                last_logged_done = status.conversations_done

        normalized = normalize_export(run_dir, request, on_progress=handle_progress)

        status.current_stage = "completed"
        status.state = "completed"
        status.message = "Finished processing export."
        status.conversations_total = len(normalized["conversation_rows"])
        status.conversations_done = len(normalized["conversation_rows"])
        status.progress_percent = 100.0
        status.updated_at = now_iso()
        status.completed_at = status.updated_at

        result.state = "completed"
        result.processed_count = len(normalized["conversation_rows"])
        result.error_count = 0
        result.batch_count = int(normalized["batch_count"])
        result.conversation_index_path = normalized["conversation_index_path"]
        result.archive_path = normalized["archive_path"]

        manifest = {
            "schema_version": 1,
            "job_id": request.job_id,
            "generated_at": now_iso(),
            "items": normalized["manifest_items"],
        }

        write_json(run_dir / "manifest.json", manifest)
        write_json(run_dir / "status.json", status.to_dict())
        write_json(run_dir / "result.json", result.to_dict())
        append_log(log_path, f"[{now_iso()}] completed {request.job_id}")
    except Exception as exc:  # noqa: BLE001
        status.state = "failed"
        status.current_stage = "failed"
        status.message = str(exc)
        status.updated_at = now_iso()
        status.completed_at = status.updated_at
        status.warnings.append("Worker failed before the scaffold parser could complete.")
        result.state = "failed"
        result.error_count = max(1, result.error_count)
        result.warnings.append(str(exc))
        write_json(run_dir / "status.json", status.to_dict())
        write_json(run_dir / "result.json", result.to_dict())
        append_log(log_path, f"[{now_iso()}] failed {request.job_id}")
        append_log(log_path, traceback.format_exc())
