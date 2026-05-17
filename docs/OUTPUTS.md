# Outputs

[Back to README](../README.md)

`POST /items/refresh` rebuilds the configured output root from one ChatGPT export ZIP. The configured output root is treated as generated data and is replaced during refresh. The source ZIP is read-only input; it is not deleted, moved, renamed, or overwritten.

The output root is configured by `settings.json`:

```json
{
  "schemaVersion": 1,
  "runtime": {
    "apiPort": 19300
  },
  "outputRoot": "C:\\TimelineData\\chatgpt"
}
```

The generated layout is:

```text
<outputRoot>\
  manifest.json
  <conversation-id>\
    convert_info.json
    timeline.json
```

All generated JSON files are UTF-8. Timestamps are ISO 8601 UTC strings when the ChatGPT export contains usable time values; otherwise the value may be `null`.

## Data Model

The current output has three layers:

- `manifest.json`: top-level index for the current converted ZIP.
- `<conversation-id>/convert_info.json`: conversion metadata for one conversation.
- `<conversation-id>/timeline.json`: normalized conversation messages for one conversation.

The per-conversation timeline is intentionally smaller than the internal run workspace. Internal files such as raw conversation JSON, events, segments, and LLM pack files are implementation details and are not part of the stable handoff output.

## `manifest.json`

`manifest.json` is the current output index. `items list` reads this file, sorts the items latest-first, and returns paged rows from it.

Example:

```json
{
  "schema_version": 1,
  "application": "TimelineForChatGPT",
  "generated_at": "2026-05-13T19:31:54.314558+00:00",
  "run_id": "run-20260513-192847-chatgpt-export-3a90b3ff",
  "source_export": {
    "source_kind": "upload_zip",
    "source_id": "file",
    "filename": "chatgpt-export.zip",
    "path": "/shared/cache/timeline-for-chatgpt/uploads/.../chatgpt-export.zip",
    "size_bytes": 123456789,
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  },
  "item_count": 1,
  "download_zip_path": "/shared/app-data/runs/run-.../export/TimelineForChatGPT-export-run-....zip",
  "items": [
    {
      "id": "conversation-0001",
      "conversation_id": "conversation-0001",
      "title": "Example conversation",
      "created_at": "2026-05-10T01:02:03+00:00",
      "updated_at": "2026-05-10T01:05:30+00:00",
      "started_at_utc": "2026-05-10T01:02:03+00:00",
      "ended_at_utc": "2026-05-10T01:05:29+00:00",
      "message_count": 4,
      "convert_info_path": "conversation-0001/convert_info.json",
      "timeline_path": "conversation-0001/timeline.json"
    }
  ]
}
```

Field notes:

| Field | Meaning |
| --- | --- |
| `schema_version` | Output contract version. Currently `1`. |
| `application` | Product name. Always `TimelineForChatGPT`. |
| `generated_at` | Time when the current output root was rebuilt. |
| `run_id` | Processing run that produced this output. |
| `source_export` | Metadata for the input ZIP used by this output. |
| `source_export.filename` | Display name of the input ZIP. |
| `source_export.path` | Runtime path of the cached/uploaded ZIP inside the worker environment. This is diagnostic metadata, not a stable consumer path. |
| `source_export.size_bytes` | Input ZIP size in bytes. |
| `source_export.sha256` | SHA-256 hash of the input ZIP when available. |
| `item_count` | Number of conversation folders written to the output root. |
| `download_zip_path` | Worker-side path of the handoff ZIP generated for the run. |
| `items[]` | One row per conversation. |
| `items[].id` | Same value as `conversation_id`; kept as a generic item identifier. |
| `items[].conversation_id` | ChatGPT conversation identifier and folder name. |
| `items[].title` | Final exported conversation title. |
| `items[].created_at` | Conversation creation time from the export. |
| `items[].updated_at` | Conversation update time from the export. |
| `items[].started_at_utc` | First normalized message timestamp in the selected branch. |
| `items[].ended_at_utc` | Last normalized message timestamp in the selected branch. |
| `items[].message_count` | Number of emitted `timeline.json` messages. |
| `items[].convert_info_path` | Relative path to conversion metadata. |
| `items[].timeline_path` | Relative path to normalized conversation messages. |

## `convert_info.json`

`convert_info.json` explains how one conversation was produced and gives counts that are useful for validation.

Example:

```json
{
  "schema_version": 1,
  "application": "TimelineForChatGPT",
  "generated_at": "2026-05-13T19:31:54.314558+00:00",
  "run_id": "run-20260513-192847-chatgpt-export-3a90b3ff",
  "conversation_id": "conversation-0001",
  "title": "Example conversation",
  "source_export": {
    "source_kind": "upload_zip",
    "source_id": "file",
    "filename": "chatgpt-export.zip",
    "path": "/shared/cache/timeline-for-chatgpt/uploads/.../chatgpt-export.zip",
    "size_bytes": 123456789,
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  },
  "counts": {
    "message_count_total": 6,
    "main_branch_message_count": 5,
    "thread_message_count": 4,
    "all_normalized_message_count": 5,
    "attachment_count": 1,
    "image_count": 1,
    "audio_count": 0,
    "tool_count": 1
  },
  "time_bounds": {
    "created_at": "2026-05-10T01:02:03+00:00",
    "updated_at": "2026-05-10T01:05:30+00:00",
    "started_at_utc": "2026-05-10T01:02:03+00:00",
    "ended_at_utc": "2026-05-10T01:05:29+00:00"
  },
  "output_files": {
    "convert_info": "convert_info.json",
    "timeline": "timeline.json"
  }
}
```

Field notes:

| Field | Meaning |
| --- | --- |
| `conversation_id` | Conversation identifier and output folder name. |
| `title` | Final exported title for the conversation. |
| `source_export` | Same source ZIP metadata shape as `manifest.json`. |
| `counts.message_count_total` | Total message nodes found in the original conversation mapping. |
| `counts.main_branch_message_count` | Normalized messages in the selected main branch. |
| `counts.thread_message_count` | Messages emitted to `timeline.json`; roles are `user`, `assistant`, or `system`. |
| `counts.all_normalized_message_count` | Count of normalized main-branch messages before final thread filtering. |
| `counts.attachment_count` | Non-image/non-audio attachment references found. |
| `counts.image_count` | Image references found. |
| `counts.audio_count` | Audio references found. |
| `counts.tool_count` | Tool-role messages found in the export. Tool messages are counted but not emitted as `timeline.json` messages. |
| `time_bounds` | Conversation and normalized message time range. |
| `output_files` | File names written inside this conversation folder. |

## `timeline.json`

`timeline.json` contains the normalized conversation messages. It preserves the selected conversation branch in message order and keeps the text needed for downstream Timeline or LLM workflows.

Example:

```json
{
  "schema_version": 1,
  "application": "TimelineForChatGPT",
  "conversation_id": "conversation-0001",
  "title": "Example conversation",
  "created_at": "2026-05-10T01:02:03+00:00",
  "updated_at": "2026-05-10T01:05:30+00:00",
  "started_at_utc": "2026-05-10T01:02:03+00:00",
  "ended_at_utc": "2026-05-10T01:05:29+00:00",
  "message_count": 2,
  "messages": [
    {
      "message_id": "message-0001",
      "parent_message_id": "",
      "created_at": "2026-05-10T01:02:03+00:00",
      "role": "user",
      "content_type": "text",
      "model_slug": "",
      "text": "Please summarize this document.",
      "attachments": []
    },
    {
      "message_id": "message-0002",
      "parent_message_id": "message-0001",
      "created_at": "2026-05-10T01:05:29+00:00",
      "role": "assistant",
      "content_type": "text",
      "model_slug": "gpt-4o",
      "text": "Here is the summary...",
      "attachments": [
        {
          "kind": "image",
          "attachment_id": "file-abc123",
          "logical_path": "files/example.png",
          "conversation_id": "conversation-0001",
          "message_id": "message-0002",
          "relative_path": "files/example.png",
          "file_exists": true,
          "size_bytes": 2048,
          "mtime_utc": "2026-05-10T01:05:20+00:00",
          "hash_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        }
      ]
    }
  ]
}
```

Message field notes:

| Field | Meaning |
| --- | --- |
| `message_id` | ChatGPT message ID, or a normalized fallback when unavailable. |
| `parent_message_id` | Parent node/message ID from the conversation mapping. |
| `created_at` | Message creation time. |
| `role` | Normalized author role. Emitted roles are `user`, `assistant`, or `system`. |
| `content_type` | ChatGPT content type, for example `text`, `multimodal_text`, `execution_output`, or `unknown`. |
| `model_slug` | Model metadata from the message or conversation when available. |
| `text` | Extracted human-readable text from supported content fields such as `parts`, `text`, `caption`, `transcript`, `result`, `output`, or `content`. |
| `attachments` | Attachment evidence references extracted from message content. Binary files are not copied into the output root. |

Attachment field notes:

| Field | Meaning |
| --- | --- |
| `kind` | `image`, `audio`, or `attachment`, inferred from the logical path extension. |
| `attachment_id` | Attachment identifier from the ChatGPT export when available. |
| `logical_path` | Path value found in the ChatGPT message payload. |
| `relative_path` | Sanitized relative path used for evidence lookup. |
| `file_exists` | Whether the referenced file existed in the extracted export during processing. |
| `size_bytes` | Referenced file size when available. |
| `mtime_utc` | Referenced file modified time when available. |
| `hash_sha256` | Referenced file SHA-256 when available. |

## Handoff ZIP

`items download --to` creates a handoff ZIP from the current output root. The ZIP contains:

```text
README.md
items/<conversation-id>/convert_info.json
items/<conversation-id>/timeline.json
```

The handoff ZIP does not include:

- the source ChatGPT export ZIP
- binary attachment files
- internal run workspace files
- `manifest.json`

The handoff ZIP is intended for downstream tools that need conversation-level JSON without requiring access to the original ChatGPT export.

## Processing Summary

The worker extracts the ChatGPT export ZIP, locates `conversations.json` or `conversations-*.json`, follows the selected conversation branch, and writes normalized conversation items to the current output root.

ZIP-level failures stop the refresh. A failure during conversation normalization fails the run and leaves the source ZIP unchanged.
