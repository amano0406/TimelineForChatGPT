# TimelineForChatGPT

## What This Product Does

TimelineForChatGPT converts one ChatGPT export ZIP into per-conversation timeline artifacts. It is a local Windows product with a small API for Timeline integration, and the conversion worker runs through Docker Compose.

The output is designed to be easy to inspect, package, and hand off to another Timeline product or an LLM workflow.

`start.ps1` also starts a small local API on the Windows host. The API is used by Timeline for product operations; host CLI launchers have been removed.

## Runtime

```powershell
cd C:\apps\TimelineForChatGPT
.\start.ps1
```

`start.ps1` starts:

- `worker`: Python conversion worker.
- native API: C# local API for health and item operations.

Stop the services without deleting generated data:

```powershell
.\stop.ps1
```

## Settings

The local settings file is:

```text
C:\apps\TimelineForChatGPT\settings.json
```

Expected shape:

```json
{
  "schemaVersion": 1,
  "runtime": {
    "instanceName": "29b8a84688",
    "apiPort": 19300
  },
  "outputRoot": "C:\\TimelineData\\chatgpt"
}
```

- `runtime.instanceName` scopes the Docker Compose project.
- `runtime.apiPort` controls the local health API port.
- `outputRoot` is where current timeline artifacts are written.

Unknown product-specific settings are preserved by settings updates.

## Input And Output

Provide one ChatGPT export ZIP when you refresh:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/refresh -Body '{"file":"C:\\path\\chatgpt-export.zip"}' -ContentType 'application/json'
```

The source ZIP is not deleted, moved, renamed, or overwritten.

The configured output root contains:

```text
<outputRoot>\
  manifest.json
  <conversation-id>\
    convert_info.json
    timeline.json
```

`items download` creates a handoff ZIP containing `README.md`, `convert_info.json`, and `timeline.json` for the exported conversations.

See [docs/OUTPUTS.md](docs/OUTPUTS.md) for the concrete JSON structure and field meanings.

## Quick Start

```powershell
cd C:\apps\TimelineForChatGPT
.\start.ps1
Invoke-RestMethod http://127.0.0.1:19300/health
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/settings/status -Body '{}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/refresh -Body '{"file":"C:\\path\\chatgpt-export.zip"}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/list -Body '{}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/download -Body '{"to":"C:\\path\\handoff"}' -ContentType 'application/json'
```

## Local API

```powershell
Invoke-RestMethod http://127.0.0.1:19300/health
```

The endpoint returns a JSON boolean: `true` when the settings file is readable and has a valid `outputRoot` / `runtime.apiPort`, otherwise `false`.

Supported API routes:

- `GET /health`
- `POST /items/refresh`
- `POST /items/list`
- `POST /items/detail`
- `POST /items/download`
- `POST /settings/status`
- `POST /settings/init`

`POST /items/list`, `POST /items/download`, `POST /items/detail`, and
`POST /settings/status` are handled directly by the local C# API from the
generated artifacts and `settings.json`. `POST /items/refresh` invokes the
Docker worker directly from C#. If the worker is not
already running, refresh returns an error instead of starting Docker implicitly.

## Supported Item Operations

The supported item commands are:

- `items refresh`: convert one ChatGPT export ZIP.
- `items list`: list generated conversation items.
- `items detail`: read one generated conversation timeline for detail preview.
- `items download`: create a handoff ZIP from generated items.

This product does not provide `items remove`. Source ZIP deletion and generated-data cleanup are outside the current API contract.

## Common API Calls

```powershell
.\start.ps1
.\stop.ps1

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/settings/status -Body '{}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/refresh -Body '{"file":"C:\\path\\chatgpt-export.zip"}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/list -Body '{"page":1,"pageSize":100}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/download -Body '{"to":"C:\\path\\handoff"}' -ContentType 'application/json'
```

## Detailed Docs

- [docs/OUTPUTS.md](docs/OUTPUTS.md): read this when you need the generated file layout.
- [docs/RUNTIME.md](docs/RUNTIME.md): read this when you need runtime requirements and settings.
- [docs/TESTING.md](docs/TESTING.md): read this when you need validation commands.
