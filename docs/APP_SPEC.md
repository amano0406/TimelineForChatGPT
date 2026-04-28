# App Spec

## Goal

`TimelineForChatGPT` converts a local ChatGPT export into timeline-oriented text that can be reviewed by a human or handed to an LLM.

The system prioritizes:

- simple ZIP-first input
- readable run output
- local processing
- a product shape close to `video2timeline`

## App Model

- `worker`: Python CLI and worker pipeline
- coordination: filesystem run directories

## User Flow

1. run the CLI with one ChatGPT export ZIP or extracted export directory
2. the CLI creates a run directory
3. the worker writes status, result, index, timeline, and attachment inventory files
4. inspect the generated run directory
5. use the final ZIP handoff package when another LLM or review workflow needs the output

## Output Model

Every run writes:

- `request.json`
- `status.json`
- `result.json`
- `manifest.json`
- `RUN_INFO.md`
- `NOTICE.md`
- `export_summary.json`
- `conversation_index.jsonl`

Each conversation currently writes:

- `conversation.json`
- `messages.jsonl`
- `events.jsonl`
- `segments.json`
- `timeline.md`
- `attachments.json`

`attachments.json` is an inventory of attachment references observed in the normalized main branch.
Each item keeps the original `attachment_id` / `logical_path` when present and adds:

- `conversation_id`
- `message_id`
- `relative_path`
- `file_exists`
- `size_bytes`
- `mtime_utc`
- `hash_sha256`

LLM export writes:

- `llm/conversation_index.jsonl`
- `llm/conversation_corpus-YYYY-MM.jsonl`

## Current contract gaps

The shared Timeline baseline includes `input_snapshot.json` and `fidelity_report.json`.
This scaffold does not emit those files yet.
Current equivalents are partial:

- input identity is recorded in `request.json`
- input summary is recorded in `export_summary.json`
- parser limitations are documented in `NOTICE.md`, README limitations, and timeline metadata

Future contract work should add explicit `input_snapshot.json` and `fidelity_report.json` without removing the current files.

## Current scaffold scope

- one ZIP or extracted export directory per CLI job
- current-branch-first normalization
- best-effort text extraction
- best-effort timeline rendering
- the worker rejects obviously corrupted ZIP files before pretending the export is usable
