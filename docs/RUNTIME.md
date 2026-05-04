# Runtime

[Back to README](../README.md)

## Requirements

- Windows
- Docker Desktop
- Git checkout at `C:\apps\TimelineForChatGPT`
- PowerShell or `cmd.exe`

Normal operation uses `cli.bat`. The Python worker runs inside Docker Compose.

## Settings

The local settings file is:

```text
C:\apps\TimelineForChatGPT\settings.json
```

The committed template is:

```text
C:\apps\TimelineForChatGPT\settings.example.json
```

`settings.json` is not committed. It is created from the template when missing.

## User-Controlled Setting

```json
{
  "outputRoot": "C:\\TimelineData\\chatgpt"
}
```

`outputRoot` is the destination for current per-conversation output artifacts.

## Docker Data

Runtime state and cache are Docker-managed data:

- `app-data`: run state, locks, current run pointer, refresh history
- `cache-data`: temporary upload and handoff staging

These locations are product-managed and are not user settings.
