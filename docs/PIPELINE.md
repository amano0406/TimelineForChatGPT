# Pipeline

## 1. Request Creation

The web app writes `request.json` into a new `job-*` directory under the configured output root.

## 2. Worker Pickup

The Python worker polls output roots for pending jobs whose `status.json` is still `pending`.

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
