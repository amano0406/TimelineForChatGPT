# Common Output Contract

## Purpose

`TimelineForChatGPT` is intentionally shaped to stay close to `video2timeline`.

The immediate goal is not a single shared repo.
The immediate goal is a shared contract so that:

- CLI and worker output flows stay predictable
- downstream readers can inspect runs in a similar way
- ZIP handoff packages stay predictable
- future common viewers or indexers can read both tools with minimal branching

## Design Rule

Shared output contract comes before shared implementation.

That means:

- `video2timeline` remains the video-focused tool
- `TimelineForChatGPT` remains the ChatGPT export-focused tool
- both tools should converge on run layout, status semantics, and deliverable naming where practical

## Shared Run Shape

Both tools should keep the same top-level run model:

- one job creates one run directory
- the CLI writes `request.json`
- the worker owns `status.json`, `result.json`, and `manifest.json`
- the worker also writes human-readable deliverables and a final ZIP
- refresh-style tools may add a timestamped refresh report above individual run directories

Current naming differs slightly:

- `video2timeline` uses `run-*`
- `TimelineForChatGPT` currently uses `job-*`

That difference is acceptable for now.
The important part is the internal file contract.

## Shared Core Files

These files are the common inspection surface.

### `request.json`

Common fields:

- `schema_version`
- `job_id`
- `created_at`
- `output_root_id`
- `output_root_path`
- `profile`
- `reprocess_duplicates`
- `input_items[]`

Source-specific extension fields:

- `video2timeline`
  - `compute_mode`
  - `processing_quality`
  - `token_enabled`
- `TimelineForChatGPT`
  - `parser_options`

Rule:

- common readers may rely on the common fields
- source-specific workers may add extra request knobs without breaking the shared shape

### `status.json`

Common fields:

- `schema_version`
- `job_id`
- `state`
- `current_stage`
- `message`
- `warnings`
- `progress_percent`
- `started_at`
- `updated_at`
- `completed_at`

Source-specific progress counters:

- `video2timeline`
  - `videos_total`
  - `videos_done`
  - `videos_skipped`
  - `videos_failed`
  - `current_media`
- `TimelineForChatGPT`
  - `conversations_total`
  - `conversations_done`
  - `conversations_skipped`
  - `conversations_failed`
  - `current_conversation`

Rule:

- shared viewers should always render `state`, `current_stage`, `message`, and `progress_percent`
- source-specific counters are additive detail

### `result.json`

Common fields:

- `schema_version`
- `job_id`
- `state`
- `run_dir`
- `output_root_id`
- `output_root_path`
- `processed_count`
- `skipped_count`
- `error_count`
- `batch_count`
- `warnings`

Current tool-specific index pointers:

- `video2timeline`
  - `timeline_index_path`
- `TimelineForChatGPT`
  - `conversation_index_path`
  - `archive_path`

Rule:

- the result file should answer "did the run finish, where is it, and what is the main index output?"

### `manifest.json`

`manifest.json` is the per-item catalog inside the run.

Item granularity differs:

- `video2timeline`: one item per media input
- `TimelineForChatGPT`: one item per conversation

Even with different granularity, the role is the same:

- what was processed
- what its status is
- where the main timeline artifact lives
- what summary counters are attached to the item

## Shared Deliverable Concepts

These deliverables should stay conceptually aligned even if field names differ.

### Human-readable timeline

- `video2timeline`: media-centered `timeline.md`
- `TimelineForChatGPT`: conversation-centered `timeline.md`

Both should optimize for:

- readable chronological review
- compact structure
- easy copy/paste into an LLM

### Structured event output

- `video2timeline`: transcript and screen-derived records
- `TimelineForChatGPT`: branch-aware message-derived records

Current file names:

- `events.jsonl`
- `segments.json`

These names should stay stable across tools.

### Index output

- `video2timeline`: `llm/timeline_index.jsonl`
- `TimelineForChatGPT`: `conversation_index.jsonl` and `llm/conversation_index.jsonl`

The exact file name can vary by domain.
The stable idea is:

- one row per top-level timeline unit
- enough metadata to list, filter, and batch downstream

### ZIP package

Both tools should produce one ZIP per completed run.

Minimum expectation:

- include the main index
- include human-readable timelines
- include machine-readable structured outputs
- include `status.json`, `result.json`, and `manifest.json`

### Refresh report

`TimelineForChatGPT` also supports directory refresh mode.
That mode writes `refresh-<timestamp>.json` into the configured output root.
It also writes `refresh-latest.md` for quick human review of the latest run.

The report records:

- configured roots used for the run
- discovered inputs
- processed items
- unchanged skipped items
- failed items
- the run directory or previous run directory for each input

## Stage Naming Guidance

Stage names do not need to be identical, but they should remain legible.

Current examples:

- `video2timeline`
  - `preflight`
  - `audio`
  - `transcription`
  - `screen_extraction`
  - `timeline_render`
- `TimelineForChatGPT`
  - `extract_zip`
  - `parse_conversations`
  - `build_indexes`
  - `completed`

Rule:

- stage names should be domain-meaningful
- they should not be internal method names unless that method already matches product language

## Shared Viewer Assumption

A future generic viewer should be able to open either tool's run directory and read:

- `request.json`
- `status.json`
- `result.json`
- `manifest.json`
- one domain-specific index file

without caring how the underlying parser worked.

## Current Boundary

What is shared now:

- run contract shape
- job flow
- output naming philosophy
- timeline-oriented deliverables

What is not shared now:

- worker implementation
- normalization logic
- item schema
- parser options

That split is intentional.
