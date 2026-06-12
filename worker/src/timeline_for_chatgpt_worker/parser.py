from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .conversation_parts import (
    build_events,
    build_segments,
    extract_asset_refs,
    format_timestamp,
    max_utc,
    message_time_bounds,
    min_utc,
    render_timeline_markdown,
)
from .contracts import RunRequest
from .export_source import load_conversations, prepare_export_root, try_load_analysis_summary
from .fs_utils import ensure_dir, write_json, write_jsonl
from .run_pack import build_llm_pack


def normalize_export(
    run_dir: Path,
    request: RunRequest,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    export_root, input_name, cleanup_root = prepare_export_root(run_dir, request)
    try:
        conversations, conversation_file_count = load_conversations(export_root)
        analysis_summary = try_load_analysis_summary(export_root)

        conversation_rows: list[dict[str, Any]] = []
        manifest_items: list[dict[str, Any]] = []
        role_counts: Counter[str] = Counter()
        content_type_counts: Counter[str] = Counter()
        total_messages = 0
        date_min: str | None = None
        date_max: str | None = None

        conversations_root = ensure_dir(run_dir / "conversations")
        llm_root = ensure_dir(run_dir / "llm")

        if on_progress is not None:
            on_progress(
                {
                    "stage": "parse_conversations",
                    "message": "Loaded conversation files.",
                    "conversations_total": len(conversations),
                    "conversations_done": 0,
                    "current_conversation": None,
                }
            )

        for index, conversation in enumerate(conversations, start=1):
            if cancel_check is not None:
                cancel_check("parse_conversations")
            normalized = normalize_conversation(conversation, request, export_root)
            summary = normalized["summary"]
            messages = normalized["messages"]
            events = normalized["events"]
            segments = normalized["segments"]
            total_messages += summary["message_count_total"]
            role_counts.update(normalized["role_counts"])
            content_type_counts.update(normalized["content_type_counts"])
            date_min = min_utc(date_min, summary.get("create_time"))
            date_max = max_utc(date_max, summary.get("update_time"))

            conversation_rows.append(summary)
            manifest_items.append(
                {
                    "conversation_id": summary["conversation_id"],
                    "title": summary["title"],
                    "status": "completed",
                    "started_at_utc": summary["started_at_utc"],
                    "ended_at_utc": summary["ended_at_utc"],
                    "message_count_total": summary["message_count_total"],
                    "main_branch_message_count": summary["main_branch_message_count"],
                    "branch_count": summary["branch_count"],
                    "attachment_count": summary["attachment_count"],
                    "image_count": summary["image_count"],
                    "audio_count": summary["audio_count"],
                    "tool_count": summary["tool_count"],
                    "has_tool_messages": summary["has_tool_messages"],
                    "has_system_messages": summary["has_system_messages"],
                    "has_attachments": summary["has_attachments"],
                    "has_multimodal_content": summary["has_multimodal_content"],
                    "timeline_path": summary["timeline_path"],
                }
            )

            conversation_dir = ensure_dir(conversations_root / summary["conversation_id"])
            if cancel_check is not None:
                cancel_check("write_conversation")
            write_json(conversation_dir / "conversation.json", conversation)
            write_jsonl(conversation_dir / "messages.jsonl", messages)
            write_jsonl(conversation_dir / "events.jsonl", events)
            write_json(conversation_dir / "segments.json", {"items": segments})
            (conversation_dir / "timeline.md").write_text(normalized["timeline_markdown"], encoding="utf-8")
            write_json(conversation_dir / "attachments.json", {"items": normalized["asset_refs"]})

            if on_progress is not None and (index == 1 or index % 25 == 0 or index == len(conversations)):
                on_progress(
                    {
                        "stage": "parse_conversations",
                        "message": f"Processed {index} / {len(conversations)} conversations.",
                        "conversations_total": len(conversations),
                        "conversations_done": index,
                        "current_conversation": summary["title"] or summary["conversation_id"],
                    }
                )

        write_jsonl(run_dir / "conversation_index.jsonl", conversation_rows)
        if cancel_check is not None:
            cancel_check("build_indexes")
        export_summary = {
            "run_id": request.run_id,
            "input_name": input_name,
            "conversation_files": conversation_file_count,
            "total_conversations": int(analysis_summary.get("total_conversations", len(conversation_rows))),
            "total_messages": int(analysis_summary.get("total_messages", total_messages)),
            "message_role_counts": analysis_summary.get("message_roles", dict(role_counts)),
            "message_content_type_counts": analysis_summary.get("message_content_types", dict(content_type_counts)),
            "date_min_utc": analysis_summary.get("date_min_utc", date_min),
            "date_max_utc": analysis_summary.get("date_max_utc", date_max),
        }
        write_json(run_dir / "export_summary.json", export_summary)

        if on_progress is not None:
            on_progress(
                {
                    "stage": "build_indexes",
                    "message": "Building LLM pack and archive.",
                    "conversations_total": len(conversation_rows),
                    "conversations_done": len(conversation_rows),
                    "current_conversation": None,
                }
            )

        batch_count = build_llm_pack(llm_root, conversation_rows, conversations_root, cancel_check=cancel_check)
        archive_path = run_dir / f"{request.run_id}.zip"

        return {
            "export_summary": export_summary,
            "conversation_rows": conversation_rows,
            "manifest_items": manifest_items,
            "batch_count": batch_count,
            "archive_path": str(archive_path),
            "conversation_index_path": str(run_dir / "conversation_index.jsonl"),
        }
    finally:
        if cleanup_root is not None and cleanup_root.exists():
            shutil.rmtree(cleanup_root, ignore_errors=True)


def normalize_conversation(
    conversation: dict[str, Any],
    request: RunRequest,
    export_root: Path | None = None,
) -> dict[str, Any]:
    conversation_id = str(conversation.get("conversation_id") or conversation.get("id") or "")
    title = str(conversation.get("title") or conversation_id or "Untitled conversation")
    mapping = conversation.get("mapping") or {}
    if not isinstance(mapping, dict):
        mapping = {}

    message_nodes = [
        (node_id, node)
        for node_id, node in mapping.items()
        if isinstance(node, dict) and isinstance(node.get("message"), dict)
    ]
    role_counts: Counter[str] = Counter()
    content_type_counts: Counter[str] = Counter()
    main_branch_role_counts: Counter[str] = Counter()
    main_branch_content_type_counts: Counter[str] = Counter()
    for _, node in message_nodes:
        message = node.get("message") or {}
        role_counts.update([author_role(message)])
        content_type_counts.update([content_type(message)])

    node_ids = current_branch_node_ids(conversation, mapping, request.parser_options.follow_current_node_only)
    messages: list[dict[str, Any]] = []
    asset_refs: list[dict[str, Any]] = []
    for node_id in node_ids:
        node = mapping.get(node_id) or {}
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        role = author_role(message)
        if role == "tool" and not request.parser_options.include_tool_messages:
            continue
        if role == "system" and not request.parser_options.include_system_messages:
            continue

        message_id = str(message.get("id") or node_id)
        refs = (
            extract_asset_refs(message, conversation_id, message_id, export_root)
            if request.parser_options.include_attachments
            else []
        )
        asset_refs.extend(refs)
        main_branch_role_counts.update([role])
        main_branch_content_type_counts.update([content_type(message)])
        messages.append(
            {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "parent_message_id": str(node.get("parent") or ""),
                "created_at": format_timestamp(message.get("create_time") or conversation.get("create_time")),
                "role": role,
                "content_type": content_type(message),
                "model_slug": message_model_slug(message, conversation),
                "text": extract_text(message),
                "asset_refs": refs,
            }
        )

    events = build_events(conversation_id, messages)
    segments = build_segments(conversation_id, events)
    started_at_utc, ended_at_utc = message_time_bounds(messages)
    summary = {
        "conversation_id": conversation_id,
        "title": title,
        "create_time": format_timestamp(conversation.get("create_time")),
        "update_time": format_timestamp(conversation.get("update_time")),
        "started_at_utc": started_at_utc,
        "ended_at_utc": ended_at_utc,
        "default_model_slug": str(conversation.get("default_model_slug") or ""),
        "message_count_total": len(message_nodes),
        "main_branch_message_count": len(messages),
        "branch_count": sum(1 for _, node in mapping.items() if isinstance(node, dict) and len(node.get("children") or []) > 1),
        "attachment_count": sum(1 for ref in asset_refs if ref.get("kind") == "attachment"),
        "image_count": sum(1 for ref in asset_refs if ref.get("kind") == "image"),
        "audio_count": sum(1 for ref in asset_refs if ref.get("kind") == "audio"),
        "tool_count": role_counts.get("tool", 0),
        "event_count": len(events),
        "segment_count": len(segments),
        "has_tool_messages": role_counts.get("tool", 0) > 0,
        "has_system_messages": role_counts.get("system", 0) > 0,
        "has_attachments": len(asset_refs) > 0,
        "has_multimodal_content": any(key != "text" for key in content_type_counts),
        "role_counts_total": dict(role_counts),
        "content_type_counts_total": dict(content_type_counts),
        "main_branch_role_counts": dict(main_branch_role_counts),
        "main_branch_content_type_counts": dict(main_branch_content_type_counts),
        "status": "completed",
        "timeline_path": f"conversations/{conversation_id}/timeline.md",
    }

    timeline_markdown = render_timeline_markdown(summary, events, segments)
    return {
        "summary": summary,
        "messages": messages,
        "events": events,
        "segments": segments,
        "asset_refs": asset_refs,
        "role_counts": dict(role_counts),
        "content_type_counts": dict(content_type_counts),
        "timeline_markdown": timeline_markdown,
    }


def current_branch_node_ids(
    conversation: dict[str, Any],
    mapping: dict[str, Any],
    follow_current_node_only: bool,
) -> list[str]:
    if not follow_current_node_only:
        return [node_id for node_id, node in mapping.items() if isinstance(node, dict) and node.get("message")]

    current = conversation.get("current_node")
    if not current or current not in mapping:
        return [node_id for node_id, node in mapping.items() if isinstance(node, dict) and node.get("message")]

    ordered: list[str] = []
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        ordered.append(str(current))
        node = mapping.get(current) or {}
        current = node.get("parent")
    ordered.reverse()
    return ordered


def author_role(message: dict[str, Any]) -> str:
    author = message.get("author") or {}
    role = str(author.get("role") or "unknown").strip().lower()
    return role or "unknown"


def content_type(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, dict):
        return str(content.get("content_type") or "unknown")
    return "unknown"


def message_model_slug(message: dict[str, Any], conversation: dict[str, Any]) -> str:
    metadata = message.get("metadata") or {}
    for key in ("model_slug", "default_model_slug", "model"):
        value = metadata.get(key)
        if value:
            return str(value)
    return str(conversation.get("default_model_slug") or "")


def extract_text(message: dict[str, Any]) -> str:
    collected: list[str] = []
    content = message.get("content")
    collect_text(content, collected)
    if not collected:
        marker = content_type(message)
        return f"[{marker}]"
    return "\n\n".join(item for item in collected if item).strip() or f"[{content_type(message)}]"


def collect_text(value: Any, collected: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            collected.append(text)
        return
    if isinstance(value, list):
        for item in value:
            collect_text(item, collected)
        return
    if isinstance(value, dict):
        if isinstance(value.get("parts"), list):
            collect_text(value.get("parts"), collected)
        for key in ("text", "caption", "transcript", "result", "output", "content"):
            if key in value:
                collect_text(value.get(key), collected)
