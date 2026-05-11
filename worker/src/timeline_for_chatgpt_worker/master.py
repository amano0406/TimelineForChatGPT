from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import RunRequest
from .fs_utils import ensure_dir, load_json, now_iso, write_json
from .jsonl_io import read_jsonl
from .master_download import build_download_zip
from .output_safety import replace_directory
from .product_constants import APPLICATION_NAME, TIMELINE_FILE_NAME
from .source_info import source_export_info

THREAD_ROLES = {"user", "assistant", "system"}


def rebuild_master_from_run(run_dir: Path, master_root: Path, request: RunRequest | None = None) -> dict[str, Any]:
    resolved_run_dir = run_dir.expanduser().resolve()
    resolved_master_root = master_root.expanduser().resolve()
    request_payload = request or RunRequest.from_dict(load_json(resolved_run_dir / "request.json"))
    source = source_export_info(request_payload)
    generated_at = now_iso()

    replace_directory(resolved_master_root)

    rows = read_jsonl(resolved_run_dir / "conversation_index.jsonl")
    items: list[dict[str, Any]] = []
    for summary in rows:
        conversation_id = str(summary.get("conversation_id") or "").strip()
        if not conversation_id:
            continue
        item_root = ensure_dir(resolved_master_root / conversation_id)
        messages_path = resolved_run_dir / "conversations" / conversation_id / "messages.jsonl"
        all_messages = read_jsonl(messages_path)
        thread_messages = [
            build_thread_message(message)
            for message in all_messages
            if str(message.get("role") or "").lower() in THREAD_ROLES
        ]
        thread = build_thread_payload(summary, thread_messages)
        convert_info = build_convert_info_payload(
            summary=summary,
            request=request_payload,
            source=source,
            generated_at=generated_at,
            all_message_count=len(all_messages),
            thread_message_count=len(thread_messages),
        )
        write_json(item_root / "convert_info.json", convert_info)
        write_json(item_root / TIMELINE_FILE_NAME, thread)
        items.append(
            {
                "id": conversation_id,
                "conversation_id": conversation_id,
                "title": summary.get("title") or "",
                "created_at": summary.get("create_time"),
                "updated_at": summary.get("update_time"),
                "started_at_utc": summary.get("started_at_utc"),
                "ended_at_utc": summary.get("ended_at_utc"),
                "message_count": len(thread_messages),
                "convert_info_path": f"{conversation_id}/convert_info.json",
                "timeline_path": f"{conversation_id}/{TIMELINE_FILE_NAME}",
            }
        )

    manifest = {
        "schema_version": 1,
        "application": APPLICATION_NAME,
        "generated_at": generated_at,
        "run_id": request_payload.run_id,
        "source_export": source,
        "item_count": len(items),
        "items": items,
    }
    write_json(resolved_master_root / "manifest.json", manifest)

    download_root = ensure_dir(resolved_run_dir / "export")
    download_zip_path = download_root / f"{APPLICATION_NAME}-export-{request_payload.run_id}.zip"
    build_download_zip(
        master_root=resolved_master_root,
        destination=download_zip_path,
        manifest=manifest,
    )
    manifest["download_zip_path"] = str(download_zip_path)
    write_json(resolved_master_root / "manifest.json", manifest)
    return manifest


def build_thread_payload(summary: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "application": APPLICATION_NAME,
        "conversation_id": summary.get("conversation_id"),
        "title": summary.get("title") or "",
        "created_at": summary.get("create_time"),
        "updated_at": summary.get("update_time"),
        "started_at_utc": summary.get("started_at_utc"),
        "ended_at_utc": summary.get("ended_at_utc"),
        "message_count": len(messages),
        "messages": messages,
    }


def build_thread_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": message.get("message_id") or "",
        "parent_message_id": message.get("parent_message_id") or "",
        "created_at": message.get("created_at"),
        "role": message.get("role") or "unknown",
        "content_type": message.get("content_type") or "unknown",
        "model_slug": message.get("model_slug") or "",
        "text": message.get("text") or "",
        "attachments": message.get("asset_refs") or [],
    }


def build_convert_info_payload(
    summary: dict[str, Any],
    request: RunRequest,
    source: dict[str, Any],
    generated_at: str,
    all_message_count: int,
    thread_message_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "application": APPLICATION_NAME,
        "generated_at": generated_at,
        "run_id": request.run_id,
        "conversation_id": summary.get("conversation_id"),
        "title": summary.get("title") or "",
        "source_export": source,
        "counts": {
            "message_count_total": summary.get("message_count_total", all_message_count),
            "main_branch_message_count": summary.get("main_branch_message_count", all_message_count),
            "thread_message_count": thread_message_count,
            "all_normalized_message_count": all_message_count,
            "attachment_count": summary.get("attachment_count", 0),
            "image_count": summary.get("image_count", 0),
            "audio_count": summary.get("audio_count", 0),
            "tool_count": summary.get("tool_count", 0),
        },
        "time_bounds": {
            "created_at": summary.get("create_time"),
            "updated_at": summary.get("update_time"),
            "started_at_utc": summary.get("started_at_utc"),
            "ended_at_utc": summary.get("ended_at_utc"),
        },
        "output_files": {
            "convert_info": "convert_info.json",
            "timeline": TIMELINE_FILE_NAME,
        },
    }
