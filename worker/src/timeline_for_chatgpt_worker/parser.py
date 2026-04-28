from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .contracts import JobRequest
from .fs_utils import ensure_dir, load_json, slugify, write_json, write_jsonl


def prepare_export_root(run_dir: Path, request: JobRequest) -> tuple[Path, str, Path | None]:
    input_item = request.input_items[0]
    uploaded_path = Path(input_item.uploaded_path or "")
    if input_item.source_kind == "upload_zip":
        extraction_root = build_short_extraction_root(uploaded_path, request.job_id)
        if extraction_root.exists():
            shutil.rmtree(extraction_root, ignore_errors=True)
        ensure_dir(extraction_root)
        try:
            with zipfile.ZipFile(uploaded_path) as archive:
                archive.extractall(extraction_root)
        except zipfile.BadZipFile as exc:
            raise ValueError(
                "The ChatGPT export ZIP is corrupted or incomplete. "
                "Older downloads in Downloads may be truncated and miss the central directory."
            ) from exc
        export_root = resolve_export_root(extraction_root)
        if not has_export_signature(export_root):
            raise ValueError("The extracted ZIP does not look like a ChatGPT export.")
        return export_root, input_item.display_name, extraction_root

    source_path = Path(input_item.uploaded_path or input_item.original_path)
    if source_path.is_dir():
        if not has_export_signature(source_path):
            raise ValueError("The selected directory does not look like a ChatGPT export.")
        return source_path, input_item.display_name, None

    raise ValueError(f"Unsupported input kind: {input_item.source_kind}")


def build_short_extraction_root(uploaded_path: Path, job_id: str) -> Path:
    job_token = job_id.rsplit("-", 1)[-1] or "job"
    anchor = uploaded_path.anchor.rstrip("\\/")
    if anchor.endswith(":"):
        return Path(f"{anchor}\\") / "t" / job_token

    temp_root = Path(tempfile.gettempdir())
    temp_anchor = temp_root.anchor.rstrip("\\/")
    if temp_anchor.endswith(":"):
        return Path(f"{temp_anchor}\\") / "t" / job_token

    return temp_root / "t" / job_token


def resolve_export_root(root: Path) -> Path:
    if has_export_signature(root):
        return root

    children = [child for child in root.iterdir() if child.is_dir()]
    if len(children) == 1 and has_export_signature(children[0]):
        return children[0]

    return root


def has_export_signature(path: Path) -> bool:
    if (path / "export_manifest.json").exists():
        return True
    return any(candidate.name.startswith("conversations") and candidate.suffix == ".json" for candidate in path.glob("*.json"))


def discover_conversation_files(export_root: Path) -> list[Path]:
    rows: list[Path] = []
    for candidate in sorted(export_root.glob("*.json")):
        name = candidate.name.lower()
        if name == "conversations.json" or (
            name.startswith("conversations-") and name.endswith(".json")
        ):
            rows.append(candidate)
    return rows


def load_conversations(export_root: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    files = discover_conversation_files(export_root)
    for path in files:
        payload = load_json(path)
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
    return rows, len(files)


def normalize_export(
    run_dir: Path,
    request: JobRequest,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
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
        export_summary = {
            "job_id": request.job_id,
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

        batch_count = build_llm_pack(llm_root, conversation_rows, conversations_root)
        archive_path = run_dir / f"{request.job_id}.zip"

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


def try_load_analysis_summary(export_root: Path) -> dict[str, Any]:
    path = export_root / "analysis_summary.json"
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def normalize_conversation(
    conversation: dict[str, Any],
    request: JobRequest,
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


def extract_asset_refs(
    message: dict[str, Any],
    conversation_id: str = "",
    message_id: str = "",
    export_root: Path | None = None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    collect_asset_refs(message, refs)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        enriched = enrich_asset_ref(ref, conversation_id, message_id, export_root)
        key = json.dumps(enriched, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(enriched)
    return unique


def collect_asset_refs(value: Any, refs: list[dict[str, Any]]) -> None:
    if isinstance(value, list):
        for item in value:
            collect_asset_refs(item, refs)
        return
    if not isinstance(value, dict):
        return

    if "attachment_id" in value or "logical_path" in value:
        refs.append(
            {
                "kind": asset_kind(value),
                "attachment_id": str(value.get("attachment_id") or ""),
                "logical_path": str(value.get("logical_path") or ""),
            }
        )

    for nested in value.values():
        collect_asset_refs(nested, refs)


def asset_kind(payload: dict[str, Any]) -> str:
    logical_path = str(payload.get("logical_path") or "").lower()
    if any(logical_path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return "image"
    if any(logical_path.endswith(ext) for ext in (".wav", ".mp3", ".m4a", ".ogg")):
        return "audio"
    return "attachment"


def enrich_asset_ref(
    ref: dict[str, Any],
    conversation_id: str,
    message_id: str,
    export_root: Path | None,
) -> dict[str, Any]:
    logical_path = str(ref.get("logical_path") or "")
    relative_path = normalize_relative_path(logical_path)
    evidence_path = resolve_evidence_path(export_root, relative_path)
    evidence = file_evidence(evidence_path) if evidence_path is not None else {}
    return {
        **ref,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "relative_path": relative_path,
        "file_exists": evidence_path is not None,
        "size_bytes": evidence.get("size_bytes"),
        "mtime_utc": evidence.get("mtime_utc"),
        "hash_sha256": evidence.get("hash_sha256"),
    }


def normalize_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return ""
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        return ""
    return path.as_posix()


def resolve_evidence_path(export_root: Path | None, relative_path: str) -> Path | None:
    if export_root is None or not relative_path:
        return None
    candidate = (export_root / relative_path).resolve()
    try:
        candidate.relative_to(export_root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def file_evidence(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "hash_sha256": hash_file_sha256(path),
    }


def hash_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_events(conversation_id: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for sequence, message in enumerate(messages, start=1):
        event_id = str(message.get("message_id") or f"event-{sequence:04d}")
        artifacts = list(message.get("asset_refs") or [])
        events.append(
            {
                "source_type": "chatgpt_export",
                "source_unit_id": conversation_id,
                "event_id": event_id,
                "sequence": sequence,
                "start_at_utc": message.get("created_at"),
                "end_at_utc": message.get("created_at"),
                "actor": message.get("role") or "unknown",
                "kind": infer_event_kind(message),
                "text": message.get("text") or "",
                "artifacts": artifacts,
                "payload": {
                    "message_id": message.get("message_id"),
                    "parent_message_id": message.get("parent_message_id"),
                    "content_type": message.get("content_type"),
                    "model_slug": message.get("model_slug"),
                    "asset_count": len(artifacts),
                },
            }
        )
    return events


def infer_event_kind(message: dict[str, Any]) -> str:
    role = str(message.get("role") or "unknown")
    if role == "tool":
        return "tool_result"
    return "message"


def build_segments(conversation_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return []

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for event in events:
        if not current or not should_start_new_segment(current, event):
            current.append(event)
            continue
        groups.append(current)
        current = [event]

    if current:
        groups.append(current)

    segments: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        actor_counts = Counter(str(event.get("actor") or "unknown") for event in group)
        kind_counts = Counter(str(event.get("kind") or "unknown") for event in group)
        artifact_count = sum(len(event.get("artifacts") or []) for event in group)
        segments.append(
            {
                "segment_id": f"segment-{index:04d}",
                "source_type": "chatgpt_export",
                "source_unit_id": conversation_id,
                "sequence": index,
                "start_at_utc": group[0].get("start_at_utc"),
                "end_at_utc": group[-1].get("end_at_utc"),
                "title": build_segment_title(group, index),
                "summary": build_segment_summary(group, actor_counts, artifact_count),
                "event_ids": [str(event["event_id"]) for event in group],
                "actor_counts": dict(actor_counts),
                "kind_counts": dict(kind_counts),
                "payload": {
                    "event_count": len(group),
                    "artifact_count": artifact_count,
                },
            }
        )

    return segments


def should_start_new_segment(current_segment: list[dict[str, Any]], next_event: dict[str, Any]) -> bool:
    previous = current_segment[-1]
    if event_gap_seconds(previous, next_event) > 900:
        return True
    return str(next_event.get("actor") or "unknown") == "user"


def event_gap_seconds(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_time = parse_datetime(left.get("end_at_utc") or left.get("start_at_utc"))
    right_time = parse_datetime(right.get("start_at_utc") or right.get("end_at_utc"))
    if left_time is None or right_time is None:
        return 0.0
    return max(0.0, (right_time - left_time).total_seconds())


def build_segment_title(events: list[dict[str, Any]], index: int) -> str:
    preferred = next((event for event in events if event.get("actor") == "user"), events[0])
    preview = summarize_text(preferred.get("text"), 72)
    if preview:
        return preview
    actor = str(preferred.get("actor") or "unknown")
    return f"{actor} segment {index}"


def build_segment_summary(
    events: list[dict[str, Any]],
    actor_counts: Counter[str],
    artifact_count: int,
) -> str:
    actor_flow = " -> ".join(unique_actor_flow(events))
    parts = [
        f"{len(events)} event{'s' if len(events) != 1 else ''}",
        actor_flow if actor_flow else "unknown flow",
    ]
    if artifact_count:
        parts.append(f"{artifact_count} asset{'s' if artifact_count != 1 else ''}")
    return ", ".join(parts)


def unique_actor_flow(events: list[dict[str, Any]]) -> list[str]:
    flow: list[str] = []
    for event in events:
        actor = str(event.get("actor") or "unknown")
        if not flow or flow[-1] != actor:
            flow.append(actor)
    return flow


def summarize_text(value: Any, limit: int) -> str:
    text = reflow_text(value)
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def reflow_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return " ".join(text.split())


def render_timeline_markdown(
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> str:
    event_lookup = {str(event["event_id"]): event for event in events}
    flags: list[str] = []
    if summary.get("has_tool_messages"):
        flags.append("tool")
    if summary.get("has_system_messages"):
        flags.append("system")
    if summary.get("has_attachments"):
        flags.append("attachments")
    if summary.get("has_multimodal_content"):
        flags.append("multimodal")

    lines = [
        "# Conversation Timeline",
        "",
        "## Metadata",
        f"- Conversation ID: `{summary['conversation_id']}`",
        f"- Title: `{summary['title']}`",
        f"- Created: `{summary.get('create_time') or '-'}`",
        f"- Updated: `{summary.get('update_time') or '-'}`",
        f"- Started (main branch): `{summary.get('started_at_utc') or '-'}`",
        f"- Ended (main branch): `{summary.get('ended_at_utc') or '-'}`",
        f"- Default model: `{summary.get('default_model_slug') or '-'}`",
        f"- Messages: `{summary.get('main_branch_message_count', 0)}` main branch / `{summary.get('message_count_total', 0)}` total",
        f"- Events: `{summary.get('event_count', len(events))}`",
        f"- Segments: `{summary.get('segment_count', len(segments))}`",
        f"- Branches: `{summary.get('branch_count', 0)}`",
        f"- Assets: `{summary.get('attachment_count', 0)}` attachments / `{summary.get('image_count', 0)}` images / `{summary.get('audio_count', 0)}` audio",
        f"- Tool messages: `{summary.get('tool_count', 0)}`",
        f"- Flags: `{', '.join(flags) if flags else 'none'}`",
        f"- Main branch roles: `{format_counter(summary.get('main_branch_role_counts'))}`",
        f"- Main branch content types: `{format_counter(summary.get('main_branch_content_type_counts'))}`",
        "",
    ]
    for segment in segments:
        lines.append(f"## {format_segment_window(segment)}")
        lines.append(f"Segment: {segment.get('title') or '-'}")
        lines.append(f"Summary: {segment.get('summary') or '-'}")
        lines.append("")
        for event_id in segment.get("event_ids", []):
            event = event_lookup.get(str(event_id))
            if event is None:
                continue
            lines.append(
                f"### {event.get('actor') or 'unknown'}"
                f" ({event.get('kind') or 'event'})"
            )
            payload = event.get("payload") or {}
            if payload.get("model_slug"):
                lines.append(f"Model: `{payload['model_slug']}`")
            if payload.get("content_type"):
                lines.append(f"Content type: `{payload['content_type']}`")
            lines.append(f"Timestamp: `{event.get('start_at_utc') or '-'}`")
            lines.append("")
            lines.append(event.get("text") or "")
            if event.get("artifacts"):
                lines.append("")
                lines.append("Assets:")
                for ref in event["artifacts"]:
                    label = ref.get("logical_path") or ref.get("attachment_id") or "(unknown)"
                    lines.append(f"- {ref.get('kind', 'attachment')}: `{label}`")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def format_segment_window(segment: dict[str, Any]) -> str:
    start = str(segment.get("start_at_utc") or "-")
    end = str(segment.get("end_at_utc") or "")
    if not end or end == start:
        return start
    return f"{start} - {end}"


def build_llm_pack(llm_root: Path, conversation_rows: list[dict[str, Any]], conversations_root: Path) -> int:
    write_jsonl(llm_root / "conversation_index.jsonl", conversation_rows)
    shards: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in conversation_rows:
        month_key = month_bucket(row.get("create_time") or row.get("update_time"))
        timeline_path = conversations_root / row["conversation_id"] / "timeline.md"
        content_markdown = timeline_path.read_text(encoding="utf-8", errors="replace") if timeline_path.exists() else ""
        shards[month_key].append(
            {
                "conversation_id": row["conversation_id"],
                "title": row["title"],
                "create_time": row.get("create_time"),
                "update_time": row.get("update_time"),
                "content_markdown": content_markdown,
            }
        )

    batch_count = 0
    for month_key, items in sorted(shards.items()):
        batch_count += 1
        write_jsonl(llm_root / f"conversation_corpus-{month_key}.jsonl", items)

    (llm_root / "README.md").write_text(
        "\n".join(
            [
                "# LLM Pack",
                "",
                "- `conversation_index.jsonl`: conversation summary rows",
                "- `conversation_corpus-YYYY-MM.jsonl`: monthly conversation markdown shards",
                "",
                "Send the monthly shards first when handing off to an LLM.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return batch_count


def build_archive(run_dir: Path, job_id: str, conversation_rows: list[dict[str, Any]], llm_root: Path) -> Path:
    archive_path = run_dir / f"{job_id}.zip"
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.md",
            "\n".join(
                [
                    "# TimelineForChatGPT Export",
                    "",
                    f"- Job ID: `{job_id}`",
                    "- Main folder: `timelines/`",
                    "- `conversation_index.jsonl` provides the summary catalog.",
                    "",
                ]
            ),
        )
        conversation_index_path = run_dir / "conversation_index.jsonl"
        if conversation_index_path.exists():
            archive.write(conversation_index_path, "conversation_index.jsonl")
        for metadata_name in ("export_summary.json", "manifest.json", "result.json", "status.json"):
            metadata_path = run_dir / metadata_name
            if metadata_path.exists():
                archive.write(metadata_path, metadata_name)
        used_names: set[str] = set()
        for row in conversation_rows:
            timeline_path = run_dir / row["timeline_path"]
            conversation_root = run_dir / "conversations" / row["conversation_id"]
            if conversation_root.exists():
                for candidate in sorted(conversation_root.rglob("*")):
                    if candidate.is_file():
                        archive.write(
                            candidate,
                            "conversations/"
                            f"{row['conversation_id']}/{candidate.relative_to(conversation_root).as_posix()}",
                        )
            if timeline_path.exists():
                file_name = unique_timeline_export_name(row, used_names)
                archive.write(timeline_path, f"timelines/{file_name}")
        if llm_root.exists():
            for candidate in llm_root.rglob("*"):
                if candidate.is_file():
                    archive.write(candidate, f"llm/{candidate.relative_to(llm_root).as_posix()}")
    return archive_path


def unique_timeline_export_name(row: dict[str, Any], used_names: set[str]) -> str:
    conversation_id = str(row.get("conversation_id") or "conversation")
    title_slug = slugify(str(row.get("title") or conversation_id))
    candidate = f"{title_slug}-{conversation_id[:8]}.md"
    suffix = 2
    while candidate.lower() in used_names:
        candidate = f"{title_slug}-{conversation_id[:8]}-{suffix}.md"
        suffix += 1
    used_names.add(candidate.lower())
    return candidate


def message_time_bounds(messages: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    timestamps = [str(value) for value in (message.get("created_at") for message in messages) if value]
    if not timestamps:
        return None, None
    return min(timestamps), max(timestamps)


def format_counter(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "-"
    pairs = [f"{key}:{value}" for key, value in sorted(payload.items()) if value]
    return ", ".join(pairs) if pairs else "-"


def month_bucket(value: str | None) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "unknown"
    return parsed.strftime("%Y-%m")


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def format_timestamp(value: Any) -> str | None:
    parsed = parse_datetime(value)
    return parsed.astimezone(timezone.utc).isoformat() if parsed else None


def min_utc(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return left if left <= right else right


def max_utc(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return left if left >= right else right
