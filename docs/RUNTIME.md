# Runtime

[Back to README](../README.md)

## Requirements

- Windows
- Docker Desktop
- Git checkout at `C:\apps\TimelineForChatGPT`
- PowerShell or `cmd.exe`

Timeline integration uses the local API started by `start.ps1`. The Python
worker runs inside Docker Compose and serves the API itself. Requests do not
call host launchers, do not start Docker implicitly, and do not spawn a separate
Python process for each request.

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

`start.ps1` starts the Compose-managed `worker` service. `stop.ps1` stops it
without deleting Docker volumes. `start.bat` and `stop.bat` are Windows
convenience wrappers for the same PowerShell scripts.

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

The worker also bind-mounts the configured host output directory to
`/workspace/output`. Windows drive paths supplied to the API are translated to
`/mnt/<drive>/...` inside the container and translated back in JSON responses.

## Safety Notes

- The source ChatGPT export ZIP is input only. It is not deleted, moved, renamed, or overwritten.
- `POST /items/refresh` rebuilds the current output root from the supplied ZIP.
- Download commands do not overwrite an existing ZIP unless `--overwrite` is passed.
- Attachment references may appear in metadata, but binary attachment files are not copied into the handoff ZIP.
