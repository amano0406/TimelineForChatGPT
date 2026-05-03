# App Spec

## Goal

`TimelineForChatGPT` converts a local ChatGPT export into timeline-oriented text that can be reviewed by a human or handed to an LLM.

The system prioritizes:

- explicit ChatGPT export ZIP input at refresh time
- readable per-conversation output
- local Docker-only processing
- a product shape close to the Timeline family CLI workflow

## App Model

- `worker`: Docker CLI and Python worker pipeline
- primary Windows entrypoint: `cli.bat`
- WSL/developer backdoor: direct `docker compose ...` commands
- coordination: Docker-managed filesystem run directories

## User Flow

1. keep `outputRoot` in `settings.json`
2. run `.\cli.bat items refresh --file C:\path\chatgpt-export.zip` from Windows command host or PowerShell
3. the wrapper copies the ZIP into a temporary container path
4. the Docker CLI creates an internal run directory
5. the worker writes status, result, index, timeline, and attachment inventory files
6. the final `outputRoot` is rebuilt from the supplied ZIP
7. use the final ZIP handoff package when another LLM or review workflow needs the output

The Docker CLI `process` command remains available for one-off ZIP or extracted export directory processing.
The `config-check` command validates the configured output/runtime roots without processing inputs.

## Output Model

Every run writes:

- `request.json`
- `status.json`
- `result.json`
- `manifest.json`
- `logs/worker.log`
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
- `llm/README.md`

Every refresh writes:

- `index.json` in the configured output root
- `index.md` in the configured output root
- `refresh-<timestamp>.json` in the configured output root
- internal `current.json` and `refresh-history.jsonl` in the Docker-managed run root
- final per-conversation artifacts under the configured `outputRoot`

## Current contract gaps

The shared Timeline baseline includes `input_snapshot.json` and `fidelity_report.json`.
This scaffold does not emit those files yet.
Current equivalents are partial:

- input identity is recorded in `request.json`
- input summary is recorded in `export_summary.json`
- parser limitations are documented in README limitations, worker logs, result warnings, and timeline metadata

Future contract work should add explicit `input_snapshot.json` and `fidelity_report.json` without removing the current files.

## Current scaffold scope

- one ChatGPT export ZIP per `items refresh --file`
- full rebuild of the configured `outputRoot` from the supplied ZIP
- refresh lock file to reject overlapping refresh runs
- internal current-run pointer and refresh history
- local settings example with only `outputRoot`
- current-branch-first normalization
- best-effort text extraction
- best-effort timeline rendering
- the worker rejects obviously corrupted ZIP files before pretending the export is usable
