# Pipeline

## 1. Request Creation

For normal Windows operation, the `cli.bat` entrypoint invokes `items refresh --file` through the PowerShell wrapper.
The input ZIP is specified explicitly and is copied into a temporary container path for the managed Docker Compose worker.
The command rejects overlapping refresh runs with an internal Docker state lock.

For each refresh, the Docker CLI writes `request.json` into a new timestamped `run-*` directory under the internal `app-data` volume.
Direct `docker compose ...` usage remains available as the WSL/developer backdoor.

## 2. Worker Execution

The Python worker processes the run immediately through `items refresh --file` or `process`.
It can also poll the internal run root for pending runs whose `status.json` is still `pending`.
Host Python CLI execution is blocked for normal operation and is only allowed when `TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1` is set for tests.

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

The run workspace writes:

- `conversation_index.jsonl`
- `conversations/<id>/timeline.md`
- `llm/conversation_corpus-YYYY-MM.jsonl`

The final output root writes:

- `manifest.json`
- `<conversation-id>/convert_info.json`
- `<conversation-id>/timeline.json`

## 7. Package

The worker creates a run archive containing:

- `conversation_index.jsonl`
- `timelines/*.md`
- `llm/*`

`items refresh --file` also creates a handoff ZIP from the final output root. That ZIP contains:

- `README.md`
- `items/<conversation-id>/convert_info.json`
- `items/<conversation-id>/timeline.json`

## 8. Failure Model

- conversation-level failures should not block unrelated conversations
- run-level failures still write `status.json` and `result.json`
- `logs/worker.log` is the primary execution trace
- the latest completed refresh is recorded in internal `current.json`
- refresh history is appended to internal `refresh-history.jsonl`
- the final output root is rebuilt from scratch for the supplied ZIP
