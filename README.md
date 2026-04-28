# TimelineForChatGPT

Local-first CLI tool that turns ChatGPT export ZIP files into timeline-oriented artifacts.

The product no longer includes a web UI. The Python CLI / worker and generated output files are the source of truth.

## Current Scope

- `worker`: Python CLI and worker pipeline
- `docker-compose.yml`: worker-only development/runtime service
- input:
  - one ChatGPT export ZIP
  - one extracted ChatGPT export directory
- output:
  - `request.json`
  - `status.json`
  - `result.json`
  - `manifest.json`
  - `export_summary.json`
  - `conversation_index.jsonl`
  - `conversations/<id>/timeline.md`
  - `conversations/<id>/events.jsonl`
  - `conversations/<id>/segments.json`
  - `conversations/<id>/messages.jsonl`
  - `conversations/<id>/attachments.json`
  - `llm/conversation_index.jsonl`
  - `llm/conversation_corpus-YYYY-MM.jsonl`
  - `job-....zip`

## CLI Usage

Run from source:

```bash
cd /mnt/c/apps/TimelineForChatGPT
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker process /path/to/chatgpt-export.zip --output-root /tmp/timelineforchatgpt-outputs
```

The command prints the run directory. The original export file is read in place; it is not deleted, overwritten, moved, or renamed.

Process existing queued jobs:

```bash
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker run-once
```

Run the polling worker:

```bash
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker daemon
```

## Docker

Build the worker image:

```bash
docker compose build
```

Run the worker daemon:

```bash
docker compose up
```

There is no browser URL or exposed port. The compose file only runs the worker container and shared local volumes.

## Validation

Worker unit tests:

```bash
PYTHONPATH=/mnt/c/apps/TimelineForChatGPT/worker/src python3 -m unittest discover -s /mnt/c/apps/TimelineForChatGPT/worker/tests -v
```

## Current Limitations

- primary input is one ChatGPT export ZIP or one extracted export directory per CLI job
- timeline rendering is still a best-effort scaffold parser
- normalized events and segments are still evolving toward the shared timeline contract
- older ChatGPT export downloads can be corrupted; the worker rejects ZIP files that cannot be opened cleanly

## Relationship To TimelineForVideo

This repo is intentionally close to `TimelineForVideo`, but it is not a fork of the video worker.

- shared direction:
  - run directory contract
  - timeline-oriented outputs
  - local-first Docker Compose shape
- source-specific direction:
  - `TimelineForVideo` parses media
  - `TimelineForChatGPT` parses ChatGPT export graphs

Reference docs:

- [docs/COMMON_OUTPUT_CONTRACT.md](docs/COMMON_OUTPUT_CONTRACT.md)
- [docs/NORMALIZED_EVENT_ALIGNMENT.md](docs/NORMALIZED_EVENT_ALIGNMENT.md)

## Sample Validation Note

The local Downloads folder already contained both valid and invalid ChatGPT export ZIP files.

- valid sample:
  - `9885dfc7ffd231544e4fe7922328af9e8b5a7a460a97254226bfea15a748bd2f-2026-03-08-16-36-29-e0ba4a3a358d4d50bbb6b8c0dcacace2.zip`
- invalid samples:
  - `9885dfc7ffd231544e4fe7922328af9e8b5a7a460a97254226bfea15a748bd2f-2026-04-01-09-27-26-8fdebf5afe87415fb7acc1ba11d6e3d1.zip`
  - `-09-27-26-8fdebf5afe87415fb7acc1ba11d6e3d1 (1).zip`
  - `aaa.zip`
  - `first.zip`
  - `second.zip`

Those invalid files still start with a ZIP local header, but they miss the end-of-central-directory record and fail with `BadZipFile`.

## Repo Layout

```text
configs/
docker/
docs/
worker/
```
