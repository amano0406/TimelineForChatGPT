from __future__ import annotations

import time
from pathlib import Path

from .fs_utils import ensure_dir, load_json, now_iso, write_json
from .processor import process_run
from .refresh import (
    build_refresh_run_id,
    build_refresh_report_path,
    discover_inputs,
    fingerprint_file,
    load_refresh_state,
    load_runtime_config,
    refresh_lock,
    same_fingerprint,
    validate_runtime_config,
    write_refresh_index,
    write_refresh_latest_markdown,
    write_refresh_state,
)
from .run_requests import create_run_from_input


def refresh_from_config(config_path: Path, dry_run: bool = False, force: bool = False) -> dict[str, object]:
    refresh_started_perf = time.perf_counter()
    config = load_runtime_config(config_path)
    warnings = validate_runtime_config(config)
    started_at = now_iso()
    ensure_dir(config.run_root)
    ensure_dir(config.state_root)
    with refresh_lock(config.state_root):
        state = load_refresh_state(config.state_root)
        state_items = state.setdefault("items", {})
        report_items: list[dict[str, object]] = []
        processed = 0
        skipped = 0
        failed = 0
        missing = 0
        duplicate = 0
        fingerprint_seconds_total = 0.0
        processing_seconds_total = 0.0

        discovery_started_perf = time.perf_counter()
        discovered_rows = discover_inputs(config)
        discovery_seconds = elapsed_seconds(discovery_started_perf)
        discovered_keys = {str(input_path) for _, input_path in discovered_rows}
        seen_sha: dict[str, dict[str, object]] = {}

        for key, previous in sorted(state_items.items()):
            if key in discovered_keys or not isinstance(previous, dict):
                continue
            missing += 1
            report_items.append(
                {
                    "input_root_id": previous.get("input_root_id"),
                    "input_path": key,
                    "status": "missing_from_input",
                    "previous_run_dir": previous.get("run_dir"),
                    "result_state": previous.get("result_state"),
                    "fingerprint": previous.get("fingerprint"),
                }
            )

        for input_root, input_path in discovered_rows:
            key = str(input_path)
            previous = state_items.get(key) if isinstance(state_items.get(key), dict) else {}
            fingerprint_started_perf = time.perf_counter()
            fingerprint = fingerprint_file(input_path, previous)
            fingerprint_seconds = elapsed_seconds(fingerprint_started_perf)
            fingerprint_seconds_total += fingerprint_seconds
            sha256 = str(fingerprint.get("sha256") or "")
            if sha256 and sha256 in seen_sha and not force:
                duplicate += 1
                skipped += 1
                first_seen = seen_sha[sha256]
                report_items.append(
                    {
                        "input_root_id": input_root.root_id,
                        "input_path": str(input_path),
                        "status": "duplicate_skipped",
                        "duplicate_of": first_seen.get("input_path"),
                        "duplicate_run_dir": first_seen.get("run_dir") or first_seen.get("previous_run_dir"),
                        "fingerprint": fingerprint,
                        "timing": {
                            "fingerprint_seconds": fingerprint_seconds,
                            "processing_seconds": 0.0,
                        },
                    }
                )
                continue

            previous_fingerprint = (previous or {}).get("fingerprint") or {}
            previous_state = str((previous or {}).get("result_state") or "")
            previous_run_dir = Path(str((previous or {}).get("run_dir") or ""))
            unchanged = same_fingerprint(fingerprint, previous_fingerprint)
            can_skip = (
                unchanged
                and not force
                and previous_state in {"completed", "failed"}
                and previous_run_dir.exists()
            )

            if can_skip:
                skipped += 1
                item = {
                    "input_root_id": input_root.root_id,
                    "input_path": str(input_path),
                    "status": "skipped_unchanged",
                    "previous_run_dir": str(previous_run_dir),
                    "result_state": previous_state,
                    "fingerprint": fingerprint,
                    "timing": {
                        "fingerprint_seconds": fingerprint_seconds,
                        "processing_seconds": 0.0,
                    },
                }
                report_items.append(item)
                if sha256:
                    seen_sha[sha256] = item
                continue

            run_id = build_refresh_run_id(input_root.root_id, input_path, fingerprint, started_at)
            if dry_run:
                skipped += 1
                item = {
                    "input_root_id": input_root.root_id,
                    "input_path": str(input_path),
                    "status": "would_process",
                    "run_id": run_id,
                    "fingerprint": fingerprint,
                    "timing": {
                        "fingerprint_seconds": fingerprint_seconds,
                        "processing_seconds": 0.0,
                    },
                }
                report_items.append(item)
                if sha256:
                    seen_sha[sha256] = item
                continue

            run_dir = create_run_from_input(
                input_path=input_path,
                output_root=config.run_root,
                profile=config.profile,
                run_id=run_id,
                source_id=input_root.root_id,
            )
            processing_started_perf = time.perf_counter()
            process_run(run_dir)
            processing_seconds = elapsed_seconds(processing_started_perf)
            processing_seconds_total += processing_seconds
            status_payload = load_json(run_dir / "status.json")
            result_payload = load_json(run_dir / "result.json")
            result_state = str(result_payload.get("state") or status_payload.get("state") or "unknown")
            if result_state == "completed":
                processed += 1
            else:
                failed += 1

            updated_at = now_iso()
            state_entry = {
                "input_root_id": input_root.root_id,
                "input_path": str(input_path),
                "display_name": input_path.name,
                "fingerprint": fingerprint,
                "run_dir": str(run_dir),
                "run_id": run_id,
                "result_state": result_state,
                "updated_at": updated_at,
            }
            if result_state == "completed":
                state_entry["latest_success_run_dir"] = str(run_dir)
                state_entry["latest_success_run_id"] = run_id
                state_entry["latest_success_at"] = updated_at
            elif isinstance(previous, dict):
                for success_key in ("latest_success_run_dir", "latest_success_run_id", "latest_success_at"):
                    if previous.get(success_key):
                        state_entry[success_key] = previous[success_key]
            state_items[key] = state_entry
            item = {
                "input_root_id": input_root.root_id,
                "input_path": str(input_path),
                "status": result_state,
                "run_dir": str(run_dir),
                "run_id": run_id,
                "fingerprint": fingerprint,
                "message": status_payload.get("message"),
                "timing": {
                    "fingerprint_seconds": fingerprint_seconds,
                    "processing_seconds": processing_seconds,
                },
            }
            report_items.append(item)
            if sha256:
                seen_sha[sha256] = item

        completed_at = now_iso()
        state["updated_at"] = completed_at
        if not dry_run:
            write_refresh_state(config.state_root, state)

        report_path = build_refresh_report_path(config.run_root, started_at)
        report = {
            "schema_version": 1,
            "started_at": started_at,
            "completed_at": completed_at,
            "config_path": str(config_path),
            "output_root": str(config.output_root),
            "run_root": str(config.run_root),
            "state_root": str(config.state_root),
            "dry_run": dry_run,
            "force": force,
            "warnings": warnings,
            "summary": {
                "discovered": len(discovered_rows),
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "missing": missing,
                "duplicates": duplicate,
                "duration_seconds": elapsed_seconds(refresh_started_perf),
                "discovery_seconds": discovery_seconds,
                "fingerprint_seconds": round(fingerprint_seconds_total, 6),
                "processing_seconds": round(processing_seconds_total, 6),
            },
            "items": report_items,
            "report_path": str(report_path),
        }
        latest_path = config.run_root / "refresh-latest.md"
        report["latest_markdown_path"] = str(latest_path)
        index_json_path = config.run_root / "index.json"
        index_markdown_path = config.run_root / "index.md"
        report["index_json_path"] = str(index_json_path)
        report["index_markdown_path"] = str(index_markdown_path)
        write_json(report_path, report)
        write_refresh_latest_markdown(config.run_root, report)
        write_refresh_index(config.run_root, state, report)
        return report


def elapsed_seconds(started_perf: float) -> float:
    return round(time.perf_counter() - started_perf, 6)
