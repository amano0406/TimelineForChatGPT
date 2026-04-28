# TimelineForChatGPT

Local-first CLI tool that turns ChatGPT export ZIP files into timeline-oriented artifacts.

The product no longer includes a web UI. The Python CLI / worker and generated output files are the source of truth.

## Current Scope

- `worker`: Python CLI and worker pipeline
- `docker-compose.yml`: worker-only development/runtime service
- input:
  - configured input directories containing ChatGPT export ZIP files
  - one ChatGPT export ZIP through the direct `process` command
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

Refresh configured input directories:

```bash
cd /mnt/c/apps/TimelineForChatGPT
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker refresh
```

`refresh` scans the configured input roots, processes changed ZIP files, and skips unchanged inputs. Each refresh writes a timestamped `refresh-....json` report into the output root.

Create a local config for daily use:

```bash
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker settings init
```

This creates `settings.json` from `settings.example.json` when `settings.json` does not exist. Edit `settings.json` so `inputRoots`, `outputRoot`, and `stateRoot` point to your local folders. `settings.json` is ignored by Git.

After refresh, open:

- `index.md`: human-readable catalog of known inputs and latest successful outputs
- `index.json`: machine-readable catalog of known inputs and latest successful outputs
- `refresh-latest.md`: human-readable latest refresh result
- `refresh-....json`: timestamped machine-readable refresh result
- `stateRoot/refresh_state.json`: refresh state used to skip unchanged inputs

Check what would run without processing:

```bash
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker refresh --dry-run
```

Check the config without processing:

```bash
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker config-check
```

Force reprocessing:

```bash
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker refresh --force
```

Run one file directly:

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

- primary refresh input is configured directories containing ChatGPT export ZIP files
- direct processing still supports one ChatGPT export ZIP or one extracted export directory per CLI job
- refresh requires at least one enabled input directory that exists
- recursive refresh rejects output/state folders inside input folders to avoid processing its own outputs
- refresh uses `stateRoot/refresh.lock` to avoid overlapping refresh runs
- refresh reports inputs that disappeared since the last run as `missing_from_input`
- refresh skips duplicate ZIP contents in the same run as `duplicate_skipped`
- refresh reports include minimal timing for discovery, fingerprinting, processing, and total duration
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
