from __future__ import annotations

import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from .conversation_parts import month_bucket
from .fs_utils import slugify, write_jsonl


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


def build_archive(run_dir: Path, run_id: str, conversation_rows: list[dict[str, Any]], llm_root: Path) -> Path:
    archive_path = run_dir / f"{run_id}.zip"
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.md",
            "\n".join(
                [
                    "# TimelineForChatGPT Export",
                    "",
                    f"- Run ID: `{run_id}`",
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
