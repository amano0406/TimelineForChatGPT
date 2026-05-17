# Runtime

[Back to README](../README.md)

## Requirements

- Windows
- Docker Desktop
- Git checkout at `C:\apps\TimelineForChatGPT`
- PowerShell or `cmd.exe`

Timeline integration uses the local API started by `start.ps1`. The Python
worker runs inside Docker Compose. `POST /items/list`, `POST /items/download`,
`POST /items/detail`, and `POST /settings/status` are handled directly by the
local C# API from `settings.json` and generated artifacts. `POST /items/refresh`
invokes the Docker worker directly from C# with auto-start disabled.

The local API exposes:

```text
GET  /health
POST /items/refresh
POST /items/list
POST /items/detail
POST /items/download
POST /settings/status
POST /settings/init
```

Use these commands to explicitly control the persistent worker:

```powershell
.\start.ps1
.\stop.ps1
```

`start.ps1` starts the Compose-managed `worker` service and the Windows-hosted local API. `stop.ps1` stops both without deleting Docker volumes. `start.bat` and `stop.bat` are Windows convenience wrappers for the same PowerShell scripts.

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

## Safety Notes

- The source ChatGPT export ZIP is input only. It is not deleted, moved, renamed, or overwritten.
- `items refresh --file` rebuilds the current output root from the supplied ZIP.
- Download commands do not overwrite an existing ZIP unless `--overwrite` is passed.
- Attachment references may appear in metadata, but binary attachment files are not copied into the handoff ZIP.
