from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
