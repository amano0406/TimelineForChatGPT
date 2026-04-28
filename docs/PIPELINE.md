# Pipeline

## 1. Request Creation

For normal operation, the CLI `refresh` command reads configured input roots, fingerprints discovered ZIP files, and skips unchanged inputs.

For changed inputs, the CLI writes `request.json` into a new timestamped `job-*` directory under the configured output root.

## 2. Worker Execution

The Python worker can process that run immediately through the CLI `refresh` or `process` command, or it can poll output roots for pending jobs whose `status.json` is still `pending`.

## 3. Extract

For ZIP input, the worker extracts the archive into `input/extracted/` and locates the export root.

## 4. Conversation Discovery

The worker reads:

- `conversations.json`
- `conversations-*.json`

when present.

## 5. Normalization

The worker:

- reads `mapping`
- follows `current_node`
- builds a main-branch message list
- extracts text and attachment references

## 6. Render

The worker writes:

- `conversation_index.jsonl`
- `conversations/<id>/timeline.md`
- `llm/conversation_corpus-YYYY-MM.jsonl`

## 7. Package

The worker creates `job-....zip` containing:

- `conversation_index.jsonl`
- `timelines/*.md`
- `llm/*`

## 8. Failure Model

- conversation-level failures should not block unrelated conversations
- run-level failures still write `status.json` and `result.json`
- `logs/worker.log` is the primary execution trace
- refresh-level results are recorded in timestamped `refresh-....json` reports
- the latest refresh result is also written to `refresh-latest.md` for human review
- unchanged inputs are recorded as `skipped_unchanged` and are not reprocessed unless `--force` is used
