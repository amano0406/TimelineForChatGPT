# Pipeline

[Back to README](../README.md)

## 1. Refresh Request

The user runs:

```powershell
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
```

The wrapper passes the ZIP to the Docker Compose-managed worker through temporary Docker staging.

## 2. Extract

The worker extracts the ZIP and locates ChatGPT export JSON files such as:

- `conversations.json`
- `conversations-*.json`

## 3. Normalize Conversations

For each conversation, the worker reads the conversation graph, follows the exported current path, and extracts message rows, roles, timestamps, text, title, and attachment references when available.

## 4. Write Run Artifacts

The Docker-managed run workspace writes processing artifacts such as:

- `request.json`
- `status.json`
- `result.json`
- `manifest.json`
- `export_summary.json`
- `conversation_index.jsonl`

## 5. Rebuild Current Output

The configured `outputRoot` is rebuilt from the supplied ZIP. The current output contains:

- `manifest.json`
- `<conversation-id>/convert_info.json`
- `<conversation-id>/timeline.json`

## 6. Package

`items download --to` packages the current output into a handoff ZIP. `items refresh --download-to` refreshes and copies that ZIP in one command.

## Failure Model

- ZIP-level failures stop the refresh.
- Conversation-level failures are recorded without changing the source ZIP.
- Run diagnostics are written to Docker-managed run state.
