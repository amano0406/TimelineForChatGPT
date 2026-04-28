# App Spec

## Goal

`TimelineForChatGPT` converts a local ChatGPT export into timeline-oriented text that can be reviewed by a human or handed to an LLM.

The system prioritizes:

- fixed input directories for normal refresh operation
- readable run output
- local processing
- a product shape close to `video2timeline`

## App Model

- `worker`: Python CLI and worker pipeline
- coordination: filesystem run directories

## User Flow

1. keep input directories and output/state roots in config
2. run `refresh`
3. the CLI scans configured input directories
4. unchanged inputs are skipped from processing
5. changed inputs create run directories
6. the worker writes status, result, index, timeline, and attachment inventory files
7. inspect the refresh report or generated run directories
8. use the final ZIP handoff package when another LLM or review workflow needs the output

The direct `process` command remains available for one-off ZIP or extracted export directory processing.

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

Every refresh writes:

- `refresh-<timestamp>.json` in the configured output root
- `refresh-latest.md` in the configured output root
- `refresh_state.json` in the configured state root

## Current contract gaps

The shared Timeline baseline includes `input_snapshot.json` and `fidelity_report.json`.
This scaffold does not emit those files yet.
Current equivalents are partial:

- input identity is recorded in `request.json`
- input summary is recorded in `export_summary.json`
- parser limitations are documented in `NOTICE.md`, README limitations, and timeline metadata

Future contract work should add explicit `input_snapshot.json` and `fidelity_report.json` without removing the current files.

## Current scaffold scope

- configured input directories for normal refresh operation
- one ZIP or extracted export directory per direct CLI job
- unchanged input skipping based on file fingerprint state
- local config example for fixed input/output/state roots
- config validation for missing input roots and unsafe recursive output/state placement
- current-branch-first normalization
- best-effort text extraction
- best-effort timeline rendering
- the worker rejects obviously corrupted ZIP files before pretending the export is usable
