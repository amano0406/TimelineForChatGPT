from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .contracts import RunRequest
from .fs_utils import ensure_dir, load_json, now_iso, write_json

APPLICATION_NAME = "TimelineForChatGPT"
THREAD_ROLES = {"user", "assistant", "system"}
TIMELINE_FILE_NAME = "timeline.json"


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


def build_download_zip(master_root: Path, destination: Path, manifest: dict[str, Any]) -> Path:
    ensure_dir(destination.parent)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", build_download_readme(manifest))
        for item in manifest.get("items") or []:
            if not isinstance(item, dict):
                continue
            conversation_id = str(item.get("conversation_id") or item.get("id") or "")
            if not conversation_id:
                continue
            item_root = master_root / conversation_id
            archive.write(item_root / "convert_info.json", f"items/{conversation_id}/convert_info.json")
            archive.write(item_root / TIMELINE_FILE_NAME, f"items/{conversation_id}/{TIMELINE_FILE_NAME}")
    return destination


def build_download_readme(manifest: dict[str, Any]) -> str:
    source = manifest.get("source_export") if isinstance(manifest.get("source_export"), dict) else {}
    return "\n".join(
        [
            "# TimelineForChatGPT Export",
            "",
            "This package was generated by TimelineForChatGPT from a ChatGPT export ZIP.",
            "",
            "Contents:",
            "",
            "- `README.md`: this file.",
            "- `items/<conversation_id>/convert_info.json`: conversion metadata for one conversation.",
            "- `items/<conversation_id>/timeline.json`: final exported title and user / assistant / system messages in conversation order.",
            "",
            f"- Generated at: `{manifest.get('generated_at') or '-'}`",
            f"- Run ID: `{manifest.get('run_id') or '-'}`",
            f"- Source file: `{source.get('filename') or '-'}`",
            f"- Conversation count: `{manifest.get('item_count', 0)}`",
            "",
        ]
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def source_export_info(request: RunRequest) -> dict[str, Any]:
    item = request.input_items[0] if request.input_items else None
    path = Path(item.uploaded_path or item.original_path).expanduser().resolve() if item else None
    payload: dict[str, Any] = {
        "source_kind": item.source_kind if item else "unknown",
        "source_id": item.source_id if item else "unknown",
        "filename": item.display_name if item else "",
        "path": str(path) if path else "",
        "size_bytes": item.size_bytes if item else 0,
    }
    if path and path.is_file():
        payload["sha256"] = hash_file_sha256(path)
        payload["size_bytes"] = path.stat().st_size
    return payload


def hash_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_directory(path: Path) -> None:
    ensure_safe_replace_root(path)
    ensure_dir(path)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def ensure_safe_replace_root(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved == Path(resolved.anchor) or str(resolved) in {"/", "/mnt", "/mnt/c"}:
        raise ValueError(f"Refusing to replace unsafe outputRoot: {resolved}")
    configured_output_root = os.environ.get("TIMELINE_FOR_CHATGPT_OUTPUT_ROOT")
    if configured_output_root:
        configured = Path(configured_output_root).expanduser().resolve()
        if resolved == configured:
            return
    if len(resolved.parts) < 4:
        raise ValueError(f"Refusing to replace too-shallow outputRoot: {resolved}")
