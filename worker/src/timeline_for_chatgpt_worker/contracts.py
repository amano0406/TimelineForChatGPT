from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class InputItem:
    input_id: str
    source_kind: str
    source_id: str
    original_path: str
    display_name: str
    size_bytes: int = 0
    uploaded_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParserOptions:
    follow_current_node_only: bool = True
    include_tool_messages: bool = True
    include_system_messages: bool = True
    include_attachments: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "ParserOptions":
        payload = payload or {}
        return cls(
            follow_current_node_only=bool(payload.get("follow_current_node_only", True)),
            include_tool_messages=bool(payload.get("include_tool_messages", True)),
            include_system_messages=bool(payload.get("include_system_messages", True)),
            include_attachments=bool(payload.get("include_attachments", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunRequest:
    schema_version: int
    run_id: str
    created_at: str
    output_root_id: str
    output_root_path: str
    profile: str
    reprocess_duplicates: bool
    parser_options: ParserOptions
    input_items: list[InputItem]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRequest":
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            run_id=str(payload["run_id"]),
            created_at=str(payload["created_at"]),
            output_root_id=str(payload["output_root_id"]),
            output_root_path=str(payload["output_root_path"]),
            profile=str(payload.get("profile") or "timeline-default"),
            reprocess_duplicates=bool(payload.get("reprocess_duplicates", False)),
            parser_options=ParserOptions.from_dict(payload.get("parser_options")),
            input_items=[InputItem(**item) for item in payload.get("input_items", [])],
        )


@dataclass
class RunStatus:
    schema_version: int = 1
    run_id: str = ""
    state: str = "pending"
    current_stage: str = "queued"
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    conversations_total: int = 0
    conversations_done: int = 0
    conversations_skipped: int = 0
    conversations_failed: int = 0
    current_conversation: str | None = None
    estimated_remaining_sec: float | None = None
    progress_percent: float = 0.0
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunResult:
    schema_version: int = 1
    run_id: str = ""
    state: str = "pending"
    run_dir: str = ""
    output_root_id: str = ""
    output_root_path: str = ""
    processed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    batch_count: int = 0
    conversation_index_path: str | None = None
    archive_path: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
